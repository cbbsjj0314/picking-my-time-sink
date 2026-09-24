from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from recovery import rotation_once as once
from recovery.rotation_collect import CollectionLimits


@pytest.fixture
def plan(tmp_path):
    parent = tmp_path.resolve() / "evidence"
    parent.mkdir(mode=0o700)
    properties = {
        "LoadState": "loaded",
        "NeedDaemonReload": "no",
        "DropInPaths": "",
        "FragmentPath": "/synthetic/service",
        "UnitFileState": "static",
        "User": "pmts",
        "Restart": "no",
    }
    return once.ExecutionPlan.parse(
        json.dumps(
            {
                "code_root": "/synthetic/code",
                "revision": "a" * 40,
                "grant_ref": "b" * 40 + ":A7-PHASE3-PROD-READONLY-HANDOFF-01",
                "recovery_root": str(tmp_path.resolve() / "source"),
                "evidence_parent": str(parent),
                "attempt_id": "synthetic-attempt",
                "reader_env": str(tmp_path / "recovery-r2-readonly.env"),
                "endpoint": "https://synthetic.r2.cloudflarestorage.com",
                "bucket": "synthetic-bucket",
                "uid": os.getuid(),
                "gid": os.getgid(),
                "limits": asdict(CollectionLimits(4, 1024, 16384, 2, 12, max_page_bytes=4096)),
                "tool_sha256": dict.fromkeys(once._TOOLS, "c" * 64),
                "scheduler_properties": {
                    "pmts-postgres-recovery.service": properties,
                    "pmts-postgres-recovery.timer": properties
                    | {
                        "FragmentPath": "/synthetic/timer",
                        "ActiveState": "active",
                        "UnitFileState": "enabled",
                        "TimersCalendar": "synthetic-calendar",
                    },
                },
                "scheduler_sha256": {"/synthetic/service": "d" * 64, "/synthetic/timer": "e" * 64},
            }
        )
    )


@pytest.fixture
def reader(plan):
    return {
        "PMTS_RECOVERY_R2_ENDPOINT_URL": plan.endpoint,
        "PMTS_RECOVERY_R2_BUCKET": plan.bucket,
        "PMTS_RECOVERY_R2_REGION": "auto",
        "PMTS_RECOVERY_R2_ACCESS_KEY_ID": "synthetic-access",
        "PMTS_RECOVERY_R2_SECRET_ACCESS_KEY": "synthetic-secret",
    }


@pytest.fixture
def worker_host(monkeypatch):
    # OS assertions are tested separately; no production paths or tools execute.
    for name in (
        "_reader_fd_preflight",
        "_identity_preflight",
        "_runtime_preflight",
        "_code_preflight",
        "_scheduler_preflight",
        "_ancestors",
    ):
        monkeypatch.setattr(once, name, Mock())
    monkeypatch.setattr(once.tempfile, "tempdir", None)
    monkeypatch.setattr(once.os, "umask", Mock())


@pytest.mark.parametrize(
    "boundary",
    [
        "_reader_fd_preflight",
        "_identity_preflight",
        "_runtime_preflight",
        "_code_preflight",
        "_scheduler_preflight",
        "_destination_preflight",
    ],
)
def test_preflight_failure_never_calls_inventory_or_creates_attempt(
    plan, reader, worker_host, monkeypatch, boundary
):
    monkeypatch.setattr(once, boundary, Mock(side_effect=once.PreflightError))
    collector, client = Mock(), Mock()
    # No local inventory enumeration is permitted anywhere in this branch.
    monkeypatch.setattr(os, "scandir", Mock(side_effect=AssertionError("inventory access")))
    assert (
        once.run_worker(
            plan,
            environ=once.child_environment(plan, reader),
            collector=collector,
            client_factory=client,
        )
        == 2
    )
    collector.assert_not_called()
    client.assert_not_called()
    os.scandir.assert_not_called()
    assert not plan.attempt_dir.exists()


@pytest.mark.parametrize("change", ["ambient", "prefix", "missing", "bucket", "region", "endpoint"])
def test_environment_rejection_before_attempt(plan, reader, worker_host, change):
    env = once.child_environment(plan, reader)
    if change == "ambient":
        env["HTTPS_PROXY"] = "https://synthetic.invalid"
    elif change == "prefix":
        env["PMTS_RECOVERY_R2_KEY_PREFIX"] = "unexpected"
    elif change == "missing":
        del env["PMTS_RECOVERY_R2_SECRET_ACCESS_KEY"]
    else:
        env["PMTS_RECOVERY_R2_" + change.upper() + ("_URL" if change == "endpoint" else "")] = "bad"
    collector = Mock()
    assert once.run_worker(plan, environ=env, collector=collector) == 2
    collector.assert_not_called()
    assert not plan.attempt_dir.exists()


