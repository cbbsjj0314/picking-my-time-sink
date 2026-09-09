from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from recovery import postgres_artifact, r2_materialize, r2_publish
from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
)

Failure = r2_materialize.RecoveryMaterializationFailure
Error = r2_materialize.RecoveryMaterializationError
GENERATION_ID = "synthetic-generation-001"
BASE_KEY = f"postgres-recovery/v1/{GENERATION_ID}"
MANIFEST_KEY = f"{BASE_KEY}/manifest.json"
CHECKSUM_KEY = f"{BASE_KEY}/appdb.dump.sha256"
DUMP_KEY = f"{BASE_KEY}/appdb.dump"
PRIVATE_MARKER = "SYNTHETIC_SECRET_ENDPOINT_BUCKET_PRIVATE_PATH"


def recovery_environment() -> dict[str, str]:
    return {
        "PMTS_RECOVERY_R2_ENDPOINT_URL": "https://synthetic-account.r2.cloudflarestorage.com",
        "PMTS_RECOVERY_R2_BUCKET": "synthetic-recovery-bucket",
        "PMTS_RECOVERY_R2_REGION": "auto",
        "PMTS_RECOVERY_R2_ACCESS_KEY_ID": "SYNTHETIC_ACCESS_KEY",
        "PMTS_RECOVERY_R2_SECRET_ACCESS_KEY": "SYNTHETIC_SECRET_KEY",
        "PMTS_RECOVERY_R2_KEY_PREFIX": "synthetic/prefix",
    }


class FakeResponse:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self.body = BytesIO(payload)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        assert size > 0, "artifact responses must use bounded reads"
        self.read_sizes.append(size)
        return self.body.read(size)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.body.close()


class RemoteFixture:
    """Remote bytes only: no local A1 directory or publisher seeds this fixture."""

    def __init__(self) -> None:
        dump = b"synthetic-custom-dump-payload"
        checksum = hashlib.sha256(dump).hexdigest()
        self.manifest: dict[str, object] = {
            "checksum_algorithm": "sha256",
            "checksum_value": checksum,
            "completed_at_utc": "2026-09-06T01:02:04Z",
            "contract_version": "postgres-recovery-artifact/v1",
            "created_at_utc": "2026-09-06T01:02:03Z",
            "database_logical_name": "appdb",
            "dump_filename": "appdb.dump",
            "dump_format": "custom",
            "dump_size_bytes": len(dump),
            "generation_id": GENERATION_ID,
            "generator": "recovery.postgres_artifact",
            "verification_status": "PASS",
        }
        self.objects = {
            MANIFEST_KEY: json.dumps(self.manifest).encode(),
            CHECKSUM_KEY: (checksum + "\n").encode("ascii"),
            DUMP_KEY: dump,
        }
        self.calls: list[tuple[str, str]] = []
        self.responses: dict[str, FakeResponse] = {}
        self.before_get: Callable[[str], None] | None = None
        self.factory_calls = 0
        self.config = S3CompatibleObjectStoreConfig(
            endpoint_url="https://synthetic-account.r2.cloudflarestorage.com",
            bucket="synthetic-recovery-bucket",
            region="auto",
            access_key_id="SYNTHETIC_ACCESS_KEY",
            secret_access_key="SYNTHETIC_SECRET_KEY",
            key_prefix="synthetic/prefix",
        )
        self.client = self.factory(self.config)
        self.factory_calls = 0

    def factory(self, config: S3CompatibleObjectStoreConfig) -> S3CompatibleObjectStoreClient:
        self.factory_calls += 1
        self.config = config
        return S3CompatibleObjectStoreClient(config, transport=self.transport)

    def transport(self, request: Request, *, context: object) -> FakeResponse:
        del context
        prefix = f"{self.config.endpoint_url}/{self.config.bucket}/{self.config.key_prefix}/"
        assert request.full_url.startswith(prefix)
        key = request.full_url.removeprefix(prefix)
        self.calls.append((request.get_method(), key))
        assert request.get_method() == "GET", "remote mutation or discovery is forbidden"
        if self.before_get is not None:
            self.before_get(key)
        if key not in self.objects:
            raise HTTPError(request.full_url, 404, PRIVATE_MARKER, None, BytesIO(b"private body"))
        response = FakeResponse(self.objects[key])
        self.responses[key] = response
        return response

    def update_manifest(self, **changes: object) -> None:
        self.manifest.update(changes)
        self.objects[MANIFEST_KEY] = json.dumps(self.manifest).encode()


