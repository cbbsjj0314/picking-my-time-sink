from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from recovery import r2_activation, r2_publish
from recovery.postgres_artifact import VerificationResult
from steam.ingest.s3_compat import S3CompatibleObjectStoreConfig

SYNTHETIC_ENDPOINT = "https://synthetic-account.r2.cloudflarestorage.com"
SYNTHETIC_BUCKET = "synthetic-recovery-bucket"
SYNTHETIC_ACCESS_KEY = "SYNTHETIC_ACCESS_KEY_MARKER"
SYNTHETIC_SECRET = "SYNTHETIC_SECRET_MARKER"


def recovery_environment(**overrides: str) -> dict[str, str]:
    environ = {
        "PMTS_RECOVERY_R2_ENDPOINT_URL": SYNTHETIC_ENDPOINT,
        "PMTS_RECOVERY_R2_BUCKET": SYNTHETIC_BUCKET,
        "PMTS_RECOVERY_R2_REGION": "auto",
        "PMTS_RECOVERY_R2_ACCESS_KEY_ID": SYNTHETIC_ACCESS_KEY,
        "PMTS_RECOVERY_R2_SECRET_ACCESS_KEY": SYNTHETIC_SECRET,
    }
    environ.update(overrides)
    return environ


def create_valid_generation(tmp_path: Path) -> Path:
    generation = tmp_path / "synthetic-private-root" / "completed" / "generation-001"
    generation.mkdir(parents=True)
    dump = b"synthetic-postgres-custom-dump"
    checksum = hashlib.sha256(dump).hexdigest()
    (generation / "appdb.dump").write_bytes(dump)
    (generation / "appdb.dump.sha256").write_text(checksum + "\n", encoding="ascii")
    manifest = {
        "checksum_algorithm": "sha256",
        "checksum_value": checksum,
        "completed_at_utc": "2026-09-06T01:02:04Z",
        "contract_version": "postgres-recovery-artifact/v1",
        "created_at_utc": "2026-09-06T01:02:03Z",
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


class NoRemoteClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def put_file(self, **_: object) -> None:
        self.calls.append("PUT_FILE")

    def put_bytes(self, **_: object) -> None:
        self.calls.append("PUT_BYTES")

    def get_file(self, **_: object) -> None:
        self.calls.append("GET_FILE")

    def get_bytes(self, **_: object) -> bytes:
        self.calls.append("GET_BYTES")
        return b""


class RecordingClientFactory:
    def __init__(self, client: object) -> None:
        self.client = client
        self.configs: list[S3CompatibleObjectStoreConfig] = []

    def __call__(self, config: S3CompatibleObjectStoreConfig) -> object:
        self.configs.append(config)
        return self.client


def combined_output(captured: pytest.CaptureResult[str]) -> str:
    return captured.out + captured.err


def assert_sensitive_markers_absent(rendered: str, private_path: Path | None = None) -> None:
    for marker in (
        SYNTHETIC_SECRET,
        SYNTHETIC_ACCESS_KEY,
        SYNTHETIC_ENDPOINT,
        SYNTHETIC_BUCKET,
    ):
        assert marker not in rendered
    if private_path is not None:
        assert str(private_path) not in rendered


def test_recovery_config_loads_expected_explicit_s3_config() -> None:
    config = r2_activation.load_recovery_r2_config(
        recovery_environment(PMTS_RECOVERY_R2_KEY_PREFIX=" /team/recovery/ ")
    )

    assert config == S3CompatibleObjectStoreConfig(
        endpoint_url=SYNTHETIC_ENDPOINT,
        bucket=SYNTHETIC_BUCKET,
        region="auto",
        access_key_id=SYNTHETIC_ACCESS_KEY,
        secret_access_key=SYNTHETIC_SECRET,
        session_token=None,
        key_prefix="team/recovery",
        use_path_style=True,
        verify_tls=True,
    )


@pytest.mark.parametrize("prefix", [None, "", " / "])
def test_recovery_config_optional_key_prefix_defaults_to_empty(prefix: str | None) -> None:
    environ = recovery_environment()
    if prefix is not None:
        environ["PMTS_RECOVERY_R2_KEY_PREFIX"] = prefix

    assert r2_activation.load_recovery_r2_config(environ).key_prefix == ""


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PMTS_RECOVERY_R2_ENDPOINT_URL", "http://synthetic.invalid"),
        (
            "PMTS_RECOVERY_R2_ENDPOINT_URL",
            "https://synthetic-account.r2.cloudflarestorage.com/private-path",
        ),
        ("PMTS_RECOVERY_R2_BUCKET", "Synthetic-Bucket"),
        ("PMTS_RECOVERY_R2_REGION", "us-east-1"),
        ("PMTS_RECOVERY_R2_ACCESS_KEY_ID", "synthetic access"),
        ("PMTS_RECOVERY_R2_SECRET_ACCESS_KEY", "synthetic secret"),
        ("PMTS_RECOVERY_R2_KEY_PREFIX", "team//recovery"),
        ("PMTS_RECOVERY_R2_KEY_PREFIX", "team/../recovery"),
        ("PMTS_RECOVERY_R2_KEY_PREFIX", "team\\recovery"),
    ],
)
def test_recovery_config_rejects_malformed_values_without_echoing_them(
    key: str, value: str
) -> None:
    with pytest.raises(r2_activation.RecoveryActivationError) as raised:
        r2_activation.load_recovery_r2_config(recovery_environment(**{key: value}))

    assert raised.value.category == r2_activation.RecoveryActivationFailure.INVALID_CONFIG
    assert str(raised.value) == "invalid_config"
    assert value not in str(raised.value)


