"""Run one guarded PostgreSQL recovery generation through remote verification."""

from __future__ import annotations

import argparse
import fcntl
import os
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import NoReturn

from recovery import postgres_artifact, r2_activation, r2_publish

OVERLAP_EXIT_CODE = 75


class ScheduledBackupFailure(StrEnum):
    """Sanitized failures exposed by the scheduler-facing recovery boundary."""

    INVALID_ARGUMENTS = "invalid_arguments"
    OVERLAP = "overlap"
    GUARD_FAILURE = "guard_failure"
    GENERATION_FAILURE = "generation_failure"
    LOCAL_VERIFICATION_FAILURE = "local_verification_failure"
    GENERATION_IDENTITY_MISMATCH = "generation_identity_mismatch"
    PREFLIGHT_FAILURE = "preflight_failure"
    UNSUPPORTED_OBJECT_SIZE = "unsupported_object_size"
    REMOTE_PRECONDITION_COLLISION = "remote_precondition_collision"
    PUBLISH_FAILURE = "publish_failure"
    REMOTE_VERIFICATION_FAILURE = "remote_verification_failure"
    INTERNAL_ERROR = "internal_error"


class ScheduledBackupError(RuntimeError):
    """A scheduled recovery failure without credential or path detail."""

    def __init__(self, category: ScheduledBackupFailure) -> None:
        super().__init__(category.value)
        self.category = category


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ScheduledBackupError(ScheduledBackupFailure.INVALID_ARGUMENTS)


@dataclass(frozen=True, slots=True)
class ScheduledBackupResult:
    """The safe identity of one locally and remotely verified generation."""

    generation_id: str


