"""Create and verify local PostgreSQL logical recovery artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "postgres-recovery-artifact/v1"
GENERATOR = "recovery.postgres_artifact"
COMPLETED_DIRNAME = "completed"
STAGING_DIRNAME = "staging"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class GenerationError(RuntimeError):
    """Raised when a recovery generation cannot be safely completed."""


@dataclass(frozen=True)
class VerificationResult:
    """The portable local verification result for one completed generation."""

    passed: bool
    errors: tuple[str, ...] = ()


ProcessRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[Any]]


def safe_database_filename(database_logical_name: str) -> str:
    """Return a non-empty filename component for a logical database identity."""

    if "://" in database_logical_name:
        raise ValueError("database_logical_name must not be a connection URI")
    sanitized = _SAFE_NAME.sub("-", database_logical_name.strip()).strip(".-")
    if not sanitized:
        raise ValueError("database_logical_name must contain a safe filename character")
    return sanitized


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_pg_dump(argv: Sequence[str]) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(argv, check=False)


def _manifest_path(generation_dir: Path) -> Path:
    return generation_dir / "manifest.json"


def _read_manifest(generation_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_manifest_path(generation_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("manifest is missing or invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    return payload


def verify_generation(generation_dir: Path) -> VerificationResult:
    """Verify a completed local generation without any storage-service dependency."""

    errors: list[str] = []
    if not generation_dir.is_dir():
        return VerificationResult(False, ("generation directory is missing",))

    try:
        manifest = _read_manifest(generation_dir)
    except ValueError as exc:
        return VerificationResult(False, (str(exc),))

    required = {
        "contract_version",
        "generation_id",
        "created_at_utc",
        "completed_at_utc",
        "database_logical_name",
        "dump_filename",
        "dump_format",
        "dump_size_bytes",
        "checksum_algorithm",
        "checksum_value",
        "verification_status",
        "generator",
    }
    missing = sorted(required - manifest.keys())
    if missing:
        errors.append("manifest missing fields: " + ", ".join(missing))
    if manifest.get("contract_version") != CONTRACT_VERSION:
        errors.append("unsupported contract version")
    if manifest.get("dump_format") != "custom":
        errors.append("dump format is not custom")
    if manifest.get("checksum_algorithm") != "sha256":
        errors.append("checksum algorithm is not sha256")
    if manifest.get("verification_status") != "PASS":
        errors.append("verification status is not PASS")
    if manifest.get("generator") != GENERATOR:
        errors.append("unexpected generator")
    if manifest.get("generation_id") != generation_dir.name:
        errors.append("generation identifier does not match directory")
    database_logical_name = manifest.get("database_logical_name")
    if not isinstance(database_logical_name, str):
        errors.append("database logical name is invalid")
    else:
        try:
            expected_filename = f"{safe_database_filename(database_logical_name)}.dump"
        except ValueError:
            errors.append("database logical name is invalid")
        else:
            if manifest.get("dump_filename") != expected_filename:
                errors.append("dump filename does not match database logical name")

    filename = manifest.get("dump_filename")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not filename.endswith(".dump")
    ):
        errors.append("dump filename is not a safe relative dump filename")
        return VerificationResult(False, tuple(errors))
    dump_path = generation_dir / filename
    checksum_path = generation_dir / f"{filename}.sha256"
    if not dump_path.is_file():
        errors.append("dump is missing")
    elif dump_path.stat().st_size == 0:
        errors.append("dump is empty")
    if not checksum_path.is_file():
        errors.append("checksum is missing")

    if errors:
        return VerificationResult(False, tuple(errors))

    size = dump_path.stat().st_size
    if manifest.get("dump_size_bytes") != size:
        errors.append("dump size does not match manifest")
    actual_checksum = _sha256(dump_path)
    if manifest.get("checksum_value") != actual_checksum:
        errors.append("dump checksum does not match manifest")
    try:
        checksum_value = checksum_path.read_text(encoding="ascii").strip()
    except OSError:
        checksum_value = ""
    if checksum_value != actual_checksum:
        errors.append("checksum file does not match dump")
    return VerificationResult(not errors, tuple(errors))


def create_generation(
    *,
    root: Path,
    database_logical_name: str,
    generation_id: str,
    now: Callable[[], datetime] | None = None,
    pg_dump_executable: str = "pg_dump",
    process_runner: ProcessRunner = _run_pg_dump,
) -> Path:
    """Create one verified custom-format dump and atomically finalize it locally."""

    if not generation_id or Path(generation_id).name != generation_id:
        raise ValueError("generation_id must be a single path component")
    safe_name = safe_database_filename(database_logical_name)
    root = Path(root)
    completed_dir = root / COMPLETED_DIRNAME / generation_id
    staging_dir = root / STAGING_DIRNAME / generation_id
    if completed_dir.exists():
        raise GenerationError(f"completed generation already exists: {generation_id}")
    if staging_dir.exists():
        raise GenerationError(f"staging generation already exists: {generation_id}")
    started_at = (now or (lambda: datetime.now(UTC)))()
    staging_dir.mkdir(parents=True)
    dump_filename = f"{safe_name}.dump"
    dump_path = staging_dir / dump_filename
    argv = [
        pg_dump_executable,
        "--format=custom",
        "--no-password",
        f"--file={dump_path}",
        f"--dbname={database_logical_name}",
    ]
    completed = process_runner(argv)
    if completed.returncode != 0:
        raise GenerationError(f"pg_dump failed with exit code {completed.returncode}")
    if not dump_path.is_file() or dump_path.stat().st_size == 0:
        raise GenerationError("pg_dump did not produce a non-empty dump")

    checksum = _sha256(dump_path)
    checksum_path = staging_dir / f"{dump_filename}.sha256"
    checksum_path.write_text(checksum + "\n", encoding="ascii")
    if _sha256(dump_path) != checksum:
        raise GenerationError("dump checksum changed during generation")
    completed_at = (now or (lambda: datetime.now(UTC)))()
    manifest = {
        "checksum_algorithm": "sha256",
        "checksum_value": checksum,
        "completed_at_utc": _format_utc(completed_at),
        "contract_version": CONTRACT_VERSION,
        "created_at_utc": _format_utc(started_at),
        "database_logical_name": database_logical_name,
        "dump_filename": dump_filename,
        "dump_format": "custom",
        "dump_size_bytes": dump_path.stat().st_size,
        "generation_id": generation_id,
        "generator": GENERATOR,
        "verification_status": "PASS",
    }
    _manifest_path(staging_dir).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verification = verify_generation(staging_dir)
    if not verification.passed:
        raise GenerationError("staging verification failed: " + "; ".join(verification.errors))

    completed_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(staging_dir, completed_dir)
    except FileExistsError as exc:
        raise GenerationError(f"completed generation already exists: {generation_id}") from exc
    return completed_dir


def build_parser() -> argparse.ArgumentParser:
    """Build the narrow local recovery artifact CLI."""

    parser = argparse.ArgumentParser(
        description="Create or verify local PostgreSQL recovery artifacts"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create one verified local generation")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--database-logical-name", required=True)
    create.add_argument("--generation-id", required=True)
    create.add_argument("--pg-dump-executable", default="pg_dump")
    verify = commands.add_parser("verify", help="verify an existing completed generation")
    verify.add_argument("generation_dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local-only recovery artifact CLI."""

    args = build_parser().parse_args(argv)
    if args.command == "create":
        generation = create_generation(
            root=args.root,
            database_logical_name=args.database_logical_name,
            generation_id=args.generation_id,
            pg_dump_executable=args.pg_dump_executable,
        )
        print(generation)
        return 0
    result = verify_generation(args.generation_dir)
    if result.passed:
        print("PASS")
        return 0
    print("FAIL: " + "; ".join(result.errors))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