def materialize(
    remote: RemoteFixture, destination: Path
) -> r2_materialize.MaterializedRemoteGeneration:
    return r2_materialize.materialize_remote_generation(
        client=remote.client, generation_id=GENERATION_ID, destination=destination
    )


def argv(destination: Path) -> list[str]:
    return ["--generation-id", GENERATION_ID, "--destination", str(destination)]


def assert_incomplete(destination: Path) -> None:
    assert not (destination / "completed" / GENERATION_ID).exists()
    assert (destination / "staging" / GENERATION_ID).is_dir()


def test_retains_remote_only_three_file_generation_and_uses_bounded_gets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = RemoteFixture()
    before = dict(remote.objects)
    destination = tmp_path / "fresh"
    verified_paths: list[Path] = []
    original_verify = postgres_artifact.verify_generation
    original_read = Path.read_bytes

    def verify(path: Path) -> postgres_artifact.VerificationResult:
        verified_paths.append(path)
        return original_verify(path)

    def reject_dump_read_bytes(path: Path) -> bytes:
        assert path.suffix != ".dump", "dump must not be loaded wholly into memory"
        return original_read(path)

    def reject_local_source(**_: object) -> None:
        raise AssertionError("local reference or publish path must not be used")

    monkeypatch.setattr(postgres_artifact, "verify_generation", verify)
    monkeypatch.setattr(Path, "read_bytes", reject_dump_read_bytes)
    monkeypatch.setattr(r2_publish, "verify_remote_generation", reject_local_source)
    monkeypatch.setattr(r2_publish, "publish_verified_generation", reject_local_source)
    result = materialize(remote, destination)

    assert result.verified
    assert result.generation_id == GENERATION_ID
    assert result.generation_dir == destination / "completed" / GENERATION_ID
    assert verified_paths == [destination / "staging" / GENERATION_ID]
    assert original_verify(result.generation_dir).passed
    assert sorted(p.name for p in result.generation_dir.iterdir()) == [
        "appdb.dump",
        "appdb.dump.sha256",
        "manifest.json",
    ]
    with (result.generation_dir / "appdb.dump").open("rb") as handle:
        assert handle.read() == before[DUMP_KEY]
    assert not list((destination / "staging").iterdir())
    assert destination.stat().st_mode & 0o777 == 0o700
    assert remote.objects == before
    assert remote.calls == [("GET", key) for key in (MANIFEST_KEY, CHECKSUM_KEY, DUMP_KEY)]
    assert remote.responses[MANIFEST_KEY].read_sizes == [r2_publish._MANIFEST_MAX_BYTES + 1]
    assert remote.responses[CHECKSUM_KEY].read_sizes == [r2_publish._CHECKSUM_MAX_BYTES + 1]
    assert remote.responses[DUMP_KEY].read_sizes == [r2_publish._TRANSFER_CHUNK_BYTES] * 2


@pytest.mark.parametrize("generation_id", ["", "../escape", "a/b", ".", "..", "a\n", "a" * 129, 1])
def test_invalid_identity_makes_no_remote_or_local_changes(
    tmp_path: Path, generation_id: str
) -> None:
    remote = RemoteFixture()
    with pytest.raises(Error, match="invalid_arguments"):
        r2_materialize.materialize_remote_generation(
            client=remote.client, generation_id=generation_id, destination=tmp_path / "fresh"
        )
    assert remote.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("payload", [b"{", b"[]", b"null", b"\xff", b"[" * 2000])
def test_malformed_manifest_is_rejected(tmp_path: Path, payload: bytes) -> None:
    remote = RemoteFixture()
    remote.objects[MANIFEST_KEY] = payload
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.INVALID_REMOTE_MANIFEST
    assert remote.calls == [("GET", MANIFEST_KEY)]
    assert_incomplete(tmp_path / "fresh")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", "unexpected"),
        ("database_logical_name", "../escape"),
        ("database_logical_name", None),
        ("dump_filename", "other.dump"),
        ("dump_filename", "../appdb.dump"),
        ("dump_filename", "/private/appdb.dump"),
        ("dump_filename", "nested/appdb.dump"),
        ("dump_filename", 1),
        ("dump_size_bytes", 0),
        ("dump_size_bytes", -1),
        ("dump_size_bytes", True),
        ("dump_size_bytes", "27"),
        ("dump_size_bytes", 1.5),
        ("checksum_algorithm", "md5"),
        ("checksum_value", "bad"),
        ("checksum_value", None),
        ("generator", "other"),
        ("dump_format", "plain"),
        ("verification_status", "FAIL"),
    ],
)
def test_manifest_contract_rejected_before_artifact_gets(
    tmp_path: Path, field: str, value: object
) -> None:
    remote = RemoteFixture()
    remote.update_manifest(**{field: value})
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.INVALID_REMOTE_MANIFEST
    assert remote.calls == [("GET", MANIFEST_KEY)]
    assert_incomplete(tmp_path / "fresh")