@pytest.mark.parametrize("outcome,expected", [("advisory", 0), ("blocked", 1), ("exception", 1)])
def test_exactly_once_and_exact_binding(plan, reader, worker_host, outcome, expected):
    def collect(**kwargs):
        assert kwargs["authority"].local_write_capable is True
        assert kwargs["authority"].handoff_ref == plan.grant_ref
        assert kwargs["authority"].r2_read_only_ref == plan.grant_ref + "#reader"
        assert kwargs["pins"].confirmed is True and kwargs["pins"].pins == ()
        assert kwargs["pins"].authority_ref == plan.grant_ref + "#pins-none"
        assert kwargs["snapshot_id"] == plan.attempt_id
        assert kwargs["evidence_ref"] == str(plan.attempt_dir / "evidence.json")
        assert kwargs["limits"] == CollectionLimits(**plan.limits)
        assert kwargs["max_output_bytes"] == once.output_budget(kwargs["limits"])
        assert not kwargs["attempt_dir"].exists()
        assert once.tempfile.gettempdir() == plan.evidence_parent
        kwargs["attempt_dir"].mkdir()
        if outcome == "exception":
            raise RuntimeError("synthetic-sensitive-provider-detail")
        return SimpleNamespace(report_json=json.dumps({"candidate_set_status": outcome}))

    collector = Mock(side_effect=collect)
    assert (
        once.run_worker(plan, environ=once.child_environment(plan, reader), collector=collector)
        == expected
    )
    collector.assert_called_once()
    # Partial and successful evidence both prohibit a second invocation.
    assert (
        once.run_worker(plan, environ=once.child_environment(plan, reader), collector=collector)
        == 2
    )
    collector.assert_called_once()


def test_competing_caller_does_not_start(plan, reader, worker_host, monkeypatch):
    monkeypatch.setattr(once.fcntl, "flock", Mock(side_effect=BlockingIOError))
    collector = Mock()
    assert (
        once.run_worker(plan, environ=once.child_environment(plan, reader), collector=collector)
        == 2
    )
    collector.assert_not_called()
    assert not plan.attempt_dir.exists()


def test_headroom_exact_threshold(plan, monkeypatch):
    monkeypatch.setattr(once, "_ancestors", Mock())
    limits = CollectionLimits(**plan.limits)
    required, inodes = once.capacity_required(limits, 4096)
    available_blocks = (required + 4095) // 4096
    fs = SimpleNamespace(f_frsize=4096, f_bsize=4096, f_bavail=available_blocks, f_favail=inodes)
    monkeypatch.setattr(os, "statvfs", lambda _: fs)
    once._destination_preflight(plan)
    fs.f_bavail -= 1
    with pytest.raises(once.PreflightError):
        once._destination_preflight(plan)
    fs.f_bavail += 1
    fs.f_favail -= 1
    with pytest.raises(once.PreflightError):
        once._destination_preflight(plan)
    assert not plan.attempt_dir.exists()


def test_capacity_accounts_for_both_a2_copies_and_outputs(plan):
    limits = CollectionLimits(**plan.limits)
    base, nodes = once.capacity_required(limits, 4096)
    assert once.capacity_required(replace(limits, max_dump_bytes=1025), 4096)[0] == base + 2
    assert once.capacity_required(replace(limits, max_local_bytes=16385), 4096)[0] == base + 1
    assert base == (
        limits.max_local_bytes
        + 2 * (limits.max_dump_bytes + 65536 + 256)
        + once.output_budget(limits)
        + 2 * nodes * 4096
    )


@pytest.mark.parametrize("kind", ["directory", "dangling_symlink"])
def test_consumed_destination_fails_without_enumeration(plan, monkeypatch, kind):
    monkeypatch.setattr(once, "_ancestors", Mock())
    if kind == "directory":
        plan.attempt_dir.mkdir()
    else:
        plan.attempt_dir.symlink_to("/synthetic/absent")
    with pytest.raises(once.PreflightError):
        once._destination_preflight(plan)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(reader_env="/synthetic/recovery-r2.env"),
        lambda p: p.update(grant_ref="main"),
        lambda p: p.update(uid=0),
        lambda p: p.update(evidence_parent=p["recovery_root"] + "/child"),
        lambda p: p.update(attempt_id="../escape"),
        lambda p: p["scheduler_properties"]["pmts-postgres-recovery.timer"].update(
            ActiveState="inactive"
        ),
        lambda p: p["scheduler_properties"]["pmts-postgres-recovery.service"].update(
            Restart="always"
        ),
        lambda p: p.update(tool_sha256={}),
        lambda p: p.update(scheduler_sha256={}),
        lambda p: p.update(unexpected=True),
    ],
)
def test_plan_rejects_drift_and_incomplete_bindings(plan, mutation):
    document = asdict(plan)
    mutation(document)
    with pytest.raises((once.PreflightError, TypeError)):
        once.ExecutionPlan.parse(json.dumps(document))


