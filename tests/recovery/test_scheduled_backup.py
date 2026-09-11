from __future__ import annotations

import stat
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from recovery import postgres_artifact, r2_activation, r2_publish, scheduled_backup

Failure = scheduled_backup.ScheduledBackupFailure
Error = scheduled_backup.ScheduledBackupError
GENERATION_ID = "scheduled-20260911T120000Z"
PRIVATE_MARKER = "SYNTHETIC_SECRET_PROVIDER_PRIVATE_PATH"


def recovery_environment() -> dict[str, str]:
    return {
        "PMTS_RECOVERY_R2_ENDPOINT_URL": "https://synthetic-account.r2.cloudflarestorage.com",
        "PMTS_RECOVERY_R2_BUCKET": "synthetic-recovery-bucket",
        "PMTS_RECOVERY_R2_REGION": "auto",
        "PMTS_RECOVERY_R2_ACCESS_KEY_ID": "SYNTHETIC_ACCESS_KEY",
        "PMTS_RECOVERY_R2_SECRET_ACCESS_KEY": "SYNTHETIC_SECRET_KEY",
    }


def fixed_clock() -> datetime:
    return datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def successful_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    lock_path: Path,
    calls: list[str],
) -> None:
    def fake_pg_dump(
        argv: Sequence[str],
        cwd: Path,
        *,
        pass_fds: Sequence[int] = (),
    ) -> subprocess.CompletedProcess[Any]:
        del argv, cwd
        calls.append("pg_dump")
        assert len(pass_fds) == 1
        with pytest.raises(Error) as raised:
            scheduled_backup.RecoveryRunLock(lock_path).acquire()
        assert raised.value.category is Failure.OVERLAP
        return subprocess.CompletedProcess([], 0)

    def create_generation(**kwargs: object) -> Path:
        calls.append("create")
        assert kwargs["generation_id"] == GENERATION_ID
        assert kwargs["root"] == root
        now = kwargs["now"]
        assert callable(now)
        assert now() == fixed_clock()
        runner = kwargs["process_runner"]
        assert callable(runner)
        runner(["synthetic-pg-dump"], root)
        return root / postgres_artifact.COMPLETED_DIRNAME / GENERATION_ID

    def verify_generation(path: Path) -> postgres_artifact.VerificationResult:
        calls.append("verify")
        assert path.name == GENERATION_ID
        return postgres_artifact.VerificationResult(True)

    def run_preflight(**kwargs: object) -> r2_activation.RecoveryActivationPreflight:
        calls.append("preflight")
        assert kwargs["generation_dir"] == root / "completed" / GENERATION_ID
        return r2_activation.RecoveryActivationPreflight(
            generation_id=GENERATION_ID,
            dump_size_bytes=1,
            object_keys=("dump", "checksum", "manifest"),
        )

    def publish_generation(**kwargs: object) -> r2_publish.VerifiedRemoteGeneration:
        calls.append("publish_and_remote_verify")
        assert kwargs["generation_dir"] == root / "completed" / GENERATION_ID
        with pytest.raises(Error) as raised:
            scheduled_backup.RecoveryRunLock(lock_path).acquire()
        assert raised.value.category is Failure.OVERLAP
        return r2_publish.VerifiedRemoteGeneration(
            generation_id=GENERATION_ID,
            object_keys=("dump", "checksum", "manifest"),
        )

    monkeypatch.setattr(postgres_artifact, "_run_pg_dump", fake_pg_dump)
    monkeypatch.setattr(postgres_artifact, "create_generation", create_generation)
    monkeypatch.setattr(postgres_artifact, "verify_generation", verify_generation)
    monkeypatch.setattr(r2_activation, "run_preflight", run_preflight)
    monkeypatch.setattr(r2_activation, "publish_generation", publish_generation)