def test_generation_identity_mismatch_never_expands_remote_keys(tmp_path: Path) -> None:
    remote = RemoteFixture()
    remote.update_manifest(generation_id="different-generation")
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.GENERATION_IDENTITY_MISMATCH
    assert remote.calls == [("GET", MANIFEST_KEY)]


@pytest.mark.parametrize("key", [MANIFEST_KEY, CHECKSUM_KEY, DUMP_KEY])
def test_missing_remote_artifact_is_sanitized_without_retry(tmp_path: Path, key: str) -> None:
    remote = RemoteFixture()
    del remote.objects[key]
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.REMOTE_TRANSPORT_FAILURE
    assert str(raised.value) == "remote_transport_failure"
    assert remote.calls.count(("GET", key)) == 1
    assert_incomplete(tmp_path / "fresh")


@pytest.mark.parametrize("key", [MANIFEST_KEY, CHECKSUM_KEY, DUMP_KEY])
def test_existing_client_enforces_response_limits(tmp_path: Path, key: str) -> None:
    remote = RemoteFixture()
    limit = {
        MANIFEST_KEY: r2_publish._MANIFEST_MAX_BYTES,
        CHECKSUM_KEY: r2_publish._CHECKSUM_MAX_BYTES,
        DUMP_KEY: len(remote.objects[DUMP_KEY]),
    }[key]
    remote.objects[key] = b"x" * (limit + 1)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    # The shared client exposes one unstructured error type for bounds and transport.
    assert raised.value.category == Failure.REMOTE_TRANSPORT_FAILURE
    assert remote.calls[-1] == ("GET", key)
    assert_incomplete(tmp_path / "fresh")


def test_unsupported_declared_size_stops_after_manifest(tmp_path: Path) -> None:
    remote = RemoteFixture()
    remote.update_manifest(dump_size_bytes=r2_publish.MAX_SINGLE_PUT_BYTES + 1)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.UNSUPPORTED_OBJECT_SIZE
    assert remote.calls == [("GET", MANIFEST_KEY)]


@pytest.mark.parametrize("key", [MANIFEST_KEY, CHECKSUM_KEY])
def test_defensive_metadata_bound_even_if_injected_client_ignores_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    remote = RemoteFixture()
    original = remote.client.get_bytes

    def oversized(*, object_key: str, max_bytes: int) -> bytes:
        if object_key == key:
            return b"x" * (max_bytes + 1)
        return original(object_key=object_key, max_bytes=max_bytes)

    monkeypatch.setattr(remote.client, "get_bytes", oversized)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.UNSUPPORTED_OBJECT_SIZE
    assert_incomplete(tmp_path / "fresh")


@pytest.mark.parametrize("fault", ["truncated", "empty", "checksum", "non_ascii_checksum", "dump"])
def test_integrity_failures_cannot_be_promoted(tmp_path: Path, fault: str) -> None:
    remote = RemoteFixture()
    if fault == "truncated":
        remote.objects[DUMP_KEY] = remote.objects[DUMP_KEY][:-1]
    elif fault == "empty":
        remote.objects[DUMP_KEY] = b""
    elif fault == "checksum":
        remote.objects[CHECKSUM_KEY] = b"0" * 64 + b"\n"
    elif fault == "non_ascii_checksum":
        remote.objects[CHECKSUM_KEY] = b"\xff"
    else:
        remote.objects[DUMP_KEY] = b"x" * len(remote.objects[DUMP_KEY])
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category in {
        Failure.CONTENT_VERIFICATION_FAILURE,
        Failure.A1_VERIFICATION_FAILURE,
    }
    assert_incomplete(tmp_path / "fresh")