def test_reader_exact_parser(plan, reader, monkeypatch):
    path = Path(plan.reader_env)
    path.write_text("".join(f"{k}={v}\n" for k, v in reader.items()))
    path.chmod(0o600)
    monkeypatch.setattr(once, "_ancestors", Mock())
    # Exercise parser/fd binding with a synthetic file owned by the test user.
    monkeypatch.setattr(once, "_trusted", lambda p: p.lstat())
    os.utime(path, ns=(1, path.stat().st_mtime_ns))
    assert once.read_reader_environment(plan) == reader
    initial = path.read_text()
    for suffix in (
        "PMTS_RECOVERY_R2_BUCKET=duplicate\n",
        "UNEXPECTED=x\n",
        "# comment\n",
        "export X=y\n",
    ):
        path.write_text(initial + suffix)
        with pytest.raises(once.PreflightError):
            once.read_reader_environment(plan)
    path.write_text(initial)
    path.chmod(0o644)
    with pytest.raises(once.PreflightError):
        once.read_reader_environment(plan)


@pytest.mark.parametrize(
    "mode,uid,gid", [(0o100666, 0, 0), (0o100600, 1, 0), (0o100600, 0, 1), (0o120777, 0, 0)]
)
def test_trusted_metadata_rejects_permissions_owner_and_symlink(monkeypatch, mode, uid, gid):
    monkeypatch.setattr(
        Path, "lstat", lambda _: SimpleNamespace(st_mode=mode, st_uid=uid, st_gid=gid)
    )
    with pytest.raises(once.PreflightError):
        once._trusted(Path("/synthetic/file"))


def test_privilege_drop_command_and_clean_environment(plan, reader):
    command = once.child_command(plan, 9)
    for option in (
        "--clear-groups",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--bounding-set=-all",
        "--no-new-privs",
        "--kill-after=30s",
        "30m",
    ):
        assert option in command
    assert command[-9:] == [
        "/usr/bin/python3.12",
        "-S",
        "-B",
        "-P",
        "-u",
        "-m",
        "recovery.rotation_once",
        "--worker",
        "9",
    ]
    env = once.child_environment(plan, reader)
    assert set(env) == once._ENV_KEYS | {"PATH", "LANG", "LC_ALL", "TZ", "TMPDIR", "PYTHONPATH"}
    assert not any(reader[k] in command for k in once._ENV_KEYS)


@pytest.mark.parametrize(
    "returncode,stdout,expected",
    [
        (0, "attempt_finished_advisory\n", 0),
        (1, "attempt_started_blocked_or_failed\n", 1),
        (2, "preflight_failed_attempt_not_started\n", 2),
        (1, "", 3),
        (124, "", 3),
        (137, "", 3),
        (0, "unrecognized", 3),
    ],
)
def test_launcher_sanitized_child_protocol(
    plan, reader, worker_host, monkeypatch, returncode, stdout, expected
):
    monkeypatch.setattr(os, "getuid", lambda: 0)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "environ", once._BASE_ENV | {"PYTHONPATH": plan.code_root + "/src"})
    monkeypatch.setattr(once, "_destination_preflight", Mock())
    monkeypatch.setattr(once, "read_reader_environment", lambda _: reader)
    monkeypatch.setattr(once, "_open_reader", lambda *_: os.open(os.devnull, os.O_RDONLY))
    run = Mock(return_value=SimpleNamespace(returncode=returncode, stdout=stdout))
    monkeypatch.setattr(once.subprocess, "run", run)
    assert once.launch(plan, json.dumps(asdict(plan))) == expected
    run.assert_called_once()
    assert run.call_args.kwargs["env"] == once.child_environment(plan, reader)
    assert run.call_args.kwargs["stderr"] == once.subprocess.DEVNULL


def test_main_sanitizes_errors(monkeypatch, capsys):
    monkeypatch.setattr(once.sys, "stdin", StringIO("synthetic-sensitive-invalid-json"))
    assert once.main([]) == 2
    output = capsys.readouterr()
    assert output.out == "preflight_failed_attempt_not_started\n"
    assert output.err == ""


