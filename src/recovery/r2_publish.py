"""Publish one verified PostgreSQL recovery generation to S3-compatible storage."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from recovery.postgres_artifact import CONTRACT_VERSION, verify_generation
from steam.ingest.s3_compat import S3CompatibleObjectStorePreconditionFailed

PORTABLE_KEY_ROOT = "postgres-recovery/v1"
# R2's nominal 5 GiB single-part boundary excludes a documented 5 MiB margin.
MAX_SINGLE_PUT_BYTES = (5 * 1024 * 1024 * 1024) - (5 * 1024 * 1024)
_MANIFEST_MAX_BYTES = 64 * 1024
_CHECKSUM_MAX_BYTES = 256
_TRANSFER_CHUNK_BYTES = 1024 * 1024


class RecoveryObjectStore(Protocol):
    """Transport operations required by the recovery publish contract."""

    def put_file(
        self,
        *,
        object_key: str,
        source_path: Path,
        content_type: str,
        if_none_match: bool = False,
    ) -> None: ...

    def put_bytes(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        if_none_match: bool = False,
    ) -> None: ...

    def get_file(
        self,
        *,
        object_key: str,
        destination_path: Path,
        chunk_size: int = _TRANSFER_CHUNK_BYTES,
        max_bytes: int | None = None,
    ) -> None: ...

    def get_bytes(
        self,
        *,
        object_key: str,
        max_bytes: int | None = None,
    ) -> bytes: ...


class RecoveryPublishFailure(StrEnum):
    """Sanitized failure categories exposed by recovery publishing."""

    INVALID_LOCAL_GENERATION = "invalid_local_generation"
    UNSUPPORTED_OBJECT_SIZE = "unsupported_object_size"
    REMOTE_PRECONDITION_COLLISION = "remote_precondition_collision"
    REMOTE_TRANSPORT_FAILURE = "remote_transport_failure"
    REMOTE_VERIFICATION_FAILURE = "remote_verification_failure"


class RecoveryPublishError(RuntimeError):
    """A recovery-facing publish failure without provider or filesystem detail."""

    def __init__(
        self,
        category: RecoveryPublishFailure,
        *,
        generation_id: str | None = None,
        artifact_role: str | None = None,
    ) -> None:
        details = [category.value]
        if generation_id is not None:
            details.append(f"generation={generation_id}")
        if artifact_role is not None:
            details.append(f"artifact={artifact_role}")
        super().__init__(": ".join(details))
        self.category = category
        self.generation_id = generation_id
        self.artifact_role = artifact_role


@dataclass(frozen=True, slots=True)
class VerifiedRemoteGeneration:
    """Successful remote-derived A1 verification result."""

    generation_id: str
    object_keys: tuple[str, str, str]
    reconciled_artifacts: tuple[str, ...] = ()
    verified: bool = True


@dataclass(frozen=True, slots=True)
class _LocalGeneration:
    generation_id: str
    dump_filename: str
    dump_path: Path
    dump_size: int
    dump_checksum: str
    checksum_bytes: bytes
    manifest_bytes: bytes
    dump_key: str
    checksum_key: str
    manifest_key: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_TRANSFER_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unsupported_size(*, generation_id: str, artifact_role: str) -> RecoveryPublishError:
    return RecoveryPublishError(
        RecoveryPublishFailure.UNSUPPORTED_OBJECT_SIZE,
        generation_id=generation_id,
        artifact_role=artifact_role,
    )


def _read_local_generation(generation_dir: Path) -> _LocalGeneration:
    try:
        verification = verify_generation(generation_dir)
    except (OSError, ValueError):
        verification = None
    if verification is None or not verification.passed:
        raise RecoveryPublishError(RecoveryPublishFailure.INVALID_LOCAL_GENERATION)

    try:
        manifest_bytes = (generation_dir / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        generation_id = manifest["generation_id"]
        dump_filename = manifest["dump_filename"]
        dump_checksum = manifest["checksum_value"]
        dump_path = generation_dir / dump_filename
        dump_size = dump_path.stat().st_size
        checksum_bytes = (generation_dir / f"{dump_filename}.sha256").read_bytes()
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise RecoveryPublishError(
            RecoveryPublishFailure.INVALID_LOCAL_GENERATION
        ) from None

    if dump_size > MAX_SINGLE_PUT_BYTES:
        raise _unsupported_size(generation_id=generation_id, artifact_role="dump")
    if len(checksum_bytes) > _CHECKSUM_MAX_BYTES:
        raise _unsupported_size(generation_id=generation_id, artifact_role="checksum")
    if len(manifest_bytes) > _MANIFEST_MAX_BYTES:
        raise _unsupported_size(generation_id=generation_id, artifact_role="manifest")

    base_key = f"{PORTABLE_KEY_ROOT}/{generation_id}"
    return _LocalGeneration(
        generation_id=generation_id,
        dump_filename=dump_filename,
        dump_path=dump_path,
        dump_size=dump_size,
        dump_checksum=dump_checksum,
        checksum_bytes=checksum_bytes,
        manifest_bytes=manifest_bytes,
        dump_key=f"{base_key}/{dump_filename}",
        checksum_key=f"{base_key}/{dump_filename}.sha256",
        manifest_key=f"{base_key}/manifest.json",
    )


def _copy_file_exact(*, source: Path, destination: Path, expected_size: int) -> None:
    transferred = 0
    with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
        while chunk := source_handle.read(_TRANSFER_CHUNK_BYTES):
            transferred += len(chunk)
            if transferred > expected_size:
                raise RecoveryPublishError(RecoveryPublishFailure.INVALID_LOCAL_GENERATION)
            destination_handle.write(chunk)
    if transferred != expected_size:
        raise RecoveryPublishError(RecoveryPublishFailure.INVALID_LOCAL_GENERATION)


@contextmanager
def _stabilized_local_generation(generation_dir: Path) -> Iterator[_LocalGeneration]:
    source = _read_local_generation(Path(generation_dir))
    try:
        snapshot_context = tempfile.TemporaryDirectory(prefix="postgres-recovery-local-")
    except OSError:
        raise RecoveryPublishError(
            RecoveryPublishFailure.INVALID_LOCAL_GENERATION
        ) from None

    with snapshot_context as snapshot_root:
        snapshot_dir = Path(snapshot_root) / source.generation_id
        try:
            snapshot_dir.mkdir()
            _copy_file_exact(
                source=source.dump_path,
                destination=snapshot_dir / source.dump_filename,
                expected_size=source.dump_size,
            )
            (snapshot_dir / f"{source.dump_filename}.sha256").write_bytes(
                source.checksum_bytes
            )
            (snapshot_dir / "manifest.json").write_bytes(source.manifest_bytes)
        except RecoveryPublishError:
            raise
        except OSError:
            raise RecoveryPublishError(
                RecoveryPublishFailure.INVALID_LOCAL_GENERATION
            ) from None
        stabilized = _read_local_generation(snapshot_dir)
        yield stabilized


def _reconcile_file(
    *,
    client: RecoveryObjectStore,
    local: _LocalGeneration,
    object_key: str,
) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="postgres-recovery-reconcile-") as temp_root:
            fetched_path = Path(temp_root) / "remote.dump"
            client.get_file(
                object_key=object_key,
                destination_path=fetched_path,
                chunk_size=_TRANSFER_CHUNK_BYTES,
                max_bytes=local.dump_size,
            )
            return (
                fetched_path.stat().st_size == local.dump_size
                and _sha256(fetched_path) == local.dump_checksum
            )
    except Exception:
        return False


def _reconcile_bytes(
    *,
    client: RecoveryObjectStore,
    object_key: str,
    expected: bytes,
) -> bool:
    try:
        return client.get_bytes(object_key=object_key, max_bytes=len(expected)) == expected
    except Exception:
        return False


def _publish_file(
    *,
    client: RecoveryObjectStore,
    local: _LocalGeneration,
    object_key: str,
) -> bool:
    try:
        client.put_file(
            object_key=object_key,
            source_path=local.dump_path,
            content_type="application/octet-stream",
            if_none_match=True,
        )
        return False
    except S3CompatibleObjectStorePreconditionFailed:
        if _reconcile_file(client=client, local=local, object_key=object_key):
            return True
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_PRECONDITION_COLLISION,
            generation_id=local.generation_id,
            artifact_role="dump",
        ) from None
    except Exception:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_TRANSPORT_FAILURE,
            generation_id=local.generation_id,
            artifact_role="dump",
        ) from None


def _publish_bytes(
    *,
    client: RecoveryObjectStore,
    local: _LocalGeneration,
    object_key: str,
    expected: bytes,
    artifact_role: str,
    content_type: str,
) -> bool:
    try:
        client.put_bytes(
            object_key=object_key,
            payload=expected,
            content_type=content_type,
            if_none_match=True,
        )
        return False
    except S3CompatibleObjectStorePreconditionFailed:
        if _reconcile_bytes(client=client, object_key=object_key, expected=expected):
            return True
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_PRECONDITION_COLLISION,
            generation_id=local.generation_id,
            artifact_role=artifact_role,
        ) from None
    except Exception:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_TRANSPORT_FAILURE,
            generation_id=local.generation_id,
            artifact_role=artifact_role,
        ) from None


def _validate_remote_manifest(local: _LocalGeneration, payload: bytes) -> None:
    try:
        manifest = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="manifest",
        ) from None
    if not isinstance(manifest, dict):
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="manifest",
        )
    if (
        manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("generation_id") != local.generation_id
        or manifest.get("dump_filename") != local.dump_filename
        or manifest.get("dump_size_bytes") != local.dump_size
    ):
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="manifest",
        )


def _verify_remote_against_local(
    *,
    client: RecoveryObjectStore,
    local: _LocalGeneration,
    verification_root: Path | None,
) -> VerifiedRemoteGeneration:
    try:
        remote_manifest = client.get_bytes(
            object_key=local.manifest_key,
            max_bytes=_MANIFEST_MAX_BYTES,
        )
    except Exception:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="manifest",
        ) from None
    _validate_remote_manifest(local, remote_manifest)

    try:
        remote_checksum = client.get_bytes(
            object_key=local.checksum_key,
            max_bytes=_CHECKSUM_MAX_BYTES,
        )
    except Exception:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="checksum",
        ) from None

    try:
        with tempfile.TemporaryDirectory(
            prefix="postgres-recovery-verify-",
            dir=verification_root,
        ) as temp_root:
            materialized = Path(temp_root) / local.generation_id
            materialized.mkdir()
            (materialized / "manifest.json").write_bytes(remote_manifest)
            (materialized / f"{local.dump_filename}.sha256").write_bytes(remote_checksum)
            client.get_file(
                object_key=local.dump_key,
                destination_path=materialized / local.dump_filename,
                chunk_size=_TRANSFER_CHUNK_BYTES,
                max_bytes=local.dump_size,
            )
            verification = verify_generation(materialized)
            remote_dump_checksum = _sha256(materialized / local.dump_filename)
    except RecoveryPublishError:
        raise
    except Exception:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="dump",
        ) from None
    if not verification.passed:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
        )
    if remote_dump_checksum != local.dump_checksum:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="dump",
        )
    if remote_manifest != local.manifest_bytes:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="manifest",
        )
    if remote_checksum != local.checksum_bytes:
        raise RecoveryPublishError(
            RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            generation_id=local.generation_id,
            artifact_role="checksum",
        )
    return VerifiedRemoteGeneration(
        generation_id=local.generation_id,
        object_keys=(local.dump_key, local.checksum_key, local.manifest_key),
    )


def verify_remote_generation(
    *,
    client: RecoveryObjectStore,
    generation_dir: Path,
    verification_root: Path | None = None,
) -> VerifiedRemoteGeneration:
    """Read back and verify a remote generation against its stable local source."""

    with _stabilized_local_generation(Path(generation_dir)) as local:
        return _verify_remote_against_local(
            client=client,
            local=local,
            verification_root=verification_root,
        )


def publish_verified_generation(
    *,
    client: RecoveryObjectStore,
    generation_dir: Path,
    verification_root: Path | None = None,
) -> VerifiedRemoteGeneration:
    """Conditionally publish and independently verify one completed A1 generation."""

    with _stabilized_local_generation(Path(generation_dir)) as local:
        reconciled: list[str] = []

        if _publish_file(client=client, local=local, object_key=local.dump_key):
            reconciled.append("dump")
        if _publish_bytes(
            client=client,
            local=local,
            object_key=local.checksum_key,
            expected=local.checksum_bytes,
            artifact_role="checksum",
            content_type="text/plain",
        ):
            reconciled.append("checksum")
        if _publish_bytes(
            client=client,
            local=local,
            object_key=local.manifest_key,
            expected=local.manifest_bytes,
            artifact_role="manifest",
            content_type="application/json",
        ):
            reconciled.append("manifest")

        verified = verify_remote_generation(
            client=client,
            generation_dir=local.dump_path.parent,
            verification_root=verification_root,
        )
        return replace(
            verified,
            reconciled_artifacts=tuple(reconciled),
        )
