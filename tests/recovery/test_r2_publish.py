from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from recovery import r2_publish
from recovery.postgres_artifact import VerificationResult
from steam.ingest.s3_compat import S3CompatibleObjectStorePreconditionFailed


class FakeRecoveryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str, bool]] = []
        self.failed_put_keys: set[str] = set()
        self.after_put: Callable[[str, FakeRecoveryStore], None] | None = None
        self.before_put_file: Callable[[Path], None] | None = None

    def put_file(
        self,
        *,
        object_key: str,
        source_path: Path,
        content_type: str,
        if_none_match: bool = False,
    ) -> None:
        del content_type
        self.calls.append(("PUT_FILE", object_key, if_none_match))
        if self.before_put_file is not None:
            self.before_put_file(source_path)
        if object_key in self.failed_put_keys:
            raise RuntimeError("SECRET_MARKER ENDPOINT_MARKER PRIVATE_PATH_MARKER")
        if if_none_match and object_key in self.objects:
            raise S3CompatibleObjectStorePreconditionFailed("already exists")
        chunks: list[bytes] = []
        with source_path.open("rb") as source:
            while chunk := source.read(3):
                chunks.append(chunk)
        self.objects[object_key] = b"".join(chunks)
        if self.after_put is not None:
            self.after_put(object_key, self)

    def put_bytes(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        if_none_match: bool = False,
    ) -> None:
        del content_type
        self.calls.append(("PUT_BYTES", object_key, if_none_match))
        if object_key in self.failed_put_keys:
            raise RuntimeError("SECRET_MARKER ENDPOINT_MARKER PRIVATE_PATH_MARKER")
        if if_none_match and object_key in self.objects:
            raise S3CompatibleObjectStorePreconditionFailed("already exists")
        self.objects[object_key] = payload
        if self.after_put is not None:
            self.after_put(object_key, self)

    def get_file(
        self,
        *,
        object_key: str,
        destination_path: Path,
        chunk_size: int = 1024 * 1024,
        max_bytes: int | None = None,
    ) -> None:
        self.calls.append(("GET_FILE", object_key, False))
        if object_key not in self.objects:
            raise RuntimeError("SECRET_MARKER ENDPOINT_MARKER PRIVATE_PATH_MARKER")
        payload = self.objects[object_key]
        if max_bytes is not None and len(payload) > max_bytes:
            raise RuntimeError("remote object is too large")
        with destination_path.open("xb") as destination:
            for offset in range(0, len(payload), chunk_size):
                destination.write(payload[offset : offset + chunk_size])

    def get_bytes(self, *, object_key: str, max_bytes: int | None = None) -> bytes:
        self.calls.append(("GET_BYTES", object_key, False))
        if object_key not in self.objects:
            raise RuntimeError("SECRET_MARKER ENDPOINT_MARKER PRIVATE_PATH_MARKER")
        payload = self.objects[object_key]
        if max_bytes is not None and len(payload) > max_bytes:
            raise RuntimeError("remote object is too large")
        return payload


