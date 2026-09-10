"""Retain one remote-derived A1 generation without publishing or restoring it.

The caller supplies a new local root under an existing, trusted parent directory.
Only completed/<generation_id> returned after verification is a successful result;
failed roots and staging contents are retained without cleanup, resume, or retry.
The remote manifest/checksum/dump are the sole artifact source, not a local backup.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn

from recovery import postgres_artifact, r2_activation, r2_publish
from steam.ingest.s3_compat import S3CompatibleObjectStoreClient


class RecoveryMaterializationFailure(StrEnum):
    """Failure categories that never contain provider or filesystem details."""

    INVALID_ARGUMENTS = "invalid_arguments"
    INVALID_DESTINATION = "invalid_destination"
    DESTINATION_COLLISION = "destination_collision"
    INVALID_REMOTE_MANIFEST = "invalid_remote_manifest"
    GENERATION_IDENTITY_MISMATCH = "generation_identity_mismatch"
    UNSUPPORTED_OBJECT_SIZE = "unsupported_object_size"
    REMOTE_TRANSPORT_FAILURE = "remote_transport_failure"
    CONTENT_VERIFICATION_FAILURE = "content_verification_failure"
    LOCAL_MATERIALIZATION_FAILURE = "local_materialization_failure"
    A1_VERIFICATION_FAILURE = "a1_verification_failure"
    INTERNAL_ERROR = "internal_error"


class RecoveryMaterializationError(RuntimeError):
    """A sanitized materialization failure, including for direct API callers."""

    def __init__(self, category: RecoveryMaterializationFailure) -> None:
        super().__init__(category.value)
        self.category = category


@dataclass(frozen=True, slots=True)
class MaterializedRemoteGeneration:
    """A retained, verified source; this does not establish restore compatibility."""

    generation_id: str
    generation_dir: Path
    verified: bool = True


def _validate_generation_id(generation_id: str) -> None:
    if (
        not isinstance(generation_id, str)
        or r2_publish._GENERATION_ID.fullmatch(generation_id) is None
    ):
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.INVALID_ARGUMENTS)


def _get_bytes(client: r2_publish.RecoveryObjectStore, *, object_key: str, max_bytes: int) -> bytes:
    try:
        payload = client.get_bytes(object_key=object_key, max_bytes=max_bytes)
    except Exception:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.REMOTE_TRANSPORT_FAILURE
        ) from None
    if not isinstance(payload, bytes):
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.REMOTE_TRANSPORT_FAILURE)
    if len(payload) > max_bytes:
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.UNSUPPORTED_OBJECT_SIZE)
    return payload


def _read_remote_manifest(payload: bytes, generation_id: str) -> tuple[str, int]:
    try:
        manifest = json.loads(payload)
        if not isinstance(manifest, dict):
            raise ValueError
        if manifest.get("generation_id") != generation_id:
            raise RecoveryMaterializationError(
                RecoveryMaterializationFailure.GENERATION_IDENTITY_MISMATCH
            )
        logical_name = manifest.get("database_logical_name")
        if not isinstance(logical_name, str):
            raise ValueError
        filename = f"{postgres_artifact.safe_database_filename(logical_name)}.dump"
        size = manifest.get("dump_size_bytes")
        checksum = manifest.get("checksum_value")
        if (
            manifest.get("contract_version") != postgres_artifact.CONTRACT_VERSION
            or manifest.get("dump_filename") != filename
            or manifest.get("dump_format") != "custom"
            or manifest.get("generator") != postgres_artifact.GENERATOR
            or manifest.get("verification_status") != "PASS"
            or manifest.get("checksum_algorithm") != "sha256"
            or not isinstance(checksum, str)
            or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.INVALID_REMOTE_MANIFEST
        ) from None
    if size > r2_publish.MAX_SINGLE_PUT_BYTES:
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.UNSUPPORTED_OBJECT_SIZE)
    return filename, size


def _reserve_destination(destination: Path) -> Path:
    try:
        destination = Path(destination)
        if not destination.name or destination.name in {".", ".."}:
            raise ValueError
        destination = destination.parent.resolve(strict=True) / destination.name
        destination.mkdir(mode=0o700)
    except FileExistsError:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.DESTINATION_COLLISION
        ) from None
    except (OSError, ValueError, TypeError, RuntimeError):
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.INVALID_DESTINATION
        ) from None
    return destination


def _materialize(
    *, client: r2_publish.RecoveryObjectStore, generation_id: str, destination: Path
) -> MaterializedRemoteGeneration:
    _validate_generation_id(generation_id)
    destination = _reserve_destination(destination)
    staging_parent = destination / postgres_artifact.STAGING_DIRNAME
    completed_parent = destination / postgres_artifact.COMPLETED_DIRNAME
    staging_parent.mkdir(mode=0o700)
    completed_parent.mkdir(mode=0o700)
    staging = staging_parent / generation_id
    completed = completed_parent / generation_id
    staging.mkdir(mode=0o700)

    base_key = f"{r2_publish.PORTABLE_KEY_ROOT}/{generation_id}"
    manifest_bytes = _get_bytes(
        client,
        object_key=f"{base_key}/manifest.json",
        max_bytes=r2_publish._MANIFEST_MAX_BYTES,
    )
    filename, size = _read_remote_manifest(manifest_bytes, generation_id)
    checksum_bytes = _get_bytes(
        client,
        object_key=f"{base_key}/{filename}.sha256",
        max_bytes=r2_publish._CHECKSUM_MAX_BYTES,
    )
    with (staging / "manifest.json").open("xb") as handle:
        handle.write(manifest_bytes)
    with (staging / f"{filename}.sha256").open("xb") as handle:
        handle.write(checksum_bytes)
    try:
        client.get_file(
            object_key=f"{base_key}/{filename}",
            destination_path=staging / filename,
            chunk_size=r2_publish._TRANSFER_CHUNK_BYTES,
            max_bytes=size,
        )
    except FileExistsError:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.DESTINATION_COLLISION
        ) from None
    except Exception:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.REMOTE_TRANSPORT_FAILURE
        ) from None

    expected_names = {"manifest.json", filename, f"{filename}.sha256"}
    if {path.name for path in staging.iterdir()} != expected_names or any(
        path.is_symlink() or not path.is_file() for path in staging.iterdir()
    ):
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.CONTENT_VERIFICATION_FAILURE
        )
    actual_size = (staging / filename).stat().st_size
    if actual_size > size:
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.UNSUPPORTED_OBJECT_SIZE)
    if actual_size != size:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.CONTENT_VERIFICATION_FAILURE
        )
    try:
        verification = postgres_artifact.verify_generation(staging)
    except Exception:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.A1_VERIFICATION_FAILURE
        ) from None
    if not verification.passed:
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.A1_VERIFICATION_FAILURE)
    with (staging / "manifest.json").open("rb") as handle:
        final_manifest = handle.read(r2_publish._MANIFEST_MAX_BYTES + 1)
    _read_remote_manifest(final_manifest, generation_id)
    if final_manifest != manifest_bytes:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.CONTENT_VERIFICATION_FAILURE
        )
    # Package-internal reuse preserves A1's Linux atomic no-replace semantics.
    try:
        postgres_artifact._rename_no_replace(staging, completed)
    except postgres_artifact.GenerationError:
        category = RecoveryMaterializationFailure.LOCAL_MATERIALIZATION_FAILURE
        if completed.exists() or completed.is_symlink():
            category = RecoveryMaterializationFailure.DESTINATION_COLLISION
        raise RecoveryMaterializationError(category) from None
    return MaterializedRemoteGeneration(generation_id=completed.name, generation_dir=completed)


def materialize_remote_generation(
    *,
    client: r2_publish.RecoveryObjectStore,
    generation_id: str,
    destination: Path,
) -> MaterializedRemoteGeneration:
    """GET and verify remote artifacts into a fresh root, retaining all failure state.

    The existing client must honor bounded reads and exclusive file creation.
    Only GET methods are used; no original local generation, retry, or cleanup is
    involved. A successful result retains destination/completed/<generation_id>.
    The destination parent must be trusted and not concurrently replaced.
    """

    try:
        return _materialize(client=client, generation_id=generation_id, destination=destination)
    except RecoveryMaterializationError:
        raise
    except FileExistsError:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.DESTINATION_COLLISION
        ) from None
    except OSError:
        raise RecoveryMaterializationError(
            RecoveryMaterializationFailure.LOCAL_MATERIALIZATION_FAILURE
        ) from None
    except Exception:
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.INTERNAL_ERROR) from None


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise RecoveryMaterializationError(RecoveryMaterializationFailure.INVALID_ARGUMENTS)


def build_parser() -> argparse.ArgumentParser:
    """Describe the retained materialization contract without accessing credentials."""

    parser = _SanitizedArgumentParser(
        description="GET and A1-verify one existing R2 generation; does not run pg_restore.",
        epilog=(
            "Uses PMTS_RECOVERY_R2_* configuration only. The destination parent must "
            "already exist and be trusted. Success retains completed/<generation-id> "
            "under the fresh destination; failures preserve staging/<generation-id>. "
            "No overwrite, automatic retry, resume, or cleanup. Real A4 materialization "
            "requires separate Human Gate approval; Phase 1 validation uses fakes only."
        ),
    )
    parser.add_argument("--generation-id", required=True, help="exact selected remote identity")
    parser.add_argument("--destination", type=Path, required=True, help="new local root only")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    client_factory: r2_activation.ClientFactory | None = None,
) -> int:
    """Compose the existing R2 client with sanitized materialization PASS/FAIL output."""

    try:
        args = build_parser().parse_args(argv)
        _validate_generation_id(args.generation_id)
        config = r2_activation.load_recovery_r2_config(environ)
        # Validate room for the longest allowed filename before the manifest GET.
        longest_key = f"{r2_publish.PORTABLE_KEY_ROOT}/{args.generation_id}/{'a' * 63}.dump.sha256"
        if len(config.resolve_remote_key(longest_key).encode("utf-8")) > 1024:
            raise r2_activation.RecoveryActivationError(
                r2_activation.RecoveryActivationFailure.INVALID_CONFIG
            )
        client = (client_factory or S3CompatibleObjectStoreClient)(config)
        result = materialize_remote_generation(
            client=client, generation_id=args.generation_id, destination=args.destination
        )
        if (
            not result.verified
            or result.generation_id != args.generation_id
            or result.generation_dir.name != args.generation_id
        ):
            raise RecoveryMaterializationError(
                RecoveryMaterializationFailure.GENERATION_IDENTITY_MISMATCH
            )
        print(f"generation={result.generation_id}")
        print("local_verification=PASS")
        print("materialization=PASS")
        return 0
    except (RecoveryMaterializationError, r2_activation.RecoveryActivationError) as exc:
        category = exc.category.value
    except Exception:
        category = RecoveryMaterializationFailure.INTERNAL_ERROR.value
    print(f"ERROR: recovery materialization failed: {category}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
