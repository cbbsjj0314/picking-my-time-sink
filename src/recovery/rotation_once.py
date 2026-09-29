"""Gated one-shot launcher; stdin carries reviewed non-secret execution bindings."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from recovery.r2_activation import load_recovery_r2_config
from recovery.rotation_collect import CollectionAuthority, CollectionLimits, collect_inventory
from recovery.rotation_dryrun import PinSnapshot
from steam.ingest.s3_compat import S3CompatibleObjectStoreClient

_ENV_KEYS = frozenset(
    "PMTS_RECOVERY_R2_" + suffix
    for suffix in ("ENDPOINT_URL", "BUCKET", "REGION", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")
)
_BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"}
_TOOLS = (
    "/usr/bin/python3.12",
    "/usr/bin/setpriv",
    "/usr/bin/timeout",
    "/usr/bin/git",
    "/usr/bin/systemctl",
)
_PLAN_BYTES = 65536


class PreflightError(Exception):
    """Details must never cross the operator output boundary."""


def _require(condition: bool) -> None:
    if not condition:
        raise PreflightError()


def _unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


@dataclass(frozen=True)
class ExecutionPlan:
    code_root: str
    revision: str
    grant_ref: str
    recovery_root: str
    evidence_parent: str
    attempt_id: str
    reader_env: str
    endpoint: str
    bucket: str
    uid: int
    gid: int
    limits: dict
    tool_sha256: dict
    scheduler_properties: dict
    scheduler_sha256: dict

    @classmethod
    def parse(cls, payload: str) -> ExecutionPlan:
        _require(len(payload.encode()) <= _PLAN_BYTES)
        plan = cls(**json.loads(payload, object_pairs_hook=_unique))
        for value in (plan.code_root, plan.recovery_root, plan.evidence_parent, plan.reader_env):
            _require(isinstance(value, str) and Path(value).is_absolute())
            _require(str(Path(value)) == value and ".." not in Path(value).parts)
        _require(re.fullmatch(r"[0-9a-f]{40}", plan.revision) is not None)
        _require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", plan.attempt_id) is not None)
        # Grant reference is an immutable private ticket revision, not an approval inferred here.
        _require(
            re.fullmatch(r"[0-9a-f]{40}:A7-PHASE3-PROD-READONLY-HANDOFF-01", plan.grant_ref)
            is not None
        )
        _require(Path(plan.reader_env).name == "recovery-r2-readonly.env")
        _require(type(plan.uid) is int and plan.uid > 0)
        _require(type(plan.gid) is int and plan.gid > 0)
        CollectionLimits(**plan.limits).validate()
        _require(set(plan.tool_sha256) == set(_TOOLS))
        _require(all(re.fullmatch(r"[0-9a-f]{64}", v) for v in plan.tool_sha256.values()))
        _require(
            set(plan.scheduler_properties)
            == {"pmts-postgres-recovery.timer", "pmts-postgres-recovery.service"}
        )
        for unit, properties in plan.scheduler_properties.items():
            _require(isinstance(properties, dict) and bool(properties))
            _require(
                all(
                    isinstance(k, str) and re.fullmatch(r"[A-Za-z]+", k) and isinstance(v, str)
                    for k, v in properties.items()
                )
            )
            _require(properties.get("LoadState") == "loaded")
            _require(properties.get("NeedDaemonReload") == "no")
            _require(bool(properties.get("FragmentPath")))
            _require("DropInPaths" in properties)
            _require("UnitFileState" in properties)
            if unit.endswith(".timer"):
                _require(properties.get("ActiveState") == "active")
                _require(properties.get("UnitFileState") == "enabled")
                _calendar_specs(properties.get("TimersCalendar", ""))
            else:
                _require(properties.get("User") == "pmts")
                _require(properties.get("Restart") == "no")
        paths = set()
        for properties in plan.scheduler_properties.values():
            paths.add(properties["FragmentPath"])
            paths.update(properties["DropInPaths"].split())
        _require(set(plan.scheduler_sha256) == paths)
        _require(all(re.fullmatch(r"[0-9a-f]{64}", v) for v in plan.scheduler_sha256.values()))
        root, parent = Path(plan.recovery_root), Path(plan.evidence_parent)
        _require(not parent.is_relative_to(root) and not root.is_relative_to(parent))
        code = Path(plan.code_root)
        _require(
            all(
                not a.is_relative_to(b) and not b.is_relative_to(a)
                for a, b in ((code, root), (code, parent))
            )
        )
        _require(not Path(plan.reader_env).is_relative_to(root))
        _require(not Path(plan.reader_env).is_relative_to(parent))
        return plan

    @property
    def attempt_dir(self) -> Path:
        return Path(self.evidence_parent) / self.attempt_id


def output_budget(limits: CollectionLimits) -> int:
    # Budget, not a claim that every possible metadata representation will fit.
    # Two local name inventories (NAME_MAX=255), two bounded LIST transcripts,
    # and one manifest-sized metadata allowance per local/remote generation.
    # JSON escaping can expand one input byte to six ASCII bytes.
    n = limits.max_local_entries
    return 6 * (
        2 * n * (n + 1) * 255
        + 2 * limits.max_pages * limits.max_page_bytes
        + (n + limits.max_objects) * 65536
    )


def capacity_required(limits: CollectionLimits, block_size: int) -> tuple[int, int]:
    _require(block_size > 0)
    # Persistent capture + both concurrent A2 copies + enforced output cap.
    payload = (
        limits.max_local_bytes + 2 * (limits.max_dump_bytes + 65536 + 256) + output_budget(limits)
    )
    # N captures each have 1 directory + 3 files. Attempt/captures, two A2
    # roots/generations/three files, and three output files add 15 nodes.
    nodes = 4 * limits.max_local_entries + 15
    # Per-node allocation rounding only; XFS metadata uses a separate residual floor.
    return payload + nodes * block_size, nodes


def _calendar_specs(value: str) -> tuple[str, ...]:
    # systemctl show prints one record per configured calendar, including a transient time.
    specs = []
    for line in value.splitlines():
        match = re.fullmatch(r"\{ OnCalendar=([^{};\n]+) ; next_elapse=[^{};\n]* \}", line)
        _require(match is not None)
        spec = match[1].strip()
        _require(bool(spec))
        specs.append(spec)
    _require(bool(specs))
    return tuple(sorted(specs))


def _trusted(path: Path, *, directory: bool = False) -> os.stat_result:
    value = path.lstat()
    _require(stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode))
    _require(value.st_uid == 0 and value.st_gid == 0 and not value.st_mode & 0o022)
    return value


def _trusted_ancestor(path: Path) -> None:
    value = path.lstat()
    _require(stat.S_ISDIR(value.st_mode))
    _require(value.st_uid == 0 and not value.st_mode & 0o022)


def _ancestors(path: Path) -> None:
    for parent in reversed(path.parents):
        _trusted_ancestor(parent)


def _run(command: list[str], *, env: dict | None = None) -> str:
    result = subprocess.run(
        command,
        env=env or _BASE_ENV,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=15,
        check=True,
    )
    return result.stdout.strip()


def _code_preflight(plan: ExecutionPlan) -> None:
    root = Path(plan.code_root)
    _ancestors(root)
    _trusted(root, directory=True)
    # Independent checkout only: no writable ignored modules, linked worktree or symlink imports.
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            _trusted(Path(parent) / name, directory=True)
        for name in files:
            _trusted(Path(parent) / name)
    _trusted(root / ".git", directory=True)
    env = _BASE_ENV | {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    git = [
        "/usr/bin/git",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "safe.directory=" + str(root),
        "-C",
        str(root),
    ]
    _require(_run(git + ["rev-parse", "--show-toplevel"], env=env) == str(root))
    _require(_run(git + ["rev-parse", "HEAD"], env=env) == plan.revision)
    _require(
        not _run(git + ["status", "--porcelain", "--untracked-files=all", "--ignored"], env=env)
    )
    _require(
        all(line.startswith("H ") for line in _run(git + ["ls-files", "-v"], env=env).splitlines())
    )
    _require(not (root / ".git/objects/info/alternates").exists())
    _require(Path(__file__) == root / "src/recovery/rotation_once.py")


def _runtime_preflight(plan: ExecutionPlan) -> None:
    _require(sys.version_info[:2] == (3, 12))
    _require(Path(sys.executable).resolve() == Path("/usr/bin/python3.12").resolve())
    _require(getattr(sys.stdout, "write_through", False))
    _require(sys.flags.no_site and sys.flags.dont_write_bytecode and sys.flags.safe_path)
    for name, digest in plan.tool_sha256.items():
        path = Path(name).resolve(strict=True)
        _ancestors(path)
        value = _trusted(path)
        _require(bool(value.st_mode & 0o111))
        with path.open("rb") as source:
            _require(hashlib.file_digest(source, "sha256").hexdigest() == digest)
    identity = pwd.getpwnam("pmts")
    _require((identity.pw_uid, identity.pw_gid) == (plan.uid, plan.gid))


def _scheduler_preflight(plan: ExecutionPlan) -> None:
    for name, digest in plan.scheduler_sha256.items():
        path = Path(name)
        _ancestors(path)
        _trusted(path)
        with path.open("rb") as source:
            _require(hashlib.file_digest(source, "sha256").hexdigest() == digest)
    for unit, expected in plan.scheduler_properties.items():
        output = _run(
            [
                "/usr/bin/systemctl",
                "show",
                unit,
                "--no-pager",
                "--property=" + ",".join(sorted(expected)),
            ]
        )
        actual = {}
        calendars = []
        for line in output.splitlines():
            key, value = line.split("=", 1)
            if key == "TimersCalendar":
                calendars.extend(_calendar_specs(value))
            else:
                _require(key not in actual)
                actual[key] = value
        stable = dict(expected)
        if "TimersCalendar" in stable:
            stable["TimersCalendar"] = _calendar_specs(stable["TimersCalendar"])
        if calendars:
            actual["TimersCalendar"] = tuple(sorted(calendars))
        _require(actual == stable)
    # A running oneshot remains compatible; failed/deactivating scheduler does not.
    state = _run(
        [
            "/usr/bin/systemctl",
            "show",
            "pmts-postgres-recovery.service",
            "--property=ActiveState",
            "--value",
        ]
    )
    _require(state in {"active", "activating", "inactive"})


def _xfs_capacity(fd: int) -> tuple[int, int, int, int]:
    # The fixed ioctl layouts below use the Linux x86_64/aarch64 native ABI.
    _require(sys.platform == "linux" and os.uname().machine in {"x86_64", "aarch64"})
    _require(struct.calcsize("P") == 8 and sys.byteorder == "little")
    info = _unique(
        [line.split(":", 1) for line in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()]
    )
    mount_id = info["mnt_id"].strip()
    _require(mount_id.isdecimal())
    mounts = [
        line.split()
        for line in Path("/proc/self/mountinfo").read_text().splitlines()
        if line.split()[0] == mount_id
    ]
    _require(len(mounts) == 1)
    mount = mounts[0]
    separator = mount.index("-")
    _require(separator >= 6 and len(mount) == separator + 4)
    value = os.fstat(fd)
    _require(mount[2] == f"{os.major(value.st_dev)}:{os.minor(value.st_dev)}")
    _require(mount[separator + 1] == "xfs")
    options = set(mount[5].split(",")) | set(mount[separator + 3].split(","))
    _require("rw" in options and "ro" not in options and "noquota" in options)
    _require(
        not any(
            option != "noquota" and ("quota" in option or "qnoenforce" in option)
            for option in options
        )
    )
    # XFS_IOC_FSGEOMETRY_V1 = _IOR('X', 100, struct xfs_fsop_geom_v1), size 112.
    geometry = bytearray(112)
    fcntl.ioctl(fd, 0x80705864, geometry)
    block_size = struct.unpack_from("=I", geometry)[0]
    data_blocks, rt_blocks, rt_extents = struct.unpack_from("=QQQ", geometry, 32)
    dir_block_size = struct.unpack_from("=I", geometry, 104)[0]
    _require(block_size == dir_block_size == 4096 and data_blocks > 0)
    _require(rt_blocks == rt_extents == 0)
    # FS_IOC_FSGETXATTR: reject REALTIME / RTINHERIT on the destination itself.
    attributes = bytearray(28)
    fcntl.ioctl(fd, 0x801C581F, attributes)
    _require(not struct.unpack_from("=I", attributes)[0] & 0x101)
    fs = os.fstatvfs(fd)
    _require(fs.f_frsize == fs.f_bsize == block_size)
    _require(0 <= fs.f_bavail <= fs.f_bfree <= fs.f_blocks <= data_blocks)
    _require(0 <= fs.f_favail <= fs.f_ffree <= fs.f_files)
    return block_size, data_blocks, fs.f_bavail, fs.f_favail


def _destination_preflight(plan: ExecutionPlan) -> None:
    parent = Path(plan.evidence_parent)
    _ancestors(parent)
    value = parent.lstat()
    _require(stat.S_ISDIR(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o770)
    _require((value.st_uid, value.st_gid) == (0, plan.gid))
    _require(not os.path.lexists(plan.attempt_dir))
    limits = CollectionLimits(**plan.limits)
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _require(_file_identity(os.fstat(fd)) == _file_identity(value))
        block_size, data_blocks, available_blocks, available_nodes = _xfs_capacity(fd)
        needed, nodes = capacity_required(limits, block_size)
        attempt_blocks = (needed + block_size - 1) // block_size
        # XFS low-space safety floor, not an exact metadata bound or a reservation.
        residual_floor = (data_blocks + 19) // 20
        _require(available_blocks >= attempt_blocks + residual_floor and available_nodes >= nodes)
    finally:
        os.close(fd)


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    # Reading may legitimately advance atime; content/authority metadata must not change.
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_reader_environment(plan: ExecutionPlan) -> dict[str, str]:
    path = Path(plan.reader_env)
    _ancestors(path)
    before = _trusted(path)
    _require(stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        _require(_file_identity(os.fstat(source.fileno())) == _file_identity(before))
        payload = source.read(_PLAN_BYTES + 1)
        _require(
            len(payload) <= _PLAN_BYTES
            and _file_identity(os.fstat(source.fileno())) == _file_identity(before)
        )
    return _parse_reader(plan, payload)


def _parse_reader(plan: ExecutionPlan, payload: bytes) -> dict[str, str]:
    _require(len(payload) <= _PLAN_BYTES)
    # Never source shell text: no expansion, quoting, comments, duplicates or optional keys.
    values = {}
    for line in payload.decode("utf-8").splitlines():
        key, separator, value = line.partition("=")
        _require(separator == "=" and key in _ENV_KEYS and key not in values)
        _require(bool(value) and all(33 <= ord(c) <= 126 and c not in "'\"`$\\" for c in value))
        values[key] = value
    validate_config(plan, values)
    return values


def validate_config(plan: ExecutionPlan, values: dict):
    _require(set(values) == _ENV_KEYS)
    config = load_recovery_r2_config(values)
    _require(config.endpoint_url == plan.endpoint and config.bucket == plan.bucket)
    _require(config.region == "auto" and config.key_prefix == "")
    return config


def child_environment(plan: ExecutionPlan, reader: dict) -> dict:
    return (
        _BASE_ENV | {"TMPDIR": plan.evidence_parent, "PYTHONPATH": plan.code_root + "/src"} | reader
    )


def child_command(plan: ExecutionPlan, reader_fd: int) -> list[str]:
    return [
        "/usr/bin/setpriv",
        "--reuid=pmts",
        "--regid=pmts",
        "--clear-groups",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--bounding-set=-all",
        "--no-new-privs",
        "/usr/bin/timeout",
        "--signal=TERM",
        "--kill-after=30s",
        "30m",
        "/usr/bin/python3.12",
        "-S",
        "-B",
        "-P",
        "-u",
        "-m",
        "recovery.rotation_once",
        "--worker",
        str(reader_fd),
    ]


def _identity_preflight(plan: ExecutionPlan) -> None:
    _require(
        (os.getuid(), os.geteuid(), os.getgid(), os.getegid())
        == (plan.uid, plan.uid, plan.gid, plan.gid)
    )
    _require(not os.getgroups())
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    _require(status["NoNewPrivs"].strip() == "1")
    _require(
        all(
            int(status[key].strip(), 16) == 0
            for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        )
    )
    _require(os.access(plan.evidence_parent, os.R_OK | os.W_OK | os.X_OK))
    for parent in Path(plan.recovery_root).parents:
        _require(not parent.is_symlink())
    for name, writable in (("", False), ("completed", True), ("staging", True)):
        path = Path(plan.recovery_root) / name
        _require(path.is_dir() and not path.is_symlink())
        _require(os.access(path, os.R_OK | os.X_OK))
        _require(os.access(path, os.W_OK) == writable)


def _reader_fd_preflight(plan: ExecutionPlan, fd: int | None, reader: dict) -> None:
    # A direct pmts invocation cannot manufacture a root-owned reader descriptor.
    _require(type(fd) is int and fd >= 3)
    value = os.fstat(fd)
    _require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY)
    _require(stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o600)
    _require(value.st_uid == value.st_gid == 0 and value.st_nlink == 1)
    _require(os.readlink(f"/proc/self/fd/{fd}") == plan.reader_env)
    _require(_parse_reader(plan, os.pread(fd, _PLAN_BYTES + 1, 0)) == reader)
    _require(_file_identity(os.fstat(fd)) == _file_identity(value))


def _open_reader(plan: ExecutionPlan, reader: dict) -> int:
    fd = os.open(plan.reader_env, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        _reader_fd_preflight(plan, fd, reader)
    except Exception:
        os.close(fd)
        raise
    return fd


def run_worker(
    plan: ExecutionPlan, *, reader_fd=None, environ=None, collector=None, client_factory=None
) -> int:
    started = False
    try:
        values = dict(os.environ if environ is None else environ)
        reader = {key: values[key] for key in _ENV_KEYS}
        _require(values == child_environment(plan, reader))
        config = validate_config(plan, reader)
        _reader_fd_preflight(plan, reader_fd, reader)
        _identity_preflight(plan)
        _runtime_preflight(plan)
        _code_preflight(plan)
        _scheduler_preflight(plan)
        _destination_preflight(plan)
        # Serialize this caller only, without a persistent lock file or scheduler lock.
        fd = os.open(plan.evidence_parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _destination_preflight(plan)
            tempfile.tempdir = plan.evidence_parent
            os.umask(0o077)
            client = (client_factory or S3CompatibleObjectStoreClient)(config)
            limits = CollectionLimits(**plan.limits)
            authority = CollectionAuthority(
                handoff_ref=plan.grant_ref,
                target_ref=plan.grant_ref + "#target",
                r2_read_only_ref=plan.grant_ref + "#reader",
                local_identity_ref=plan.grant_ref + "#local-identity",
                local_write_capable=True,
            )
            pins = PinSnapshot(authority_ref=plan.grant_ref + "#pins-none", confirmed=True, pins=())
            started = True
            result = (collector or collect_inventory)(
                recovery_root=Path(plan.recovery_root),
                attempt_dir=plan.attempt_dir,
                client=client,
                authority=authority,
                limits=limits,
                pins=pins,
                snapshot_id=plan.attempt_id,
                evidence_ref=str(plan.attempt_dir / "evidence.json"),
                max_output_bytes=output_budget(limits),
            )
            return 0 if json.loads(result.report_json)["candidate_set_status"] == "advisory" else 1
        finally:
            os.close(fd)
    except (Exception, KeyboardInterrupt):
        return 1 if started else 2


def launch(plan: ExecutionPlan, payload: str) -> int:
    _require(os.getuid() == 0 and os.geteuid() == 0)
    _require(dict(os.environ) == _BASE_ENV | {"PYTHONPATH": plan.code_root + "/src"})
    _runtime_preflight(plan)
    _code_preflight(plan)
    _scheduler_preflight(plan)
    _destination_preflight(plan)
    reader = read_reader_environment(plan)
    os.umask(0o077)
    reader_fd = _open_reader(plan, reader)
    try:
        result = subprocess.run(
            child_command(plan, reader_fd),
            pass_fds=(reader_fd,),
            input=payload,
            text=True,
            env=child_environment(plan, reader),
            cwd=plan.code_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (Exception, KeyboardInterrupt):
        return 3
    finally:
        os.close(reader_fd)
    # An abnormal launcher/timeout exit cannot establish whether first access occurred.
    expected = {
        0: "attempt_finished_advisory",
        1: "attempt_started_blocked_or_failed",
        2: "preflight_failed_attempt_not_started",
    }
    return (
        result.returncode
        if result.returncode in expected and result.stdout.strip() == expected[result.returncode]
        else 3
    )


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        _require(not args or (len(args) == 2 and args[0] == "--worker"))
        payload = sys.stdin.read(_PLAN_BYTES + 1)
        plan = ExecutionPlan.parse(payload)
        code = run_worker(plan, reader_fd=int(args[1])) if args else launch(plan, payload)
    except (Exception, KeyboardInterrupt):
        code = 2
    labels = {
        0: "attempt_finished_advisory",
        1: "attempt_started_blocked_or_failed",
        2: "preflight_failed_attempt_not_started",
        3: "attempt_state_unknown_no_retry",
    }
    print(labels[code])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