def create_valid_generation(tmp_path: Path) -> Path:
    generation = tmp_path / "completed" / "generation-001"
    generation.mkdir(parents=True)
    dump = b"postgres-custom-dump-payload"
    checksum = hashlib.sha256(dump).hexdigest()
    (generation / "appdb.dump").write_bytes(dump)
    (generation / "appdb.dump.sha256").write_text(checksum + "\n", encoding="ascii")
    manifest = {
        "checksum_algorithm": "sha256",
        "checksum_value": checksum,
        "completed_at_utc": "2026-09-04T01:02:04Z",
        "contract_version": "postgres-recovery-artifact/v1",
        "created_at_utc": "2026-09-04T01:02:03Z",
        "database_logical_name": "appdb",
        "dump_filename": "appdb.dump",
        "dump_format": "custom",
        "dump_size_bytes": len(dump),
        "generation_id": "generation-001",
        "generator": "recovery.postgres_artifact",
        "verification_status": "PASS",
    }
    (generation / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return generation


def expected_keys() -> tuple[str, str, str]:
    base = "postgres-recovery/v1/generation-001"
    return (
        f"{base}/appdb.dump",
        f"{base}/appdb.dump.sha256",
        f"{base}/manifest.json",
    )


def test_valid_generation_publishes_in_order_and_verifies_remote_readback(
    tmp_path: Path,
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()

    result = r2_publish.publish_verified_generation(
        client=store,
        generation_dir=generation,
        verification_root=tmp_path,
    )

    dump_key, checksum_key, manifest_key = expected_keys()
    assert result.verified
    assert result.generation_id == "generation-001"
    assert result.object_keys == expected_keys()
    assert result.reconciled_artifacts == ()
    assert list(store.objects) == [dump_key, checksum_key, manifest_key]
    assert store.calls[:3] == [
        ("PUT_FILE", dump_key, True),
        ("PUT_BYTES", checksum_key, True),
        ("PUT_BYTES", manifest_key, True),
    ]
    assert store.calls[-3:] == [
        ("GET_BYTES", manifest_key, False),
        ("GET_BYTES", checksum_key, False),
        ("GET_FILE", dump_key, False),
    ]


def test_a1_verifier_runs_against_fresh_remote_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, checksum_key, manifest_key = expected_keys()
    store.objects = {
        dump_key: (generation / "appdb.dump").read_bytes(),
        checksum_key: (generation / "appdb.dump.sha256").read_bytes(),
        manifest_key: (generation / "manifest.json").read_bytes(),
    }
    verified_paths: list[Path] = []
    original_verify = r2_publish.verify_generation

    def record_verify(path: Path) -> VerificationResult:
        verified_paths.append(path)
        return original_verify(path)

    monkeypatch.setattr(r2_publish, "verify_generation", record_verify)

    result = r2_publish.verify_remote_generation(
        client=store,
        generation_dir=generation,
        verification_root=tmp_path,
    )

    assert result.verified
    assert verified_paths[0] != generation
    assert verified_paths[0].name == generation.name
    assert verified_paths[0].parent.name.startswith("postgres-recovery-local-")
    assert verified_paths[1] != generation
    assert verified_paths[1].name == generation.name
    assert verified_paths[1].parent.name.startswith("postgres-recovery-verify-")
    assert len(verified_paths) == 2
    assert [method for method, _, _ in store.calls] == [
        "GET_BYTES",
        "GET_BYTES",
        "GET_FILE",
    ]


def test_publish_uses_public_remote_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    calls: list[Path] = []
    original_verify_remote = r2_publish.verify_remote_generation

    def record_verify_remote(
        *,
        client: r2_publish.RecoveryObjectStore,
        generation_dir: Path,
        verification_root: Path | None = None,
    ) -> r2_publish.VerifiedRemoteGeneration:
        calls.append(generation_dir)
        return original_verify_remote(
            client=client,
            generation_dir=generation_dir,
            verification_root=verification_root,
        )

    monkeypatch.setattr(r2_publish, "verify_remote_generation", record_verify_remote)

    result = r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert result.verified
    assert len(calls) == 1
    assert calls[0] != generation
    assert calls[0].name == generation.name


def test_coordinated_remote_replacement_cannot_pass_expected_local_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, checksum_key, manifest_key = expected_keys()
    remote_a1_results: list[VerificationResult] = []
    original_verify = r2_publish.verify_generation

    def record_remote_a1(path: Path) -> VerificationResult:
        result = original_verify(path)
        if path.parent.name.startswith("postgres-recovery-verify-"):
            remote_a1_results.append(result)
        return result

    def replace_generation(object_key: str, fake: FakeRecoveryStore) -> None:
        if object_key != manifest_key:
            return
        replacement_dump = b"x" * len(fake.objects[dump_key])
        replacement_checksum = hashlib.sha256(replacement_dump).hexdigest()
        replacement_manifest = json.loads(fake.objects[manifest_key])
        replacement_manifest["checksum_value"] = replacement_checksum
        fake.objects[dump_key] = replacement_dump
        fake.objects[checksum_key] = (replacement_checksum + "\n").encode("ascii")
        fake.objects[manifest_key] = (
            json.dumps(replacement_manifest, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

    monkeypatch.setattr(r2_publish, "verify_generation", record_remote_a1)
    store.after_put = replace_generation

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert remote_a1_results == [VerificationResult(passed=True)]
    assert raised.value.category == r2_publish.RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE
    assert raised.value.artifact_role == "dump"


@pytest.mark.parametrize("mutation", ["replacement", "growth"])
def test_caller_generation_change_cannot_change_uploaded_snapshot(
    tmp_path: Path, mutation: str
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, _, _ = expected_keys()
    caller_dump = generation / "appdb.dump"
    expected_dump = caller_dump.read_bytes()
    upload_sources: list[Path] = []

    def mutate_caller(source_path: Path) -> None:
        upload_sources.append(source_path)
        if mutation == "replacement":
            caller_dump.write_bytes(b"z" * len(expected_dump))
        else:
            with caller_dump.open("ab") as handle:
                handle.write(b"-growth")

    store.before_put_file = mutate_caller

    result = r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert result.verified
    assert upload_sources[0] != caller_dump
    assert store.objects[dump_key] == expected_dump
    assert caller_dump.read_bytes() != expected_dump


def test_coordinated_replacement_during_snapshot_capture_makes_zero_remote_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    manifest_path = generation / "manifest.json"
    dump_path = generation / "appdb.dump"
    checksum_path = generation / "appdb.dump.sha256"
    manifest_a_bytes = manifest_path.read_bytes()
    replacement_dump = b"b" * len(dump_path.read_bytes())
    replacement_checksum = hashlib.sha256(replacement_dump).hexdigest()
    replacement_manifest = json.loads(manifest_a_bytes)
    replacement_manifest["checksum_value"] = replacement_checksum
    manifest_b_bytes = (
        json.dumps(replacement_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    original_copy = r2_publish._copy_file_exact
    capture_seam_calls = 0

    def replace_then_copy(
        *, source: Path, destination: Path, expected_size: int
    ) -> None:
        nonlocal capture_seam_calls
        capture_seam_calls += 1
        assert (destination.parent / "manifest.json").read_bytes() == manifest_a_bytes
        dump_path.write_bytes(replacement_dump)
        checksum_path.write_text(replacement_checksum + "\n", encoding="ascii")
        manifest_path.write_bytes(manifest_b_bytes)
        original_copy(
            source=source,
            destination=destination,
            expected_size=expected_size,
        )

    monkeypatch.setattr(r2_publish, "_copy_file_exact", replace_then_copy)

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert capture_seam_calls == 1
    assert r2_publish.verify_generation(generation).passed
    assert raised.value.category == r2_publish.RecoveryPublishFailure.INVALID_LOCAL_GENERATION
    assert store.calls == []


@pytest.mark.parametrize("fault", ["tampered", "dump", "checksum", "manifest"])
def test_invalid_local_generation_makes_zero_remote_calls(tmp_path: Path, fault: str) -> None:
    generation = create_valid_generation(tmp_path)
    if fault == "tampered":
        (generation / "appdb.dump").write_bytes(b"tampered")
    elif fault == "dump":
        (generation / "appdb.dump").unlink()
    elif fault == "checksum":
        (generation / "appdb.dump.sha256").unlink()
    else:
        (generation / "manifest.json").unlink()
    store = FakeRecoveryStore()

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.INVALID_LOCAL_GENERATION
    assert store.calls == []


@pytest.mark.parametrize("missing_role", ["dump", "checksum", "manifest"])
def test_missing_remote_object_fails_independent_verification(
    tmp_path: Path, missing_role: str
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, checksum_key, manifest_key = expected_keys()
    role_keys = {"dump": dump_key, "checksum": checksum_key, "manifest": manifest_key}

    def remove_after_manifest(object_key: str, fake: FakeRecoveryStore) -> None:
        if object_key == manifest_key:
            fake.objects.pop(role_keys[missing_role])

    store.after_put = remove_after_manifest

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE


def test_remote_dump_corruption_fails_independent_verification(tmp_path: Path) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, _, manifest_key = expected_keys()

    def corrupt_after_manifest(object_key: str, fake: FakeRecoveryStore) -> None:
        if object_key == manifest_key:
            fake.objects[dump_key] = b"corrupt-remote-dump"

    store.after_put = corrupt_after_manifest

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE


@pytest.mark.parametrize("fault", ["checksum", "manifest"])
def test_remote_checksum_or_manifest_inconsistency_fails_verification(
    tmp_path: Path, fault: str
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    _, checksum_key, manifest_key = expected_keys()

    def alter_after_manifest(object_key: str, fake: FakeRecoveryStore) -> None:
        if object_key != manifest_key:
            return
        if fault == "checksum":
            fake.objects[checksum_key] = b"0" * 64 + b"\n"
        else:
            manifest = json.loads(fake.objects[manifest_key])
            manifest["dump_filename"] = "other.dump"
            fake.objects[manifest_key] = json.dumps(manifest).encode()

    store.after_put = alter_after_manifest

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE


def test_identical_preexisting_objects_are_reconciled_without_overwrite(tmp_path: Path) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, checksum_key, manifest_key = expected_keys()
    store.objects = {
        dump_key: (generation / "appdb.dump").read_bytes(),
        checksum_key: (generation / "appdb.dump.sha256").read_bytes(),
        manifest_key: (generation / "manifest.json").read_bytes(),
    }
    before = dict(store.objects)

    result = r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert result.reconciled_artifacts == ("dump", "checksum", "manifest")
    assert store.objects == before
    put_calls = (call for call in store.calls if call[0].startswith("PUT"))
    assert all(if_none_match for _, _, if_none_match in put_calls)


def test_mismatched_preexisting_object_is_collision_without_overwrite(tmp_path: Path) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, _, _ = expected_keys()
    store.objects[dump_key] = b"different-existing-object"

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == (
        r2_publish.RecoveryPublishFailure.REMOTE_PRECONDITION_COLLISION
    )
    assert raised.value.artifact_role == "dump"
    assert store.objects == {dump_key: b"different-existing-object"}
    assert not any(method == "DELETE" for method, _, _ in store.calls)


def test_partial_publish_fails_unverified_and_retry_reconciles_prior_object(
    tmp_path: Path,
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, checksum_key, _ = expected_keys()
    store.failed_put_keys.add(checksum_key)

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.REMOTE_TRANSPORT_FAILURE
    assert list(store.objects) == [dump_key]
    assert not any(method.startswith("GET") for method, _, _ in store.calls)

    store.failed_put_keys.clear()
    result = r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert result.verified
    assert result.reconciled_artifacts == ("dump",)


def test_dump_transfer_does_not_use_path_read_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    original_read_bytes = Path.read_bytes

    def reject_dump_read_bytes(path: Path) -> bytes:
        if path.suffix == ".dump":
            raise AssertionError("dump was materialized as whole bytes")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_dump_read_bytes)

    assert r2_publish.publish_verified_generation(
        client=store,
        generation_dir=generation,
    ).verified


def test_unsupported_single_put_size_fails_before_remote_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    monkeypatch.setattr(r2_publish, "MAX_SINGLE_PUT_BYTES", 1)

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.UNSUPPORTED_OBJECT_SIZE
    assert raised.value.artifact_role == "dump"
    assert store.calls == []


@pytest.mark.parametrize(
    ("artifact_role", "limit_name", "filename"),
    [
        ("checksum", "_CHECKSUM_MAX_BYTES", "appdb.dump.sha256"),
        ("manifest", "_MANIFEST_MAX_BYTES", "manifest.json"),
    ],
)
def test_unsupported_metadata_size_fails_before_remote_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_role: str,
    limit_name: str,
    filename: str,
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    monkeypatch.setattr(
        r2_publish,
        limit_name,
        len((generation / filename).read_bytes()) - 1,
    )

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(client=store, generation_dir=generation)

    assert raised.value.category == r2_publish.RecoveryPublishFailure.UNSUPPORTED_OBJECT_SIZE
    assert raised.value.artifact_role == artifact_role
    assert store.calls == []


@pytest.mark.parametrize(
    "scenario",
    ["invalid_local", "transport", "collision", "remote_verification"],
)
def test_recovery_errors_do_not_leak_private_or_provider_markers(
    tmp_path: Path, scenario: str
) -> None:
    generation = create_valid_generation(tmp_path)
    store = FakeRecoveryStore()
    dump_key, _, manifest_key = expected_keys()

    def corrupt_manifest(object_key: str, fake: FakeRecoveryStore) -> None:
        if object_key == manifest_key:
            fake.objects[manifest_key] = b"ENDPOINT_MARKER"

    if scenario == "invalid_local":
        (generation / "appdb.dump").write_bytes(b"PRIVATE_PATH_MARKER")
    elif scenario == "transport":
        store.failed_put_keys.add(dump_key)
    elif scenario == "collision":
        store.objects[dump_key] = b"SECRET_MARKER"
    else:
        store.after_put = corrupt_manifest

    with pytest.raises(r2_publish.RecoveryPublishError) as raised:
        r2_publish.publish_verified_generation(
            client=store,
            generation_dir=generation,
            verification_root=tmp_path,
        )

    rendered = str(raised.value)
    for marker in (
        "SECRET_MARKER",
        "ENDPOINT_MARKER",
        "PRIVATE_PATH_MARKER",
        str(tmp_path),
    ):
        assert marker not in rendered
