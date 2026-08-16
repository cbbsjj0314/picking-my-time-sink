"""Small Linux ``/proc`` reader used by the resource-envelope observer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """A PID paired with its Linux start tick to prevent PID reuse confusion."""

    pid: int
    starttime_ticks: int


@dataclass(frozen=True, slots=True)
class ProcessHeader:
    """The stat fields needed for ancestry and CPU handoff validation."""

    identity: ProcessIdentity
    ppid: int
    comm: str
    utime_ticks: int
    stime_ticks: int
    cutime_ticks: int
    cstime_ticks: int

    @property
    def child_cpu_ticks(self) -> tuple[int, int]:
        return self.cutime_ticks, self.cstime_ticks


@dataclass(frozen=True, slots=True)
class ProcessSample:
    """A process header plus current VmRSS for one tree snapshot."""

    header: ProcessHeader
    vmrss_bytes: int


class ProcReadError(RuntimeError):
    """Raised when a required proc file cannot be read consistently."""


def clock_ticks_per_second() -> int:
    """Return the running Linux host's configured CPU tick rate."""

    value = os.sysconf("SC_CLK_TCK")
    if not isinstance(value, int) or value <= 0:
        raise RuntimeError("invalid_SC_CLK_TCK")
    return value


def parse_stat(raw: str) -> ProcessHeader:
    """Parse a Linux proc stat row without assuming a simple command name."""

    close = raw.rfind(")")
    open_index = raw.find("(")
    if open_index <= 0 or close <= open_index:
        raise ValueError("invalid_proc_stat")
    try:
        pid = int(raw[:open_index].strip())
        comm = raw[open_index + 1 : close]
        fields = raw[close + 1 :].split()
        # fields[0] is state (field 3), so field n maps to fields[n - 3].
        ppid = int(fields[1])
        utime = int(fields[11])
        stime = int(fields[12])
        cutime = int(fields[13])
        cstime = int(fields[14])
        starttime = int(fields[19])
    except (IndexError, ValueError) as exc:
        raise ValueError("invalid_proc_stat") from exc
    return ProcessHeader(
        identity=ProcessIdentity(pid=pid, starttime_ticks=starttime),
        ppid=ppid,
        comm=comm,
        utime_ticks=utime,
        stime_ticks=stime,
        cutime_ticks=cutime,
        cstime_ticks=cstime,
    )


def parse_vmrss_bytes(raw: str) -> int:
    """Return ``VmRSS`` in bytes from a Linux proc status payload."""

    for line in raw.splitlines():
        if not line.startswith("VmRSS:"):
            continue
        fields = line.split()
        if len(fields) != 3 or fields[2] != "kB":
            break
        try:
            value = int(fields[1])
        except ValueError as exc:
            raise ValueError("invalid_VmRSS") from exc
        if value < 0:
            raise ValueError("invalid_VmRSS")
        return value * 1024
    raise ValueError("VmRSS_missing")


class LinuxProcReader:
    """Read only the narrow Linux proc fields needed by this observer."""

    def __init__(self, proc_root: Path = Path("/proc")) -> None:
        self.proc_root = proc_root

    def headers(self) -> dict[int, ProcessHeader]:
        """Return readable process stat headers without reading any cmdline."""

        result: dict[int, ProcessHeader] = {}
        try:
            entries = list(self.proc_root.iterdir())
        except OSError as exc:
            raise ProcReadError("proc_inventory_unavailable") from exc
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                header = parse_stat((entry / "stat").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            result[header.identity.pid] = header
        return result

    def cmdline(self, pid: int) -> tuple[str, ...] | None:
        """Read a NUL-delimited cmdline only for a pre-filtered candidate."""

        try:
            raw = (self.proc_root / str(pid) / "cmdline").read_bytes()
        except OSError:
            return None
        if not raw:
            return ()
        return tuple(part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part)

    def sample(self, header: ProcessHeader) -> ProcessSample | None:
        """Read a process's current stat and VmRSS if its identity is unchanged."""

        process_dir = self.proc_root / str(header.identity.pid)
        try:
            current = parse_stat((process_dir / "stat").read_text(encoding="utf-8"))
            if current.identity != header.identity:
                return None
            vmrss = parse_vmrss_bytes((process_dir / "status").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return ProcessSample(header=current, vmrss_bytes=vmrss)