@pytest.mark.parametrize(
    "missing_key",
    [
        "PMTS_RECOVERY_R2_ENDPOINT_URL",
        "PMTS_RECOVERY_R2_BUCKET",
        "PMTS_RECOVERY_R2_REGION",
        "PMTS_RECOVERY_R2_ACCESS_KEY_ID",
        "PMTS_RECOVERY_R2_SECRET_ACCESS_KEY",
    ],
)
def test_recovery_config_missing_required_value_fails_closed(missing_key: str) -> None:
    environ = recovery_environment()
    del environ[missing_key]

    with pytest.raises(r2_activation.RecoveryActivationError) as raised:
        r2_activation.load_recovery_r2_config(environ)

    assert raised.value.category == r2_activation.RecoveryActivationFailure.INVALID_CONFIG


def test_recovery_config_never_uses_steam_shared_environment() -> None:
    steam_only = {
        "STEAM_SHARED_S3_ENDPOINT_URL": SYNTHETIC_ENDPOINT,
        "STEAM_SHARED_S3_BUCKET": SYNTHETIC_BUCKET,
        "STEAM_SHARED_S3_REGION": "auto",
        "STEAM_SHARED_S3_ACCESS_KEY_ID": SYNTHETIC_ACCESS_KEY,
        "STEAM_SHARED_S3_SECRET_ACCESS_KEY": SYNTHETIC_SECRET,
    }
    with pytest.raises(r2_activation.RecoveryActivationError):
        r2_activation.load_recovery_r2_config(steam_only)

    environ = recovery_environment()
    environ.update({key: f"ignored-{value}" for key, value in steam_only.items()})
    config = r2_activation.load_recovery_r2_config(environ)
    assert config.endpoint_url == SYNTHETIC_ENDPOINT
    assert config.bucket == SYNTHETIC_BUCKET


def test_preflight_valid_generation_reports_portable_contract(tmp_path: Path) -> None:
    generation = create_valid_generation(tmp_path)

    result = r2_activation.run_preflight(
        generation_dir=generation,
        environ=recovery_environment(),
    )

    base_key = "postgres-recovery/v1/generation-001"
    assert result.generation_id == "generation-001"
    assert result.dump_size_bytes == len(b"synthetic-postgres-custom-dump")
    assert result.object_keys == (
        f"{base_key}/appdb.dump",
        f"{base_key}/appdb.dump.sha256",
        f"{base_key}/manifest.json",
    )


