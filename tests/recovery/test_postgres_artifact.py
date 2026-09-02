from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from recovery import postgres_artifact


class FakePgDump:
    def __init__(self, *, payload: bytes | None, returncode: int = 0) -> None:
        self.payload = payload
        self.returncode = returncode
        self.argv: list[str] | None = None

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[object]:
        self.argv = argv
        output_arg = next(item for item in argv if item.startswith("--file="))
        if self.payload is not None:
            Path(output_arg.removeprefix("--file=")).write_bytes(self.payload)
        return subprocess.CompletedProcess(argv, self.returncode)


def fixed_clock() -> object:
    values = iter(
        [
            datetime(2026, 9, 2, 1, 2, 3, tzinfo=UTC),
            datetime(2026, 9, 2, 1, 2, 4, tzinfo=UTC),
        ]
    )
    return lambda: next(values)


def create_valid_generation(tmp_path: Path) -> tuple[Path, FakePgDump]:
    fake = FakePgDump(payload=b"custom-format-bytes")
    generation = postgres_artifact.create_generation(
        root=tmp_path,
        database_logical_name="app-db/production",
        generation_id="20260902T010203Z",
        now=fixed_clock(),  # type: ignore[arg-type]
        process_runner=fake,
    )
    return generation, fake


def test_success_creates_verified_three_file_generation_with_deterministic_metadata(
    tmp_path: Path,
) -> None:
    generation, fake = create_valid_generation(tmp_path)

    assert sorted(path.name for path in generation.iterdir()) == [
        "app-db-production.dump",
        "app-db-production.dump.sha256",
        "manifest.json",
    ]
    manifest = json.loads((generation / "manifest.json").read_text())
    assert manifest == {
        "checksum_algorithm": "sha256",
        "checksum_value": "685ace2ca7a4e51bfa9785a63304b66634a4b1b1e5e02d6688c77a1a133d4a16",
        "completed_at_utc": "2026-09-02T01:02:04Z",
        "contract_version": "postgres-recovery-artifact/v1",
        "created_at_utc": "2026-09-02T01:02:03Z",
        "database_logical_name": "app-db/production",
        "dump_filename": "app-db-production.dump",
        "dump_format": "custom",
        "dump_size_bytes": 19,
        "generation_id": "20260902T010203Z",
        "generator": "recovery.postgres_artifact",
        "verification_status": "PASS",
    }
    assert postgres_artifact.verify_generation(generation).passed
    assert fake.argv == [
        "pg_dump",
        "--format=custom",
        "--no-password",
        f"--file={tmp_path / 'staging' / '20260902T010203Z' / 'app-db-production.dump'}",
        "--dbname=app-db/production",
    ]


@pytest.mark.parametrize(
    ("payload", "returncode"),
    [(b"partial", 1), (None, 0), (b"", 0)],
)
def test_failed_or_invalid_pg_dump_never_creates_completed_generation(
    tmp_path: Path, payload: bytes | None, returncode: int
) -> None:
    with pytest.raises(postgres_artifact.GenerationError):
        postgres_artifact.create_generation(
            root=tmp_path,
            database_logical_name="appdb",
            generation_id="generation-1",
            process_runner=FakePgDump(payload=payload, returncode=returncode),
        )

    assert not (tmp_path / "completed" / "generation-1").exists()


@pytest.mark.parametrize(
    "fault", ["tamper", "missing_dump", "missing_checksum", "missing_manifest"]
)
def test_verify_rejects_tampered_or_missing_required_files(tmp_path: Path, fault: str) -> None:
    generation, _ = create_valid_generation(tmp_path)
    dump = generation / "app-db-production.dump"
    if fault == "tamper":
        dump.write_bytes(b"altered")
    elif fault == "missing_dump":
        dump.unlink()
    elif fault == "missing_checksum":
        (generation / "app-db-production.dump.sha256").unlink()
    else:
        (generation / "manifest.json").unlink()

    assert not postgres_artifact.verify_generation(generation).passed


@pytest.mark.parametrize("fault", ["checksum", "checksum_file", "size", "filename"])
def test_verify_rejects_checksum_or_manifest_inconsistency(tmp_path: Path, fault: str) -> None:
    generation, _ = create_valid_generation(tmp_path)
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if fault == "checksum":
        manifest["checksum_value"] = "0" * 64
    elif fault == "checksum_file":
        (generation / "app-db-production.dump.sha256").write_text("0" * 64 + "\n")
    elif fault == "size":
        manifest["dump_size_bytes"] += 1
    else:
        manifest["dump_filename"] = "other.dump"
    manifest_path.write_text(json.dumps(manifest))

    assert not postgres_artifact.verify_generation(generation).passed


def test_generation_collision_does_not_overwrite_completed_generation(tmp_path: Path) -> None:
    generation, _ = create_valid_generation(tmp_path)
    original_dump = (generation / "app-db-production.dump").read_bytes()

    with pytest.raises(postgres_artifact.GenerationError, match="already exists"):
        postgres_artifact.create_generation(
            root=tmp_path,
            database_logical_name="app-db/production",
            generation_id="20260902T010203Z",
            process_runner=FakePgDump(payload=b"replacement"),
        )

    assert (generation / "app-db-production.dump").read_bytes() == original_dump


def test_pg_dump_argv_is_shell_safe_and_does_not_accept_connection_uri_or_credentials(
    tmp_path: Path,
) -> None:
    fake = FakePgDump(payload=b"safe")
    postgres_artifact.create_generation(
        root=tmp_path,
        database_logical_name="logical-db",
        generation_id="safe-generation",
        process_runner=fake,
    )

    assert fake.argv is not None
    assert isinstance(fake.argv, list)
    assert "--no-password" in fake.argv
    assert not any("password" in item.lower() and item != "--no-password" for item in fake.argv)
    assert not any("://" in item for item in fake.argv)
    assert "shell" not in postgres_artifact._run_pg_dump.__code__.co_names
    parser_options = {action.dest for action in postgres_artifact.build_parser()._actions}
    assert "password" not in parser_options

    manifest_text = (tmp_path / "completed" / "safe-generation" / "manifest.json").read_text()
    for forbidden in ("postgresql://", "password", str(tmp_path), "r2", "bucket"):
        assert forbidden not in manifest_text.lower()

    with pytest.raises(ValueError, match="connection URI"):
        postgres_artifact.create_generation(
            root=tmp_path,
            database_logical_name="postgresql://user:secret@private-host/appdb",
            generation_id="reject-uri",
            process_runner=fake,
        )


def test_cli_parser_opens_without_external_connection() -> None:
    parser = postgres_artifact.build_parser()
    assert parser.parse_args(["verify", "local-generation"]).command == "verify"