@pytest.mark.parametrize(
    "fault",
    [
        "timestamp",
        "extra_field",
        "missing_field",
        "forced_fail",
        "exception",
        "identity_after_verify",
    ],
)
def test_final_a1_verification_and_identity_are_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    remote = RemoteFixture()
    original = postgres_artifact.verify_generation
    if fault == "timestamp":
        remote.update_manifest(created_at_utc="invalid")
    elif fault == "extra_field":
        remote.update_manifest(untrusted_path=PRIVATE_MARKER)
    elif fault == "missing_field":
        del remote.manifest["created_at_utc"]
        remote.update_manifest()
    else:

        def verify(path: Path) -> postgres_artifact.VerificationResult:
            if fault == "exception":
                raise RuntimeError(PRIVATE_MARKER)
            if fault == "forced_fail":
                return postgres_artifact.VerificationResult(False, (PRIVATE_MARKER,))
            result = original(path)
            manifest = json.loads((path / "manifest.json").read_text())
            manifest["generation_id"] = "replaced"
            (path / "manifest.json").write_text(json.dumps(manifest))
            return result

        monkeypatch.setattr(postgres_artifact, "verify_generation", verify)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    expected = (
        Failure.GENERATION_IDENTITY_MISMATCH
        if fault == "identity_after_verify"
        else Failure.A1_VERIFICATION_FAILURE
    )
    assert raised.value.category == expected
    assert PRIVATE_MARKER not in str(raised.value)
    assert_incomplete(tmp_path / "fresh")


@pytest.mark.parametrize(
    "kind", ["empty_dir", "nonempty_dir", "file", "symlink", "dangling_symlink"]
)
def test_existing_destination_is_never_overwritten_or_read_remotely(
    tmp_path: Path, kind: str
) -> None:
    remote = RemoteFixture()
    destination = tmp_path / "existing"
    protected = tmp_path / "protected"
    protected.mkdir()
    (protected / "marker").write_bytes(b"preserve")
    if kind in {"empty_dir", "nonempty_dir"}:
        destination.mkdir()
        if kind == "nonempty_dir":
            (destination / "marker").write_bytes(b"preserve")
    elif kind == "file":
        destination.write_bytes(b"preserve")
    else:
        destination.symlink_to(protected if kind == "symlink" else tmp_path / "missing")
    with pytest.raises(Error) as raised:
        materialize(remote, destination)
    assert raised.value.category == Failure.DESTINATION_COLLISION
    assert remote.calls == []
    assert (protected / "marker").read_bytes() == b"preserve"
    if kind == "file":
        assert destination.read_bytes() == b"preserve"
    if kind == "nonempty_dir":
        assert (destination / "marker").read_bytes() == b"preserve"
    if "symlink" in kind:
        assert destination.is_symlink()


def test_missing_parent_is_not_created(tmp_path: Path) -> None:
    remote = RemoteFixture()
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "missing" / "fresh")
    assert raised.value.category == Failure.INVALID_DESTINATION
    assert not list(tmp_path.iterdir())
    assert remote.calls == []


@pytest.mark.parametrize("kind", ["empty_dir", "nonempty_dir", "file", "symlink"])
def test_atomic_promotion_rejects_late_collision(tmp_path: Path, kind: str) -> None:
    remote = RemoteFixture()
    destination = tmp_path / "fresh"
    completed = destination / "completed" / GENERATION_ID

    def collision(key: str) -> None:
        if key != DUMP_KEY:
            return
        if kind in {"empty_dir", "nonempty_dir"}:
            completed.mkdir()
            if kind == "nonempty_dir":
                (completed / "marker").write_bytes(b"preserve")
        elif kind == "file":
            completed.write_bytes(b"preserve")
        else:
            completed.symlink_to(tmp_path / "absent")

    remote.before_get = collision
    with pytest.raises(Error) as raised:
        materialize(remote, destination)
    assert raised.value.category == Failure.DESTINATION_COLLISION
    assert postgres_artifact.verify_generation(destination / "staging" / GENERATION_ID).passed
    if kind == "empty_dir":
        assert list(completed.iterdir()) == []
    elif kind == "nonempty_dir":
        assert (completed / "marker").read_bytes() == b"preserve"
    elif kind == "file":
        assert completed.read_bytes() == b"preserve"
    else:
        assert completed.is_symlink()