def test_run_orders_existing_boundaries_and_binds_lock_fd_to_default_dump_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    root = tmp_path / "recovery"
    lock_path = tmp_path / "scheduled-backup.lock"
    successful_boundaries(monkeypatch, root=root, lock_path=lock_path, calls=calls)

    result = scheduled_backup.run_scheduled_backup(
        root=root,
        database_logical_name="appdb",
        lock_path=lock_path,
        environ=recovery_environment(),
        now=fixed_clock,
    )

    assert result == scheduled_backup.ScheduledBackupResult(generation_id=GENERATION_ID)
    assert calls == [
        "create",
        "pg_dump",
        "verify",
        "preflight",
        "publish_and_remote_verify",
    ]
    acquired = scheduled_backup.RecoveryRunLock(lock_path)
    assert acquired.acquire() >= 0
    acquired.close()


def test_injected_two_argument_process_runner_remains_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    root = tmp_path / "recovery"
    lock_path = tmp_path / "scheduled-backup.lock"
    successful_boundaries(monkeypatch, root=root, lock_path=lock_path, calls=calls)
    injected_calls: list[tuple[Sequence[str], Path]] = []

    def two_argument_runner(
        argv: Sequence[str], cwd: Path
    ) -> subprocess.CompletedProcess[Any]:
        injected_calls.append((argv, cwd))
        return subprocess.CompletedProcess(argv, 0)

    result = scheduled_backup.run_scheduled_backup(
        root=root,
        database_logical_name="appdb",
        lock_path=lock_path,
        environ=recovery_environment(),
        now=fixed_clock,
        process_runner=two_argument_runner,
    )

    assert result.generation_id == GENERATION_ID
    assert injected_calls == [(["synthetic-pg-dump"], root)]
    assert "pg_dump" not in calls


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 9, 11, 21, 0, tzinfo=timezone(timedelta(hours=9))), GENERATION_ID),
        (
            datetime(2026, 9, 12, 1, 30, 45, 999999, tzinfo=timezone(timedelta(hours=9))),
            "scheduled-20260911T163045Z",
        ),
    ],
)
def test_generation_identity_uses_actual_utc_start(
    value: datetime, expected: str
) -> None:
    assert scheduled_backup._generation_id(value) == expected


def test_naive_clock_fails_before_generation_or_remote_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: calls.append("create"),
    )
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: calls.append("preflight"),
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=tmp_path / "recovery",
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=lambda: datetime(2026, 9, 11, 12, 0),
        )

    assert raised.value.category is Failure.GENERATION_FAILURE
    assert calls == []


def test_invalid_database_selector_fails_before_dump_or_remote_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: calls.append("create"),
    )
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: calls.append("preflight"),
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=tmp_path / "recovery",
            database_logical_name="postgresql://user:secret@private-host/appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
        )

    assert raised.value.category is Failure.INVALID_ARGUMENTS
    assert calls == []


def _patch_until_local_verify(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    verification: postgres_artifact.VerificationResult,
    remote_calls: list[str],
) -> None:
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: root / "completed" / GENERATION_ID,
    )
    monkeypatch.setattr(postgres_artifact, "verify_generation", lambda _: verification)
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: remote_calls.append("preflight"),
    )
    monkeypatch.setattr(
        r2_activation,
        "publish_generation",
        lambda **_: remote_calls.append("publish"),
    )


def test_generation_failure_retains_staging_and_makes_no_remote_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    root = tmp_path / "recovery"

    def fail_dump(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[Any]:
        del argv
        calls.append("pg_dump")
        (cwd / "appdb.dump").write_bytes(b"partial")
        return subprocess.CompletedProcess([], 1)

    monkeypatch.setattr(r2_activation, "run_preflight", lambda **_: calls.append("preflight"))
    monkeypatch.setattr(
        r2_activation,
        "publish_generation",
        lambda **_: calls.append("publish"),
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
            process_runner=fail_dump,
        )

    assert raised.value.category is Failure.GENERATION_FAILURE
    assert calls == ["pg_dump"]
    assert (root / "staging" / GENERATION_ID / "appdb.dump").read_bytes() == b"partial"
    assert not (root / "completed" / GENERATION_ID).exists()


@pytest.mark.parametrize("collision_dir", ["staging", "completed"])
def test_local_collision_is_retained_and_makes_no_dump_or_remote_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision_dir: str,
) -> None:
    calls: list[str] = []
    root = tmp_path / "recovery"
    collision = root / collision_dir / GENERATION_ID
    collision.mkdir(parents=True)
    marker = collision / "existing-evidence"
    marker.write_text("retained", encoding="utf-8")

    def unexpected_dump(
        argv: Sequence[str], cwd: Path
    ) -> subprocess.CompletedProcess[Any]:
        del argv, cwd
        calls.append("pg_dump")
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(r2_activation, "run_preflight", lambda **_: calls.append("preflight"))
    monkeypatch.setattr(
        r2_activation,
        "publish_generation",
        lambda **_: calls.append("publish"),
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
            process_runner=unexpected_dump,
        )

    assert raised.value.category is Failure.GENERATION_FAILURE
    assert calls == []
    assert marker.read_text(encoding="utf-8") == "retained"