def test_scheduler_checks_content_and_active_state(plan, tmp_path, monkeypatch):
    unit = tmp_path / "unit"
    unit.write_text("synthetic-unit")
    plan = replace(
        plan, scheduler_sha256={str(unit): hashlib.sha256(unit.read_bytes()).hexdigest()}
    )
    monkeypatch.setattr(once, "_ancestors", Mock())
    monkeypatch.setattr(once, "_trusted", Mock())

    def run(command):
        if "--value" in command:
            return "activating"
        return "\n".join(f"{k}={v}" for k, v in plan.scheduler_properties[command[2]].items())

    monkeypatch.setattr(once, "_run", run)
    once._scheduler_preflight(plan)
    unit.write_text("changed-unit")
    with pytest.raises(once.PreflightError):
        once._scheduler_preflight(plan)


@pytest.mark.parametrize(
    "failure", ["revision", "dirty", "ignored", "skip_worktree", "module_path"]
)
def test_code_authority_currentness(plan, tmp_path, monkeypatch, failure):
    root = tmp_path / "code"
    (root / ".git").mkdir(parents=True)
    plan = replace(plan, code_root=str(root))
    monkeypatch.setattr(once, "_ancestors", Mock())
    monkeypatch.setattr(once, "_trusted", Mock())
    monkeypatch.setattr(
        once,
        "__file__",
        str(root / "src/recovery/rotation_once.py")
        if failure != "module_path"
        else "/other/rotation_once.py",
    )

    def run(command, **kwargs):
        if command[-1] == "--show-toplevel":
            return str(root)
        if command[-1] == "HEAD":
            return "f" * 40 if failure == "revision" else plan.revision
        if command[-1] == "--ignored":
            return {"dirty": " M tracked", "ignored": "!! ignored.py"}.get(failure, "")
        return "S skipped.py" if failure == "skip_worktree" else "H tracked.py"

    monkeypatch.setattr(once, "_run", run)
    with pytest.raises(once.PreflightError):
        once._code_preflight(plan)


@pytest.mark.parametrize("failure", ["uid", "groups", "no_new_privs", "capability", "write_access"])
def test_worker_identity_fails_closed(plan, monkeypatch, failure):
    for name, value in [
        ("getuid", plan.uid),
        ("geteuid", plan.uid),
        ("getgid", plan.gid),
        ("getegid", plan.gid),
    ]:
        monkeypatch.setattr(os, name, lambda value=value: value)
    if failure == "uid":
        monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "getgroups", lambda: [plan.gid] if failure == "groups" else [])
    state = {
        "NoNewPrivs": "0" if failure == "no_new_privs" else "1",
        "CapInh": "0",
        "CapPrm": "0",
        "CapEff": "0",
        "CapBnd": "0",
        "CapAmb": "0",
    }
    if failure == "capability":
        state["CapBnd"] = "1"
    monkeypatch.setattr(
        Path, "read_text", lambda _: "\n".join(f"{k}: {v}" for k, v in state.items())
    )
    monkeypatch.setattr(Path, "is_dir", lambda _: True)
    monkeypatch.setattr(Path, "is_symlink", lambda _: False)

    def access(path, mode):
        if str(path) == plan.recovery_root and mode == os.W_OK:
            return failure == "write_access"
        return True

    monkeypatch.setattr(os, "access", access)
    with pytest.raises(once.PreflightError):
        once._identity_preflight(plan)


@pytest.mark.parametrize("failure", ["missing", "owner", "mode", "path", "writer_fd", "value"])
def test_reader_descriptor_provenance(plan, reader, monkeypatch, failure):
    value = SimpleNamespace(st_mode=0o100600, st_uid=0, st_gid=0, st_nlink=1)
    if failure == "owner":
        value.st_uid = plan.uid
    if failure == "mode":
        value.st_mode = 0o100644
    monkeypatch.setattr(os, "fstat", lambda _: value)
    monkeypatch.setattr(once.fcntl, "fcntl", lambda *_: os.O_RDWR if failure == "writer_fd" else 0)
    monkeypatch.setattr(
        os, "readlink", lambda _: "/synthetic/writer.env" if failure == "path" else plan.reader_env
    )
    content = reader | (
        {"PMTS_RECOVERY_R2_ACCESS_KEY_ID": "different-synthetic"} if failure == "value" else {}
    )
    monkeypatch.setattr(
        os, "pread", lambda *_: "".join(f"{k}={v}\n" for k, v in content.items()).encode()
    )
    with pytest.raises(once.PreflightError):
        once._reader_fd_preflight(plan, None if failure == "missing" else 9, reader)