def test_existing_dump_file_is_not_overwritten(tmp_path: Path) -> None:
    remote = RemoteFixture()
    destination = tmp_path / "fresh"
    dump = destination / "staging" / GENERATION_ID / "appdb.dump"

    def collision(key: str) -> None:
        if key == DUMP_KEY:
            dump.write_bytes(b"preserve")

    remote.before_get = collision
    with pytest.raises(Error) as raised:
        materialize(remote, destination)
    assert raised.value.category == Failure.DESTINATION_COLLISION
    assert dump.read_bytes() == b"preserve"
    assert_incomplete(destination)


@pytest.mark.parametrize("filename", ["manifest.json", "appdb.dump.sha256"])
def test_existing_metadata_file_is_not_overwritten(tmp_path: Path, filename: str) -> None:
    remote = RemoteFixture()
    destination = tmp_path / "fresh"
    artifact = destination / "staging" / GENERATION_ID / filename

    def collision(key: str) -> None:
        if key == CHECKSUM_KEY:
            artifact.write_bytes(b"preserve")

    remote.before_get = collision
    with pytest.raises(Error) as raised:
        materialize(remote, destination)
    assert raised.value.category == Failure.DESTINATION_COLLISION
    assert artifact.read_bytes() == b"preserve"
    assert ("GET", DUMP_KEY) not in remote.calls
    assert_incomplete(destination)


@pytest.mark.parametrize("fault", ["oversized", "symlink", "extra_file"])
def test_unexpected_local_transfer_result_is_never_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    remote = RemoteFixture()

    def unexpected(*, destination_path: Path, max_bytes: int, **_: object) -> None:
        if fault == "symlink":
            destination_path.symlink_to(tmp_path / "absent")
        else:
            destination_path.write_bytes(b"x" * (max_bytes + (fault == "oversized")))
            if fault == "extra_file":
                (destination_path.parent / "extra").write_bytes(b"unverified")

    monkeypatch.setattr(remote.client, "get_file", unexpected)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == (
        Failure.UNSUPPORTED_OBJECT_SIZE
        if fault == "oversized"
        else Failure.CONTENT_VERIFICATION_FAILURE
    )
    assert_incomplete(tmp_path / "fresh")


def test_partial_transfer_is_retained_and_reinvocation_does_not_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = RemoteFixture()
    destination = tmp_path / "fresh"

    def fail(*, destination_path: Path, **_: object) -> None:
        with destination_path.open("xb") as handle:
            handle.write(b"partial")
        raise RuntimeError(PRIVATE_MARKER)

    monkeypatch.setattr(remote.client, "get_file", fail)
    with pytest.raises(Error, match="remote_transport_failure"):
        materialize(remote, destination)
    assert_incomplete(destination)
    staging = destination / "staging" / GENERATION_ID
    before = {p.name: p.read_bytes() for p in staging.iterdir()}
    calls = list(remote.calls)
    with pytest.raises(Error, match="destination_collision"):
        materialize(remote, destination)
    assert {p.name: p.read_bytes() for p in staging.iterdir()} == before
    assert before["appdb.dump"] == b"partial"
    assert remote.calls == calls