def test_explicit_local_verification_failure_prevents_preflight_and_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote_calls: list[str] = []
    root = tmp_path / "recovery"
    _patch_until_local_verify(
        monkeypatch,
        root=root,
        verification=postgres_artifact.VerificationResult(False, (PRIVATE_MARKER,)),
        remote_calls=remote_calls,
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
        )

    assert raised.value.category is Failure.LOCAL_VERIFICATION_FAILURE
    assert remote_calls == []


def test_preflight_failure_prevents_publish_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    root = tmp_path / "recovery"
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: root / "completed" / GENERATION_ID,
    )
    monkeypatch.setattr(
        postgres_artifact,
        "verify_generation",
        lambda _: postgres_artifact.VerificationResult(True),
    )

    def fail_preflight(**_: object) -> None:
        calls.append("preflight")
        raise r2_activation.RecoveryActivationError(
            r2_activation.RecoveryActivationFailure.INVALID_CONFIG
        )

    monkeypatch.setattr(r2_activation, "run_preflight", fail_preflight)
    monkeypatch.setattr(
        r2_activation,
        "publish_generation",
        lambda **_: calls.append("publish"),
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
        )

    assert raised.value.category is Failure.PREFLIGHT_FAILURE
    assert calls == ["preflight"]


@pytest.mark.parametrize(
    ("lower_failure", "expected"),
    [
        (
            r2_publish.RecoveryPublishFailure.UNSUPPORTED_OBJECT_SIZE,
            Failure.UNSUPPORTED_OBJECT_SIZE,
        ),
        (
            r2_publish.RecoveryPublishFailure.REMOTE_PRECONDITION_COLLISION,
            Failure.REMOTE_PRECONDITION_COLLISION,
        ),
        (r2_publish.RecoveryPublishFailure.REMOTE_TRANSPORT_FAILURE, Failure.PUBLISH_FAILURE),
        (
            r2_publish.RecoveryPublishFailure.REMOTE_VERIFICATION_FAILURE,
            Failure.REMOTE_VERIFICATION_FAILURE,
        ),
    ],
)
def test_publish_failures_are_mapped_once_and_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lower_failure: r2_publish.RecoveryPublishFailure,
    expected: Failure,
) -> None:
    calls: list[str] = []
    root = tmp_path / "recovery"
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: root / "completed" / GENERATION_ID,
    )
    monkeypatch.setattr(
        postgres_artifact,
        "verify_generation",
        lambda _: postgres_artifact.VerificationResult(True),
    )
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: r2_activation.RecoveryActivationPreflight(
            generation_id=GENERATION_ID,
            dump_size_bytes=1,
            object_keys=("dump", "checksum", "manifest"),
        ),
    )

    def fail_publish(**_: object) -> None:
        calls.append("publish")
        raise r2_publish.RecoveryPublishError(lower_failure)

    monkeypatch.setattr(r2_activation, "publish_generation", fail_publish)

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
        )

    assert raised.value.category is expected
    assert calls == ["publish"]


