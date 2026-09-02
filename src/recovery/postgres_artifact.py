"""Create and verify local PostgreSQL logical recovery artifacts."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "postgres-recovery-artifact/v1"
GENERATOR = "recovery.postgres_artifact"
COMPLETED_DIRNAME = "completed"
STAGING_DIRNAME = "staging"
_DATABASE_LOGICAL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")
_GENERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MANIFEST_FIELDS = frozenset(
    {
        "checksum_algorithm",
        "checksum_value",
        "completed_at_utc",
        "contract_version",
        "created_at_utc",
        "database_logical_name",
        "dump_filename",
        "dump_format",
        "dump_size_bytes",
        "generation_id",
        "generator",
        "verification_status",
    }
)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class GenerationError(RuntimeError):
    """Raised when a recovery generation cannot be safely completed."""


@dataclass(frozen=True)
class VerificationResult:
    """The portable local verification result for one completed generation."""

    passed: bool
    errors: tuple[str, ...] = ()


ProcessRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[Any]]


def safe_database_filename(database_logical_name: str) -> str:
    """Return a non-empty filename component for a logical database identity."""

    if not _DATABASE_LOGICAL_NAME.fullmatch(database_logical_name):
        raise ValueError("database_logical_name must be a plain database selector")
    return database_logical_name


def _validate_generation_id(generation_id: object) -> bool:
    return isinstance(generation_id, str) and _GENERATION_ID.fullmatch(generation_id) is not None


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or _UTC_TIMESTAMP.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_pg_dump(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(argv, check=False, capture_output=True, cwd=cwd)


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


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename a Linux directory only when destination does not exist."""

    if os.name != "posix":
        raise GenerationError("atomic no-replace finalization is unsupported")
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise GenerationError("atomic no-replace finalization is unsupported") from exc
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    ) == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise GenerationError("completed generation already exists")
    raise GenerationError("atomic no-replace finalization failed")


def verify_generation(generation_dir: Path) -> VerificationResult:
    """Verify a completed local generation without any storage-service dependency."""

    errors: list[str] = []
    if not generation_dir.is_dir():
        return VerificationResult(False, ("generation directory is missing",))

    try:
        manifest = _read_manifest(generation_dir)
    except ValueError as exc:
        return VerificationResult(False, (str(exc),))

    missing = sorted(_MANIFEST_FIELDS - manifest.keys())
    if missing:
        errors.append("manifest missing fields: " + ", ".join(missing))
    extra = sorted(manifest.keys() - _MANIFEST_FIELDS)
    if extra:
        errors.append("manifest contains unsupported fields")
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
    if not _validate_generation_id(manifest.get("generation_id")):
        errors.append("generation identifier is invalid")
    elif manifest.get("generation_id") != generation_dir.name:
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

    created_at = _parse_utc_timestamp(manifest.get("created_at_utc"))
    completed_at = _parse_utc_timestamp(manifest.get("completed_at_utc"))
    if created_at is None:
        errors.append("created timestamp is invalid")
    if completed_at is None:
        errors.append("completed timestamp is invalid")
    if created_at is not None and completed_at is not None and completed_at < created_at:
        errors.append("completed timestamp precedes created timestamp")
    dump_size = manifest.get("dump_size_bytes")
    if not isinstance(dump_size, int) or isinstance(dump_size, bool) or dump_size <= 0:
        errors.append("dump size is invalid")
    checksum = manifest.get("checksum_value")
    if not isinstance(checksum, str) or _SHA256.fullmatch(checksum) is None:
        errors.append("checksum value is invalid")

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

    if not _validate_generation_id(generation_id):
        raise ValueError("generation_id must be a safe identifier")
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
        f"--file={dump_filename}",
        f"--dbname={database_logical_name}",
    ]
    completed = process_runner(argv, staging_dir)
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
    _rename_no_replace(staging_dir, completed_dir)
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
        try:
            generation = create_generation(
                root=args.root,
                database_logical_name=args.database_logical_name,
                generation_id=args.generation_id,
                pg_dump_executable=args.pg_dump_executable,
            )
        except (GenerationError, OSError, ValueError, subprocess.SubprocessError):
            print("ERROR: recovery generation failed", file=sys.stderr)
            return 1
        print(f"completed generation: {generation.name}")
        return 0
    try:
        result = verify_generation(args.generation_dir)
    except OSError:
        print("ERROR: recovery verification failed", file=sys.stderr)
        return 1
    if result.passed:
        print("PASS")
        return 0
    print("FAIL: " + "; ".join(result.errors))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