def test_local_write_failure_is_sanitized_and_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = RemoteFixture()
    original = Path.open

    def fail(path: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        if path.name == "manifest.json" and mode == "xb":
            raise OSError(PRIVATE_MARKER)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.LOCAL_MATERIALIZATION_FAILURE
    assert PRIVATE_MARKER not in str(raised.value)
    assert_incomplete(tmp_path / "fresh")


def test_no_replace_failure_has_no_fallback_or_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = RemoteFixture()

    def fail(*_: object) -> None:
        raise postgres_artifact.GenerationError(PRIVATE_MARKER)

    monkeypatch.setattr(postgres_artifact, "_rename_no_replace", fail)
    with pytest.raises(Error) as raised:
        materialize(remote, tmp_path / "fresh")
    assert raised.value.category == Failure.LOCAL_MATERIALIZATION_FAILURE
    assert_incomplete(tmp_path / "fresh")


def test_cli_success_reports_only_safe_identity_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    remote = RemoteFixture()
    assert (
        r2_materialize.main(
            argv(tmp_path / "private-root"),
            environ=recovery_environment(),
            client_factory=remote.factory,
        )
        == 0
    )
    captured = capsys.readouterr()
    assert (
        captured.out
        == f"generation={GENERATION_ID}\nlocal_verification=PASS\nmaterialization=PASS\n"
    )
    assert captured.err == ""
    assert postgres_artifact.verify_generation(
        tmp_path / "private-root" / "completed" / GENERATION_ID
    ).passed


@pytest.mark.parametrize(
    "args", [[], ["--bad", PRIVATE_MARKER], ["--generation-id", PRIVATE_MARKER]]
)
def test_cli_argument_errors_never_echo_input(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    remote = RemoteFixture()
    assert r2_materialize.main(args, environ={}, client_factory=remote.factory) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: recovery materialization failed: invalid_arguments\n"
    assert remote.factory_calls == 0


@pytest.mark.parametrize(
    "fault", ["config", "provider", "unexpected_transport", "factory", "internal"]
)
def test_cli_errors_never_expose_provider_secret_path_or_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    remote = RemoteFixture()
    environment = recovery_environment()
    marker = " ".join([PRIVATE_MARKER, str(tmp_path), *environment.values()])

    def fail(*_: object, **__: object) -> None:
        raise RuntimeError(marker)

    def fail_get(key: str) -> None:
        if fault == "provider":
            raise HTTPError(
                "https://synthetic.invalid", 403, marker, None, BytesIO(marker.encode())
            )
        fail()

    factory = remote.factory
    if fault == "config":
        del environment["PMTS_RECOVERY_R2_REGION"]
    elif fault in {"provider", "unexpected_transport"}:
        remote.before_get = fail_get
    elif fault == "factory":
        factory = fail
    else:
        monkeypatch.setattr(r2_materialize, "materialize_remote_generation", fail)
    assert (
        r2_materialize.main(argv(tmp_path / "fresh"), environ=environment, client_factory=factory)
        == 1
    )
    captured = capsys.readouterr()
    category = (
        "invalid_config"
        if fault == "config"
        else (
            "remote_transport_failure"
            if fault in {"provider", "unexpected_transport"}
            else "internal_error"
        )
    )
    assert captured.out == ""
    assert captured.err == f"ERROR: recovery materialization failed: {category}\n"
    for forbidden in [PRIVATE_MARKER, str(tmp_path), "Traceback", *environment.values()]:
        assert forbidden not in captured.out + captured.err


def test_cli_help_describes_freshness_retention_and_gate_without_config_or_client(
    capsys: pytest.CaptureFixture[str],
) -> None:
    remote = RemoteFixture()
    with pytest.raises(SystemExit) as raised:
        r2_materialize.main(["--help"], environ={}, client_factory=remote.factory)
    assert raised.value.code == 0
    output = capsys.readouterr().out
    for text in [
        "--generation-id",
        "--destination",
        "completed/",
        "staging/",
        "Human Gate",
        "cleanup",
    ]:
        assert text in output
    assert remote.factory_calls == 0
    assert remote.calls == []


@pytest.mark.parametrize("fault", ["unverified", "wrong_id", "wrong_path"])
def test_cli_rechecks_success_result_identity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    remote = RemoteFixture()
    monkeypatch.setattr(
        r2_materialize,
        "materialize_remote_generation",
        lambda **_: r2_materialize.MaterializedRemoteGeneration(
            generation_id="other" if fault == "wrong_id" else GENERATION_ID,
            generation_dir=tmp_path / ("other" if fault == "wrong_path" else GENERATION_ID),
            verified=fault != "unverified",
        ),
    )
    assert (
        r2_materialize.main(
            argv(tmp_path / "fresh"), environ=recovery_environment(), client_factory=remote.factory
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: recovery materialization failed: generation_identity_mismatch\n"


@pytest.mark.parametrize("excess", [0, 1])
def test_cli_bounds_prefix_before_client_creation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], excess: int
) -> None:
    remote = RemoteFixture()
    environment = recovery_environment()
    longest_key = f"{BASE_KEY}/{'a' * 63}.dump.sha256"
    length = 1024 - len(longest_key) - 1 + excess
    environment["PMTS_RECOVERY_R2_KEY_PREFIX"] = "한" * (length // 3) + "a" * (length % 3)
    # A multibyte over-limit prefix must fail before constructing the client.
    if not excess:
        environment["PMTS_RECOVERY_R2_KEY_PREFIX"] = "a" * length
    assert (
        r2_materialize.main(
            argv(tmp_path / "fresh"), environ=environment, client_factory=remote.factory
        )
        == excess
    )
    captured = capsys.readouterr()
    if excess:
        assert captured.err == "ERROR: recovery materialization failed: invalid_config\n"
        assert remote.factory_calls == 0
        assert remote.calls == []
        assert not (tmp_path / "fresh").exists()
    else:
        assert remote.factory_calls == 1