class RecoveryRunLock:
    """Nonblocking single-host guard for all cooperating A5 invocations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    def acquire(self) -> int:
        if self._fd is not None:
            raise ScheduledBackupError(ScheduledBackupFailure.GUARD_FAILURE)
        if not self.path.name or self.path.name in {".", ".."}:
            raise ScheduledBackupError(ScheduledBackupFailure.GUARD_FAILURE)

        try:
            parent_fd = os.open(
                self.path.parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
            )
        except (OSError, TypeError, ValueError):
            raise ScheduledBackupError(ScheduledBackupFailure.GUARD_FAILURE) from None

        try:
            fd = os.open(
                self.path.name,
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
        except (OSError, TypeError, ValueError):
            raise ScheduledBackupError(ScheduledBackupFailure.GUARD_FAILURE) from None
        finally:
            os.close(parent_fd)

        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ScheduledBackupError(ScheduledBackupFailure.GUARD_FAILURE)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise ScheduledBackupError(ScheduledBackupFailure.OVERLAP) from None
        except ScheduledBackupError:
            os.close(fd)
            raise
        except OSError:
            os.close(fd)
            raise ScheduledBackupError(ScheduledBackupFailure.GUARD_FAILURE) from None

        self._fd = fd
        return fd

    def close(self) -> None:
        if self._fd is None:
            return
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> int:
        return self.acquire()

    def __exit__(self, *exc_info: object) -> None:
        del exc_info
        self.close()


Clock = Callable[[], datetime]


def _generation_id(value: datetime) -> str:
    try:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError
        utc_value = value.astimezone(UTC)
        generation_id = (
            f"scheduled-{utc_value.year:04d}{utc_value.month:02d}{utc_value.day:02d}"
            f"T{utc_value.hour:02d}{utc_value.minute:02d}{utc_value.second:02d}Z"
        )
    except Exception:
        raise ScheduledBackupError(ScheduledBackupFailure.GENERATION_FAILURE) from None
    if not postgres_artifact._validate_generation_id(generation_id):
        raise ScheduledBackupError(ScheduledBackupFailure.GENERATION_FAILURE)
    return generation_id


def _a1_clock(started_at: datetime, clock: Clock) -> Clock:
    first_call = True

    def now() -> datetime:
        nonlocal first_call
        if first_call:
            first_call = False
            return started_at
        return clock()

    return now


def _activation_failure(
    exc: r2_activation.RecoveryActivationError,
) -> ScheduledBackupFailure:
    mapping = {
        r2_activation.RecoveryActivationFailure.INVALID_CONFIG: (
            ScheduledBackupFailure.PREFLIGHT_FAILURE
        ),
        r2_activation.RecoveryActivationFailure.INVALID_ARGUMENTS: (
            ScheduledBackupFailure.PREFLIGHT_FAILURE
        ),
        r2_activation.RecoveryActivationFailure.INVALID_LOCAL_GENERATION: (
            ScheduledBackupFailure.LOCAL_VERIFICATION_FAILURE
        ),
        r2_activation.RecoveryActivationFailure.UNSUPPORTED_OBJECT_SIZE: (
            ScheduledBackupFailure.UNSUPPORTED_OBJECT_SIZE
        ),
        r2_activation.RecoveryActivationFailure.REMOTE_VERIFICATION_FAILURE: (
            ScheduledBackupFailure.REMOTE_VERIFICATION_FAILURE
        ),
    }
    return mapping.get(exc.category, ScheduledBackupFailure.INTERNAL_ERROR)


def _publish_failure(exc: r2_publish.RecoveryPublishError) -> ScheduledBackupFailure:
    mapping = {
        r2_publish.RecoveryPublishFailure.INVALID_LOCAL_GENERATION: (
            ScheduledBackupFailure.LOCAL_VERIFICATION_FAILURE
        ),
        r2_publish.RecoveryPublishFailure.UNSUPPORTED_OBJECT_SIZE: (
            ScheduledBackupFailure.UNSUPPORTED_OBJECT_SIZE
        ),
        r2_publish.RecoveryPublishFailure.REMOTE_PRECONDITION_COLLISION: (
            ScheduledBackupFailure.REMOTE_PRECONDITION_COLLISION
        ),
        r2_publish.RecoveryPublishFailure.REMOTE_TRANSPORT_FAILURE: (
            ScheduledBackupFailure.PUBLISH_FAILURE
        ),
        r2_publish.RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE: (
            ScheduledBackupFailure.REMOTE_VERIFICATION_FAILURE
        ),
    }
    return mapping.get(exc.category, ScheduledBackupFailure.INTERNAL_ERROR)


def run_scheduled_backup(
    *,
    root: Path,
    database_logical_name: str,
    lock_path: Path,
    environ: Mapping[str, str] | None = None,
    now: Clock | None = None,
    pg_dump_executable: str = "pg_dump",
    process_runner: postgres_artifact.ProcessRunner | None = None,
    client_factory: r2_activation.ClientFactory | None = None,
) -> ScheduledBackupResult:
    """Create, locally verify, publish, and remotely verify one generation."""

    clock = now or (lambda: datetime.now(UTC))
    with RecoveryRunLock(lock_path) as lock_fd:
        try:
            started_at = clock()
        except Exception:
            raise ScheduledBackupError(ScheduledBackupFailure.GENERATION_FAILURE) from None
        generation_id = _generation_id(started_at)
        try:
            postgres_artifact.safe_database_filename(database_logical_name)
        except ValueError:
            raise ScheduledBackupError(ScheduledBackupFailure.INVALID_ARGUMENTS) from None
        except Exception:
            raise ScheduledBackupError(ScheduledBackupFailure.INTERNAL_ERROR) from None
        dump_runner = process_runner or partial(
            postgres_artifact._run_pg_dump,
            pass_fds=(lock_fd,),
        )

        try:
            generation_dir = postgres_artifact.create_generation(
                root=Path(root),
                database_logical_name=database_logical_name,
                generation_id=generation_id,
                now=_a1_clock(started_at, clock),
                pg_dump_executable=pg_dump_executable,
                process_runner=dump_runner,
            )
        except (postgres_artifact.GenerationError, OSError, ValueError, subprocess.SubprocessError):
            raise ScheduledBackupError(ScheduledBackupFailure.GENERATION_FAILURE) from None
        except Exception:
            raise ScheduledBackupError(ScheduledBackupFailure.INTERNAL_ERROR) from None

        expected_dir = Path(root) / postgres_artifact.COMPLETED_DIRNAME / generation_id
        if (
            not isinstance(generation_dir, Path)
            or generation_dir != expected_dir
            or generation_dir.name != generation_id
        ):
            raise ScheduledBackupError(
                ScheduledBackupFailure.GENERATION_IDENTITY_MISMATCH
            )

        try:
            local_verification = postgres_artifact.verify_generation(generation_dir)
        except (OSError, ValueError):
            raise ScheduledBackupError(
                ScheduledBackupFailure.LOCAL_VERIFICATION_FAILURE
            ) from None
        except Exception:
            raise ScheduledBackupError(ScheduledBackupFailure.INTERNAL_ERROR) from None
        if not local_verification.passed:
            raise ScheduledBackupError(ScheduledBackupFailure.LOCAL_VERIFICATION_FAILURE)

        try:
            preflight = r2_activation.run_preflight(
                generation_dir=generation_dir,
                environ=environ,
            )
        except r2_activation.RecoveryActivationError as exc:
            raise ScheduledBackupError(_activation_failure(exc)) from None
        except Exception:
            raise ScheduledBackupError(ScheduledBackupFailure.INTERNAL_ERROR) from None
        if preflight.generation_id != generation_id:
            raise ScheduledBackupError(
                ScheduledBackupFailure.GENERATION_IDENTITY_MISMATCH
            )

        try:
            remote = r2_activation.publish_generation(
                generation_dir=generation_dir,
                environ=environ,
                client_factory=client_factory,
            )
        except r2_activation.RecoveryActivationError as exc:
            raise ScheduledBackupError(_activation_failure(exc)) from None
        except r2_publish.RecoveryPublishError as exc:
            raise ScheduledBackupError(_publish_failure(exc)) from None
        except Exception:
            raise ScheduledBackupError(ScheduledBackupFailure.INTERNAL_ERROR) from None
        if not remote.verified:
            raise ScheduledBackupError(ScheduledBackupFailure.REMOTE_VERIFICATION_FAILURE)
        if remote.generation_id != generation_id:
            raise ScheduledBackupError(
                ScheduledBackupFailure.GENERATION_IDENTITY_MISMATCH
            )

        return ScheduledBackupResult(generation_id=generation_id)


def build_parser() -> argparse.ArgumentParser:
    """Build the scheduler-facing recovery CLI without loading configuration."""

    parser = _SanitizedArgumentParser(
        description="Create and remotely verify one guarded PostgreSQL recovery generation"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--database-logical-name", required=True)
    parser.add_argument("--lock-path", type=Path, required=True)
    parser.add_argument("--pg-dump-executable", default="pg_dump")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    now: Clock | None = None,
    process_runner: postgres_artifact.ProcessRunner | None = None,
    client_factory: r2_activation.ClientFactory | None = None,
) -> int:
    """Run one scheduled recovery with deterministic sanitized output."""

    try:
        args = build_parser().parse_args(argv)
        result = run_scheduled_backup(
            root=args.root,
            database_logical_name=args.database_logical_name,
            lock_path=args.lock_path,
            environ=environ,
            now=now,
            pg_dump_executable=args.pg_dump_executable,
            process_runner=process_runner,
            client_factory=client_factory,
        )
    except ScheduledBackupError as exc:
        category = exc.category
    except KeyboardInterrupt:
        category = ScheduledBackupFailure.INTERNAL_ERROR
    except Exception:
        category = ScheduledBackupFailure.INTERNAL_ERROR
    else:
        print(f"generation={result.generation_id}")
        print("local_verification=PASS")
        print("remote_verification=PASS")
        print("scheduled_recovery=PASS")
        return 0

    print(f"ERROR: scheduled recovery failed: {category.value}", file=sys.stderr)
    if category is ScheduledBackupFailure.OVERLAP:
        return OVERLAP_EXIT_CODE
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