def test_unverified_remote_result_cannot_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "recovery"
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: root / "completed" / GENERATION_ID,
    )
    monkeypatch.setattr(
        postgres_artifact,
        "verify_generation",
        lambda _: postgres_artifact.VerificationResult(True),
    )
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: r2_activation.RecoveryActivationPreflight(
            generation_id=GENERATION_ID,
            dump_size_bytes=1,
            object_keys=("dump", "checksum", "manifest"),
        ),
    )
    monkeypatch.setattr(
        r2_activation,
        "publish_generation",
        lambda **_: r2_publish.VerifiedRemoteGeneration(
            generation_id=GENERATION_ID,
            object_keys=("dump", "checksum", "manifest"),
            verified=False,
        ),
    )

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
        )

    assert raised.value.category is Failure.REMOTE_VERIFICATION_FAILURE


@pytest.mark.parametrize("boundary", ["local", "preflight", "remote"])
def test_identity_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    root = tmp_path / "recovery"
    local_id = "other-generation" if boundary == "local" else GENERATION_ID
    preflight_id = "other-generation" if boundary == "preflight" else GENERATION_ID
    remote_id = "other-generation" if boundary == "remote" else GENERATION_ID
    publish_calls: list[str] = []
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: root / "completed" / local_id,
    )
    monkeypatch.setattr(
        postgres_artifact,
        "verify_generation",
        lambda _: postgres_artifact.VerificationResult(True),
    )
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: r2_activation.RecoveryActivationPreflight(
            generation_id=preflight_id,
            dump_size_bytes=1,
            object_keys=("dump", "checksum", "manifest"),
        ),
    )

    def publish(**_: object) -> r2_publish.VerifiedRemoteGeneration:
        publish_calls.append("publish")
        return r2_publish.VerifiedRemoteGeneration(
            generation_id=remote_id,
            object_keys=("dump", "checksum", "manifest"),
        )

    monkeypatch.setattr(r2_activation, "publish_generation", publish)

    with pytest.raises(Error) as raised:
        scheduled_backup.run_scheduled_backup(
            root=root,
            database_logical_name="appdb",
            lock_path=tmp_path / "scheduled-backup.lock",
            now=fixed_clock,
        )

    assert raised.value.category is Failure.GENERATION_IDENTITY_MISMATCH
    assert publish_calls == ([] if boundary in {"local", "preflight"} else ["publish"])