def test_preflight_cli_is_sanitized_and_never_constructs_remote_client(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generation = create_valid_generation(tmp_path)
    remote = NoRemoteClient()
    factory = RecordingClientFactory(remote)

    assert (
        r2_activation.main(
            ["preflight", str(generation)],
            environ=recovery_environment(),
            client_factory=factory,  # type: ignore[arg-type]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert captured.out == (
        "generation=generation-001\n"
        "dump_size_bytes=30\n"
        "local_verification=PASS\n"
        "single_upload_preflight=PASS\n"
        "activation_preflight=PASS\n"
    )
    assert captured.err == ""
    assert factory.configs == []
    assert remote.calls == []
    assert_sensitive_markers_absent(combined_output(captured), generation.parent.parent)


def test_preflight_requires_a1_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = create_valid_generation(tmp_path)
    monkeypatch.setattr(
        r2_activation,
        "verify_generation",
        lambda _: VerificationResult(False, ("synthetic-private-detail",)),
    )

    with pytest.raises(r2_activation.RecoveryActivationError) as raised:
        r2_activation.run_preflight(
            generation_dir=generation,
            environ=recovery_environment(),
        )

    assert raised.value.category == (
        r2_activation.RecoveryActivationFailure.INVALID_LOCAL_GENERATION
    )


@pytest.mark.parametrize("fault", ["missing_directory", "tampered_dump", "missing_checksum"])
def test_invalid_generation_fails_preflight_before_remote_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    generation = create_valid_generation(tmp_path)
    if fault == "missing_directory":
        generation = generation.parent / "missing-generation"
    elif fault == "tampered_dump":
        (generation / "appdb.dump").write_bytes(b"tampered")
    else:
        (generation / "appdb.dump.sha256").unlink()
    remote = NoRemoteClient()
    factory = RecordingClientFactory(remote)

    assert (
        r2_activation.main(
            ["preflight", str(generation)],
            environ=recovery_environment(),
            client_factory=factory,  # type: ignore[arg-type]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "ERROR: recovery R2 activation failed: invalid_local_generation\n"
    )
    assert factory.configs == []
    assert remote.calls == []
    assert_sensitive_markers_absent(combined_output(captured), generation.parent)


def test_preflight_enforces_current_a2_single_put_boundary_before_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generation = create_valid_generation(tmp_path)
    monkeypatch.setattr(r2_publish, "MAX_SINGLE_PUT_BYTES", 1)
    remote = NoRemoteClient()
    factory = RecordingClientFactory(remote)

    assert (
        r2_activation.main(
            ["preflight", str(generation)],
            environ=recovery_environment(),
            client_factory=factory,  # type: ignore[arg-type]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.err == "ERROR: recovery R2 activation failed: unsupported_object_size\n"
    assert factory.configs == []
    assert remote.calls == []


def test_preflight_config_failure_output_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generation = create_valid_generation(tmp_path)
    environ = recovery_environment()
    del environ["PMTS_RECOVERY_R2_REGION"]

    assert r2_activation.main(["preflight", str(generation)], environ=environ) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: recovery R2 activation failed: invalid_config\n"
    assert_sensitive_markers_absent(combined_output(captured), generation.parent.parent)


def test_publish_uses_a2_publisher_and_only_reports_verified_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generation = create_valid_generation(tmp_path)
    remote = NoRemoteClient()
    factory = RecordingClientFactory(remote)
    seen: dict[str, object] = {}

    def fake_a2_publish(**kwargs: object) -> r2_publish.VerifiedRemoteGeneration:
        seen.update(kwargs)
        return r2_publish.VerifiedRemoteGeneration(
            generation_id="generation-001",
            object_keys=("portable-dump", "portable-checksum", "portable-manifest"),
        )

    monkeypatch.setattr(r2_publish, "publish_verified_generation", fake_a2_publish)

    assert (
        r2_activation.main(
            ["publish", str(generation)],
            environ=recovery_environment(),
            client_factory=factory,  # type: ignore[arg-type]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert captured.out == "generation=generation-001\nremote_verification=PASS\n"
    assert captured.err == ""
    assert seen == {"client": remote, "generation_dir": generation}
    assert len(factory.configs) == 1
    assert factory.configs[0].bucket == SYNTHETIC_BUCKET
    assert remote.calls == []
    assert_sensitive_markers_absent(combined_output(captured), generation.parent.parent)


def test_publish_rejects_unverified_a2_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generation = create_valid_generation(tmp_path)
    remote = NoRemoteClient()

    def unverified(**_: object) -> r2_publish.VerifiedRemoteGeneration:
        return r2_publish.VerifiedRemoteGeneration(
            generation_id="generation-001",
            object_keys=("dump", "checksum", "manifest"),
            verified=False,
        )

    assert (
        r2_activation.main(
            ["publish", str(generation)],
            environ=recovery_environment(),
            client_factory=RecordingClientFactory(remote),  # type: ignore[arg-type]
            publisher=unverified,
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "ERROR: recovery R2 activation failed: remote_verification_failure\n"
    )
    assert remote.calls == []


def test_publish_a2_failure_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generation = create_valid_generation(tmp_path)
    remote = NoRemoteClient()

    def fail(**_: object) -> r2_publish.VerifiedRemoteGeneration:
        raise r2_publish.RecoveryPublishError(
            r2_publish.RecoveryPublishFailure.REMOTE_TRANSPORT_FAILURE,
            generation_id="generation-001",
            artifact_role="dump",
        )

    assert (
        r2_activation.main(
            ["publish", str(generation)],
            environ=recovery_environment(),
            client_factory=RecordingClientFactory(remote),  # type: ignore[arg-type]
            publisher=fail,
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: recovery R2 activation failed: remote_transport_failure\n"
    assert_sensitive_markers_absent(combined_output(captured), generation.parent.parent)


def test_publish_hides_unexpected_lower_level_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generation = create_valid_generation(tmp_path)
    remote = NoRemoteClient()

    def fail(**_: object) -> r2_publish.VerifiedRemoteGeneration:
        raise RuntimeError(
            f"Authorization {SYNTHETIC_SECRET} {SYNTHETIC_ACCESS_KEY} "
            f"{SYNTHETIC_ENDPOINT} {SYNTHETIC_BUCKET} {generation.parent.parent}"
        )

    assert (
        r2_activation.main(
            ["publish", str(generation)],
            environ=recovery_environment(),
            client_factory=RecordingClientFactory(remote),  # type: ignore[arg-type]
            publisher=fail,
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: recovery R2 activation failed: internal_error\n"
    assert "Authorization" not in combined_output(captured)
    assert_sensitive_markers_absent(combined_output(captured), generation.parent.parent)


def test_publish_invalid_generation_uses_a2_fail_closed_path_with_zero_remote_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generation = create_valid_generation(tmp_path)
    (generation / "appdb.dump").write_bytes(b"tampered")
    remote = NoRemoteClient()

    assert (
        r2_activation.main(
            ["publish", str(generation)],
            environ=recovery_environment(),
            client_factory=RecordingClientFactory(remote),  # type: ignore[arg-type]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.err == "ERROR: recovery R2 activation failed: invalid_local_generation\n"
    assert remote.calls == []


def test_loader_and_preflight_do_not_construct_or_call_transport(tmp_path: Path) -> None:
    generation = create_valid_generation(tmp_path)
    remote = NoRemoteClient()
    factory = RecordingClientFactory(remote)
    environ: Mapping[str, str] = recovery_environment()

    r2_activation.load_recovery_r2_config(environ)
    r2_activation.run_preflight(generation_dir=generation, environ=environ)

    assert factory.configs == []
    assert remote.calls == []