def test_overlap_uses_shared_lock_across_different_roots_and_exits_75(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    lock_path = tmp_path / "scheduled-backup.lock"
    held = scheduled_backup.RecoveryRunLock(lock_path)
    held.acquire()
    monkeypatch.setattr(
        postgres_artifact,
        "create_generation",
        lambda **_: calls.append("create"),
    )
    monkeypatch.setattr(
        r2_activation,
        "run_preflight",
        lambda **_: calls.append("preflight"),
    )

    try:
        exit_code = scheduled_backup.main(
            [
                "--root",
                str(tmp_path / "different-root"),
                "--database-logical-name",
                "appdb",
                "--lock-path",
                str(lock_path),
            ],
            now=fixed_clock,
        )
    finally:
        held.close()

    captured = capsys.readouterr()
    assert exit_code == scheduled_backup.OVERLAP_EXIT_CODE
    assert captured.out == ""
    assert captured.err == "ERROR: scheduled recovery failed: overlap\n"
    assert calls == []


@pytest.mark.parametrize("unsafe_kind", ["missing-parent", "symlink", "directory"])
def test_guard_rejects_unsafe_lock_state(
    tmp_path: Path, unsafe_kind: str
) -> None:
    lock_path = tmp_path / "scheduled-backup.lock"
    if unsafe_kind == "missing-parent":
        lock_path = tmp_path / "missing" / "scheduled-backup.lock"
    elif unsafe_kind == "symlink":
        target = tmp_path / "target"
        target.write_text("unchanged", encoding="utf-8")
        lock_path.symlink_to(target)
    else:
        lock_path.mkdir()

    with pytest.raises(Error) as raised:
        scheduled_backup.RecoveryRunLock(lock_path).acquire()

    assert raised.value.category is Failure.GUARD_FAILURE
    if unsafe_kind == "symlink":
        assert target.read_text(encoding="utf-8") == "unchanged"


def test_new_guard_is_private_empty_and_is_never_unlinked(tmp_path: Path) -> None:
    lock_path = tmp_path / "scheduled-backup.lock"
    lock = scheduled_backup.RecoveryRunLock(lock_path)

    lock.acquire()
    lock.close()

    assert lock_path.exists()
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
    assert lock_path.read_bytes() == b""


def test_dump_child_keeps_lock_after_parent_exits(tmp_path: Path) -> None:
    lock_path = tmp_path / "scheduled-backup.lock"
    ready_path = tmp_path / "child-ready"
    release_path = tmp_path / "child-release"
    child_code = """
import sys
import time
from pathlib import Path

ready = Path(sys.argv[1])
release = Path(sys.argv[2])
ready.touch()
while not release.exists():
    time.sleep(0.01)
"""
    parent_code = f"""
import fcntl
import os
import sys
from pathlib import Path

from recovery import postgres_artifact

lock_fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
postgres_artifact._run_pg_dump(
    [sys.executable, "-c", {child_code!r}, sys.argv[2], sys.argv[3]],
    Path.cwd(),
    pass_fds=(lock_fd,),
)
"""
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code, str(lock_path), str(ready_path), str(release_path)],
        cwd=Path.cwd(),
    )

    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready_path.exists()

        parent.terminate()
        assert parent.wait(timeout=5) != 0

        with pytest.raises(Error) as raised:
            scheduled_backup.RecoveryRunLock(lock_path).acquire()
        assert raised.value.category is Failure.OVERLAP

        release_path.touch()
        acquired: scheduled_backup.RecoveryRunLock | None = None
        deadline = time.monotonic() + 5
        while acquired is None and time.monotonic() < deadline:
            candidate = scheduled_backup.RecoveryRunLock(lock_path)
            try:
                candidate.acquire()
            except Error as exc:
                assert exc.category is Failure.OVERLAP
                time.sleep(0.01)
            else:
                acquired = candidate
        assert acquired is not None
        acquired.close()
    finally:
        release_path.touch(exist_ok=True)
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=5)


def test_cli_success_is_machine_checkable_and_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        scheduled_backup,
        "run_scheduled_backup",
        lambda **_: scheduled_backup.ScheduledBackupResult(GENERATION_ID),
    )

    exit_code = scheduled_backup.main(
        [
            "--root",
            str(tmp_path / PRIVATE_MARKER),
            "--database-logical-name",
            "appdb",
            "--lock-path",
            str(tmp_path / "lock"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        f"generation={GENERATION_ID}\n"
        "local_verification=PASS\n"
        "remote_verification=PASS\n"
        "scheduled_recovery=PASS\n"
    )
    assert captured.err == ""
    assert PRIVATE_MARKER not in captured.out


@pytest.mark.parametrize(
    "argv",
    [[], ["--root", PRIVATE_MARKER], ["--unknown", PRIVATE_MARKER]],
)
def test_cli_argument_failures_do_not_echo_private_input(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert scheduled_backup.main(argv) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: scheduled recovery failed: invalid_arguments\n"
    assert PRIVATE_MARKER not in captured.err


def test_cli_unexpected_error_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**_: object) -> None:
        raise RuntimeError(PRIVATE_MARKER)

    monkeypatch.setattr(scheduled_backup, "run_scheduled_backup", fail)

    assert (
        scheduled_backup.main(
            [
                "--root",
                str(tmp_path / PRIVATE_MARKER),
                "--database-logical-name",
                "appdb",
                "--lock-path",
                str(tmp_path / "lock"),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: scheduled recovery failed: internal_error\n"
    assert PRIVATE_MARKER not in captured.err


def test_cli_help_has_no_configuration_or_client_side_effect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory_calls: list[object] = []

    def factory(config: object) -> object:
        factory_calls.append(config)
        return object()

    with pytest.raises(SystemExit) as raised:
        scheduled_backup.main(["--help"], client_factory=factory)  # type: ignore[arg-type]

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert "--lock-path" in captured.out
    assert captured.err == ""
    assert factory_calls == []
