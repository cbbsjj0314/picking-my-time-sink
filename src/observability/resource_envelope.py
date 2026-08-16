"""Read-only resource-envelope evidence for current PMTS recurring workloads."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.linux_proc import (
    LinuxProcReader,
    ProcessHeader,
    ProcessIdentity,
    ProcessSample,
    clock_ticks_per_second,
)

DEFAULT_OUTPUT_DIR = Path("tmp/observability/resource-envelope")
DEFAULT_STEAM_JOBS_DIR = Path("tmp/steam/jobs")
DEFAULT_CHZZK_WRAPPER_DIR = Path("tmp/chzzk/guarded-write-scheduler-wrapper")
TARGET_INTERVAL_MS = 100
DISCOVERY_INTERVAL_MS = 250
ARTIFACT_INTERVAL_MS = 1000
HANDOFF_ADDITIONAL_RETRY_LIMIT = 2
ARTIFACT_TOLERANCE_SECONDS = 2.0
STEAM_STATUSES = frozenset({"success", "partial_success", "lock_busy", "hard_failure"})
CHZZK_STATUSES = frozenset({"success", "partial_success", "hard_failure"})
DISCOVERY_COMMS = frozenset({"bash", "sh", "zsh", "poetry", "python", "python3", "python3.12"})


def utc_now_iso() -> str:
    """Return a human-readable UTC timestamp; never use it for durations."""

    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def boottime_ns() -> int:
    """Return the Linux monotonic clock used for lifecycle and gap calculations."""

    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


def parse_utc(value: object) -> dt.datetime | None:
    """Parse one existing result timestamp for correlation only."""

    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _safe_json(path: Path) -> tuple[str, Mapping[str, Any] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "missing", None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unreadable", None
    return ("present", payload) if isinstance(payload, Mapping) else ("unreadable", None)


def _timestamp_slug() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write private evidence with restrictive file permissions."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    """A sanitized workload identity and its narrow discovery rule."""

    workload_id: str
    kind: str
    steam_job_name: str | None = None


WORKLOADS = (
    WorkloadSpec("steam.ccu-30m", "steam", "ccu-30m"),
    WorkloadSpec("steam.price-1h", "steam", "price-1h"),
    WorkloadSpec("steam.daily", "steam", "daily"),
    WorkloadSpec("chzzk.fetch-load-guarded-write-30m", "chzzk"),
)


def _contains_tokens(cmdline: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    width = len(expected)
    return any(
        cmdline[index : index + width] == expected
        for index in range(len(cmdline) - width + 1)
    )


def match_workloads(cmdline: tuple[str, ...]) -> tuple[WorkloadSpec, ...]:
    """Classify a candidate cmdline without retaining it in evidence."""

    matches: list[WorkloadSpec] = []
    for spec in WORKLOADS:
        if spec.kind == "steam" and spec.steam_job_name and _contains_tokens(
            cmdline,
            ("-m", "steam.ingest.run_steam_cadence_job", spec.steam_job_name),
        ):
            matches.append(spec)
        if spec.kind == "chzzk" and any(
            Path(token).name == "run_chzzk_fetch_load_guarded_write_orchestration_wsl.sh"
            for token in cmdline
        ):
            matches.append(spec)
    return tuple(matches)


def tree_pids(
    root: ProcessIdentity,
    headers: Mapping[int, ProcessHeader],
) -> tuple[int, ...] | None:
    """Return a root's current descendants using PPID and stable identities."""

    current = headers.get(root.pid)
    if current is None or current.identity != root:
        return None
    children: dict[int, list[int]] = {}
    for header in headers.values():
        children.setdefault(header.ppid, []).append(header.identity.pid)
    discovered: list[int] = []
    pending = [root.pid]
    while pending:
        pid = pending.pop()
        if pid in discovered:
            continue
        discovered.append(pid)
        pending.extend(children.get(pid, ()))
    return tuple(sorted(discovered))


@dataclass(frozen=True, slots=True)
class StableTreeSample:
    """One accepted snapshot after child CPU handoff validation."""

    completed_boottime_ns: int
    samples: tuple[ProcessSample, ...]

    @property
    def rss_bytes(self) -> int:
        return sum(sample.vmrss_bytes for sample in self.samples)

    @property
    def cpu_ticks(self) -> tuple[int, int]:
        user = sum(
            sample.header.utime_ticks + sample.header.cutime_ticks for sample in self.samples
        )
        system = sum(
            sample.header.stime_ticks + sample.header.cstime_ticks for sample in self.samples
        )
        return user, system


@dataclass(frozen=True, slots=True)
class TreeSampleResult:
    """One sampling cycle's accepted snapshot and discarded handoff attempts."""

    sample: StableTreeSample | None
    handoff_retry_count: int = 0
    handoff_unstable_snapshot_count: int = 0
    handoff_retry_exhausted: bool = False


def _stable_tree_sample_attempt(
    reader: LinuxProcReader,
    root: ProcessIdentity,
    *,
    now_ns: Callable[[], int],
) -> tuple[StableTreeSample | None, bool]:
    """Return one proc snapshot and whether a CPU-handoff race invalidated it."""

    before = reader.headers()
    pids = tree_pids(root, before)
    if pids is None:
        return None, False
    samples: list[ProcessSample] = []
    for pid in pids:
        sample = reader.sample(before[pid])
        if sample is None:
            return None, False
        samples.append(sample)
    after = reader.headers()
    after_pids = tree_pids(root, after)
    if after_pids != pids:
        return None, True
    for pid in pids:
        prior = before[pid]
        current = after[pid]
        if prior.identity != current.identity or prior.child_cpu_ticks != current.child_cpu_ticks:
            return None, True
    return StableTreeSample(completed_boottime_ns=now_ns(), samples=tuple(samples)), False


def stable_tree_sample(
    reader: LinuxProcReader,
    root: ProcessIdentity,
    *,
    now_ns: Callable[[], int] = boottime_ns,
) -> TreeSampleResult:
    """Read a tree with at most two additional retries for CPU handoff races.

    A child-time change or membership transition while the tree is read makes the
    assembled proc view non-coherent. The two immediate retries keep observer
    perturbation bounded within the 100ms target sampling budget.
    """

    retries = 0
    unstable = 0
    while True:
        sample, handoff_unstable = _stable_tree_sample_attempt(reader, root, now_ns=now_ns)
        if sample is not None:
            return TreeSampleResult(
                sample=sample,
                handoff_retry_count=retries,
                handoff_unstable_snapshot_count=unstable,
            )
        if not handoff_unstable:
            return TreeSampleResult(
                sample=None,
                handoff_retry_count=retries,
                handoff_unstable_snapshot_count=unstable,
            )
        unstable += 1
        if retries >= HANDOFF_ADDITIONAL_RETRY_LIMIT:
            return TreeSampleResult(
                sample=None,
                handoff_retry_count=retries,
                handoff_unstable_snapshot_count=unstable,
                handoff_retry_exhausted=True,
            )
        retries += 1


def gap_threshold_ms(target_interval_ms: int) -> int:
    """Return the approved no-known-gap threshold for a target sample interval."""

    return max(250, target_interval_ms * 2)


@dataclass(slots=True)
class SamplingStats:
    target_interval_ms: int
    valid_sample_count: int = 0
    sample_attempt_count: int = 0
    invalid_snapshot_count: int = 0
    handoff_retry_count: int = 0
    handoff_unstable_snapshot_count: int = 0
    observed_sample_gap_count: int = 0
    max_observed_sample_gap_ms: int = 0
    over_threshold_sample_gap_count: int = 0
    total_sample_gap_excess_ms: int = 0
    max_snapshot_read_duration_ms: int = 0
    _previous_completion_ns: int | None = None

    def record(self, result: TreeSampleResult, *, started_ns: int) -> None:
        """Record one attempt and actual monotonic completion gap."""

        self.sample_attempt_count += 1
        self.handoff_retry_count += result.handoff_retry_count
        self.handoff_unstable_snapshot_count += result.handoff_unstable_snapshot_count
        completed_ns = boottime_ns()
        self.max_snapshot_read_duration_ms = max(
            self.max_snapshot_read_duration_ms,
            int((completed_ns - started_ns) / 1_000_000),
        )
        if result.sample is None:
            if result.handoff_retry_exhausted:
                self.invalid_snapshot_count += 1
            return
        sample = result.sample
        if self._previous_completion_ns is not None:
            gap_ms = int((sample.completed_boottime_ns - self._previous_completion_ns) / 1_000_000)
            threshold = gap_threshold_ms(self.target_interval_ms)
            self.observed_sample_gap_count += 1
            self.max_observed_sample_gap_ms = max(self.max_observed_sample_gap_ms, gap_ms)
            if gap_ms > threshold:
                self.over_threshold_sample_gap_count += 1
                self.total_sample_gap_excess_ms += gap_ms - threshold
        self._previous_completion_ns = sample.completed_boottime_ns
        self.valid_sample_count += 1


@dataclass(slots=True)
class ActiveRun:
    spec: WorkloadSpec
    root: ProcessIdentity
    root_pid: int
    started_boottime_ns: int
    first_sample_boottime_ns: int | None = None
    first_sample_at_utc: str | None = None
    last_sample_boottime_ns: int | None = None
    last_sample_at_utc: str | None = None
    exit_detected_boottime_ns: int | None = None
    exit_detected_at_utc: str | None = None
    peak_rss_bytes: int | None = None
    process_count_at_peak: int | None = None
    cpu_user_ticks: int | None = None
    cpu_system_ticks: int | None = None
    stats: SamplingStats = field(default_factory=lambda: SamplingStats(TARGET_INTERVAL_MS))
    reasons: set[str] = field(default_factory=set)
    overlap_ids: set[str] = field(default_factory=set)
    overlap_sample_count: int = 0
    peak_other_run_count: int = 0
    overlap_first_utc: str | None = None
    overlap_last_utc: str | None = None
    overlap_lower_bound_ms: int = 0
    last_valid_sample_cycle: int | None = None

    def record_sample(self, sample: StableTreeSample, *, at_utc: str) -> None:
        if self.first_sample_boottime_ns is None:
            self.first_sample_boottime_ns = sample.completed_boottime_ns
            self.first_sample_at_utc = at_utc
            if sample.completed_boottime_ns - self.started_boottime_ns > gap_threshold_ms(
                self.stats.target_interval_ms
            ) * 1_000_000:
                self.reasons.add("late_attach")
        self.last_sample_boottime_ns = sample.completed_boottime_ns
        self.last_sample_at_utc = at_utc
        if self.peak_rss_bytes is None or sample.rss_bytes > self.peak_rss_bytes:
            self.peak_rss_bytes = sample.rss_bytes
            self.process_count_at_peak = len(sample.samples)
        user, system = sample.cpu_ticks
        if self.cpu_user_ticks is None or (
            user + system > self.cpu_user_ticks + self.cpu_system_ticks
        ):
            self.cpu_user_ticks = user
            self.cpu_system_ticks = system


@dataclass(frozen=True, slots=True)
class ValidCycleSample:
    """The current valid sample and its immediately preceding valid evidence."""

    active: ActiveRun
    completed_boottime_ns: int
    previous_completed_boottime_ns: int | None
    previous_cycle: int | None


def _steam_correlation(
    spec: WorkloadSpec,
    *,
    started_at: dt.datetime | None,
    finished_at: dt.datetime | None,
    jobs_dir: Path,
) -> dict[str, Any]:
    if spec.steam_job_name is None or started_at is None or finished_at is None:
        return {"state": "unmatched", "contract": "steam_cadence_result_v1"}
    candidates: list[Mapping[str, Any]] = []
    unreadable = False
    for path in (jobs_dir / spec.steam_job_name).glob("*/result.json"):
        state, payload = _safe_json(path)
        if state == "unreadable":
            unreadable = True
            continue
        if state != "present" or payload is None or payload.get("job_name") != spec.steam_job_name:
            continue
        run_started = parse_utc(payload.get("started_at_utc"))
        run_finished = parse_utc(payload.get("finished_at_utc"))
        if run_started is None or run_finished is None:
            continue
        tolerance = dt.timedelta(seconds=ARTIFACT_TOLERANCE_SECONDS)
        if run_started <= finished_at + tolerance and run_finished >= started_at - tolerance:
            candidates.append(payload)
    if len(candidates) != 1:
        return {
            "state": "ambiguous" if candidates else "unreadable" if unreadable else "unmatched",
            "contract": "steam_cadence_result_v1",
        }
    candidate = candidates[0]
    status = candidate.get("status")
    if status not in STEAM_STATUSES:
        return {"state": "unreadable", "contract": "steam_cadence_result_v1"}
    return {
        "state": "matched",
        "contract": "steam_cadence_result_v1",
        "existing_run_id": (
            candidate.get("run_id") if isinstance(candidate.get("run_id"), str) else None
        ),
        "existing_result_status": status,
        "existing_duration_ms": (
            candidate.get("duration_ms")
            if isinstance(candidate.get("duration_ms"), int)
            else None
        ),
        "existing_run_started_at_utc": candidate.get("started_at_utc"),
        "existing_run_finished_at_utc": candidate.get("finished_at_utc"),
        "status_conflict": False,
    }


def _chzzk_correlation(root_pid: int, *, wrapper_dir: Path) -> dict[str, Any]:
    matches: list[tuple[str, Mapping[str, Any] | None, Mapping[str, Any] | None]] = []
    try:
        run_dirs = [path for path in wrapper_dir.iterdir() if path.is_dir()]
    except OSError:
        return {"state": "unreadable", "contract": "chzzk_guarded_wrapper_v1"}
    for run_dir in run_dirs:
        start_state, start = _safe_json(run_dir / "trace" / "start.json")
        if start_state != "present" or start is None:
            continue
        try:
            matches_pid = int(start.get("wrapper_pid")) == root_pid
        except (TypeError, ValueError):
            matches_pid = False
        if matches_pid:
            guarded_state, guarded = _safe_json(run_dir / "guarded-write-result.json")
            _, end = _safe_json(run_dir / "trace" / "end.json")
            matches.append((run_dir.name, guarded if guarded_state == "present" else None, end))
    if len(matches) != 1:
        return {
            "state": "ambiguous" if matches else "unmatched",
            "contract": "chzzk_guarded_wrapper_v1",
        }
    boundary_id, guarded, end = matches[0]
    if guarded is None:
        return {
            "state": "unreadable",
            "contract": "chzzk_guarded_wrapper_v1",
            "wrapper_boundary_id": boundary_id,
        }
    status = guarded.get("status") if guarded.get("status") in CHZZK_STATUSES else None
    if status is None:
        return {
            "state": "unreadable",
            "contract": "chzzk_guarded_wrapper_v1",
            "wrapper_boundary_id": boundary_id,
        }
    exit_state = "missing"
    exit_code: int | None = None
    if end is not None:
        try:
            exit_code = int(end.get("exit_code"))
            exit_state = "zero" if exit_code == 0 else "nonzero"
        except (TypeError, ValueError):
            exit_state = "invalid"
    conflict = status == "success" and exit_state == "nonzero"
    return {
        "state": "matched",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": boundary_id,
        "existing_run_id": (
            guarded.get("run_id") if isinstance(guarded.get("run_id"), str) else None
        ),
        "existing_result_status": status,
        "wrapper_exit_code_state": exit_state,
        "status_conflict": conflict,
    }


def correlate_run(
    active: ActiveRun,
    *,
    jobs_dir: Path,
    wrapper_dir: Path,
) -> dict[str, Any]:
    """Correlate only allowlisted existing-result fields; never infer status."""

    if active.spec.kind == "steam":
        return _steam_correlation(
            active.spec,
            started_at=parse_utc(active.first_sample_at_utc),
            finished_at=parse_utc(active.exit_detected_at_utc),
            jobs_dir=jobs_dir,
        )
    return _chzzk_correlation(active.root_pid, wrapper_dir=wrapper_dir)


def build_run_summary(
    active: ActiveRun,
    *,
    session_id: str,
    observation_id: str,
    ticks_per_second: int,
    correlation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a strict allowlisted summary that contains no proc raw fields."""

    if active.stats.over_threshold_sample_gap_count:
        active.reasons.add("sampling_gap_exceeded")
    if active.stats.handoff_unstable_snapshot_count and active.stats.invalid_snapshot_count:
        active.reasons.add("cpu_handoff_snapshot_unstable")
    state = "incomplete" if active.stats.valid_sample_count == 0 else "complete"
    if active.reasons or correlation.get("state") not in {"matched", "not_applicable"}:
        state = "partial" if state != "incomplete" else state
    if correlation.get("status_conflict") is True:
        active.reasons.add("existing_status_exit_conflict")
        state = "partial"
    user_seconds = (active.cpu_user_ticks or 0) / ticks_per_second
    system_seconds = (active.cpu_system_ticks or 0) / ticks_per_second
    elapsed_ms = 0
    if active.first_sample_boottime_ns is not None and active.exit_detected_boottime_ns is not None:
        elapsed_ms = int(
            (active.exit_detected_boottime_ns - active.first_sample_boottime_ns) / 1_000_000
        )
    start_age_ms = int(
        (
            (active.first_sample_boottime_ns or active.started_boottime_ns)
            - active.started_boottime_ns
        )
        / 1_000_000
    )
    exit_window_ms = 0
    if active.last_sample_boottime_ns is not None and active.exit_detected_boottime_ns is not None:
        exit_window_ms = int(
            (active.exit_detected_boottime_ns - active.last_sample_boottime_ns) / 1_000_000
        )
    return {
        "schema_version": "1",
        "session_id": session_id,
        "observation_id": observation_id,
        "workload": {"id": active.spec.workload_id, "origin_assertion": "process_signature_only"},
        "correlation": dict(correlation),
        "timing": {
            "first_sample_at_utc": active.first_sample_at_utc,
            "last_sample_at_utc": active.last_sample_at_utc,
            "process_exit_detected_at_utc": active.exit_detected_at_utc,
            "observed_elapsed_ms": elapsed_ms,
            "root_start_age_at_first_sample_ms": start_age_ms,
            "last_present_to_exit_detection_ms": exit_window_ms,
            "existing_run_started_at_utc": correlation.get("existing_run_started_at_utc"),
            "existing_run_finished_at_utc": correlation.get("existing_run_finished_at_utc"),
            "existing_duration_ms": correlation.get("existing_duration_ms"),
            "elapsed_clock": "linux_clock_boottime",
        },
        "memory": {
            "metric_kind": "maximum_sampled_sum_of_process_tree_vmrss",
            "peak_aggregate_rss_bytes": active.peak_rss_bytes,
            "process_count_at_peak": active.process_count_at_peak,
            "temporal_peak_may_be_missed": True,
            "shared_pages_may_be_double_counted": True,
            "vmrss_accounting_may_be_approximate": True,
        },
        "cpu": {
            "accounting_kind": "stable_proc_tree_self_plus_waited_children",
            "user_seconds": user_seconds if active.cpu_user_ticks is not None else None,
            "system_seconds": system_seconds if active.cpu_system_ticks is not None else None,
            "total_seconds": (
                user_seconds + system_seconds if active.cpu_user_ticks is not None else None
            ),
            "handoff_retry_count": active.stats.handoff_retry_count,
            "handoff_unstable_snapshot_count": active.stats.handoff_unstable_snapshot_count,
        },
        "sampling": {
            "measurement_method": "periodic_linux_proc_process_tree_snapshot",
            "target_interval_ms": active.stats.target_interval_ms,
            "gap_threshold_ms": gap_threshold_ms(active.stats.target_interval_ms),
            "sample_attempt_count": active.stats.sample_attempt_count,
            "valid_sample_count": active.stats.valid_sample_count,
            "invalid_snapshot_count": active.stats.invalid_snapshot_count,
            "observed_sample_gap_count": active.stats.observed_sample_gap_count,
            "max_observed_sample_gap_ms": active.stats.max_observed_sample_gap_ms,
            "over_threshold_sample_gap_count": active.stats.over_threshold_sample_gap_count,
            "total_sample_gap_excess_ms": active.stats.total_sample_gap_excess_ms,
            "max_snapshot_read_duration_ms": active.stats.max_snapshot_read_duration_ms,
            "scheduling_clock": "linux_clock_boottime",
        },
        "completeness": {
            "state": state,
            "meaning": "no_known_observation_contract_gap",
            "reasons": sorted(active.reasons),
        },
        "overlap": {
            "observed": bool(active.overlap_ids),
            "workload_ids": sorted(active.overlap_ids),
            "peak_other_run_count": active.peak_other_run_count,
            "first_observed_at_utc": active.overlap_first_utc,
            "last_observed_at_utc": active.overlap_last_utc,
            "sample_count": active.overlap_sample_count,
            "observed_overlap_lower_bound_ms": active.overlap_lower_bound_ms,
            "duration_clock": "linux_clock_boottime",
        },
        "sanitization": {
            "command_line_persisted": False,
            "environment_persisted": False,
            "host_identity_persisted": False,
            "filesystem_path_persisted": False,
            "raw_result_payload_persisted": False,
        },
    }


class ResourceEnvelopeObserver:
    """Observe matched workloads without becoming their parent or controller."""

    def __init__(
        self,
        *,
        reader: LinuxProcReader,
        output_dir: Path,
        duration_seconds: float,
        target_interval_ms: int = TARGET_INTERVAL_MS,
        discovery_interval_ms: int = DISCOVERY_INTERVAL_MS,
        jobs_dir: Path = DEFAULT_STEAM_JOBS_DIR,
        wrapper_dir: Path = DEFAULT_CHZZK_WRAPPER_DIR,
        explicit_pid: int | None = None,
        explicit_workload_id: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.reader = reader
        self.output_dir = output_dir
        self.duration_seconds = duration_seconds
        self.target_interval_ms = target_interval_ms
        self.discovery_interval_ms = discovery_interval_ms
        self.jobs_dir = jobs_dir
        self.wrapper_dir = wrapper_dir
        self.explicit_pid = explicit_pid
        self.explicit_workload_id = explicit_workload_id
        self.sleep = sleep
        self.session_id = _timestamp_slug()
        self.active: dict[ProcessIdentity, ActiveRun] = {}
        self.finished: list[dict[str, Any]] = []
        self._last_discovery_ns = 0

    @staticmethod
    def _process_started_boottime_ns(identity: ProcessIdentity) -> int:
        return identity.starttime_ticks * 1_000_000_000 // clock_ticks_per_second()

    def _discover(self, headers: Mapping[int, ProcessHeader], now: int) -> None:
        if self.explicit_pid is not None:
            header = headers.get(self.explicit_pid)
            if header is not None and header.identity not in self.active and not self.finished:
                spec = WorkloadSpec(self.explicit_workload_id or "synthetic.smoke", "synthetic")
                self.active[header.identity] = ActiveRun(
                    spec=spec,
                    root=header.identity,
                    root_pid=header.identity.pid,
                    started_boottime_ns=self._process_started_boottime_ns(header.identity),
                    stats=SamplingStats(self.target_interval_ms),
                )
            return
        if now - self._last_discovery_ns < self.discovery_interval_ms * 1_000_000:
            return
        self._last_discovery_ns = now
        matched: dict[int, WorkloadSpec] = {}
        for header in headers.values():
            if header.comm not in DISCOVERY_COMMS:
                continue
            cmdline = self.reader.cmdline(header.identity.pid)
            if cmdline is None:
                continue
            for spec in match_workloads(cmdline):
                matched[header.identity.pid] = spec
        for pid, spec in matched.items():
            root = headers[pid].identity
            ancestor = headers[pid].ppid
            while ancestor in matched and ancestor in headers:
                root = headers[ancestor].identity
                ancestor = headers[ancestor].ppid
            if root not in self.active:
                self.active[root] = ActiveRun(
                    spec=spec,
                    root=root,
                    root_pid=root.pid,
                    started_boottime_ns=self._process_started_boottime_ns(root),
                    stats=SamplingStats(self.target_interval_ms),
                )

    def _record_overlap(
        self,
        valid_samples: Mapping[ProcessIdentity, ValidCycleSample],
        *,
        cycle: int,
        at_utc: str,
    ) -> None:
        """Accumulate only intervals bounded by consecutive valid samples on both runs."""

        threshold_ns = gap_threshold_ms(self.target_interval_ms) * 1_000_000
        valid = list(valid_samples.values())
        for run in valid:
            qualifying: list[tuple[ValidCycleSample, int]] = []
            for other in valid:
                if other.active is run.active:
                    continue
                if run.previous_cycle != cycle - 1 or other.previous_cycle != cycle - 1:
                    continue
                if (
                    run.previous_completed_boottime_ns is None
                    or other.previous_completed_boottime_ns is None
                ):
                    continue
                run_gap_ns = run.completed_boottime_ns - run.previous_completed_boottime_ns
                other_gap_ns = other.completed_boottime_ns - other.previous_completed_boottime_ns
                if run_gap_ns > threshold_ns or other_gap_ns > threshold_ns:
                    continue
                interval_start = max(
                    run.previous_completed_boottime_ns,
                    other.previous_completed_boottime_ns,
                )
                interval_end = min(run.completed_boottime_ns, other.completed_boottime_ns)
                duration_ms = max(0, int((interval_end - interval_start) / 1_000_000))
                if duration_ms:
                    qualifying.append((other, duration_ms))
            if not qualifying:
                continue
            run.active.overlap_ids.update(other.active.spec.workload_id for other, _ in qualifying)
            run.active.peak_other_run_count = max(
                run.active.peak_other_run_count,
                len(qualifying),
            )
            run.active.overlap_sample_count += 1
            run.active.overlap_first_utc = run.active.overlap_first_utc or at_utc
            run.active.overlap_last_utc = at_utc
            run.active.overlap_lower_bound_ms += min(duration for _, duration in qualifying)

    def _finish(self, active: ActiveRun, *, at_ns: int, at_utc: str) -> None:
        active.exit_detected_boottime_ns = at_ns
        active.exit_detected_at_utc = at_utc
        if active.last_sample_boottime_ns is not None and (
            at_ns - active.last_sample_boottime_ns
        ) > gap_threshold_ms(self.target_interval_ms) * 1_000_000:
            active.reasons.add("exit_detection_gap_exceeded")
        correlation: Mapping[str, Any]
        if active.spec.kind == "synthetic":
            correlation = {"state": "not_applicable", "contract": "synthetic_pid_smoke"}
        else:
            correlation = correlate_run(
                active,
                jobs_dir=self.jobs_dir,
                wrapper_dir=self.wrapper_dir,
            )
        summary = build_run_summary(
            active,
            session_id=self.session_id,
            observation_id=f"{self.session_id}-{len(self.finished) + 1:03d}",
            ticks_per_second=clock_ticks_per_second(),
            correlation=correlation,
        )
        self.finished.append(summary)
        _write_private_json(
            self.output_dir / self.session_id / "runs" / f"{summary['observation_id']}.json",
            summary,
        )

    def _artifact_only_summary(self, spec: WorkloadSpec, correlation: Mapping[str, Any]) -> None:
        run_id = correlation.get("existing_run_id")
        if not isinstance(run_id, str):
            return
        if any(item["correlation"].get("existing_run_id") == run_id for item in self.finished):
            return
        active = ActiveRun(
            spec=spec,
            root=ProcessIdentity(0, 0),
            root_pid=0,
            started_boottime_ns=0,
            stats=SamplingStats(self.target_interval_ms),
        )
        active.reasons.add("process_not_observed")
        summary = build_run_summary(
            active,
            session_id=self.session_id,
            observation_id=f"{self.session_id}-{len(self.finished) + 1:03d}",
            ticks_per_second=clock_ticks_per_second(),
            correlation=correlation,
        )
        self.finished.append(summary)
        _write_private_json(
            self.output_dir / self.session_id / "runs" / f"{summary['observation_id']}.json",
            summary,
        )

    def _record_artifact_only_runs(self, started_at: str, finished_at: str) -> None:
        """Surface result artifacts created in-session when no process was seen."""

        session_start = parse_utc(started_at)
        session_end = parse_utc(finished_at)
        if session_start is None or session_end is None:
            return
        for spec in WORKLOADS:
            if spec.kind != "steam" or spec.steam_job_name is None:
                continue
            for path in (self.jobs_dir / spec.steam_job_name).glob("*/result.json"):
                state, payload = _safe_json(path)
                if state != "present" or payload is None:
                    continue
                result_finished = parse_utc(payload.get("finished_at_utc"))
                if result_finished is None or not session_start <= result_finished <= session_end:
                    continue
                correlation = _steam_correlation(
                    spec,
                    started_at=parse_utc(payload.get("started_at_utc")),
                    finished_at=result_finished,
                    jobs_dir=self.jobs_dir,
                )
                self._artifact_only_summary(spec, correlation)
        try:
            wrapper_runs = [path for path in self.wrapper_dir.iterdir() if path.is_dir()]
        except OSError:
            return
        spec = next(item for item in WORKLOADS if item.kind == "chzzk")
        for run_dir in wrapper_runs:
            guarded_state, guarded = _safe_json(run_dir / "guarded-write-result.json")
            if guarded_state != "present" or guarded is None:
                continue
            result_finished = parse_utc(guarded.get("finished_at_utc"))
            if result_finished is None or not session_start <= result_finished <= session_end:
                continue
            _, end = _safe_json(run_dir / "trace" / "end.json")
            status = guarded.get("status") if guarded.get("status") in CHZZK_STATUSES else None
            if status is None:
                continue
            try:
                exit_code = int((end or {}).get("exit_code"))
                exit_state = "zero" if exit_code == 0 else "nonzero"
            except (TypeError, ValueError):
                exit_state = "missing" if end is None else "invalid"
            correlation = {
                "state": "matched",
                "contract": "chzzk_guarded_wrapper_v1",
                "wrapper_boundary_id": run_dir.name,
                "existing_run_id": (
                    guarded.get("run_id") if isinstance(guarded.get("run_id"), str) else None
                ),
                "existing_result_status": status,
                "wrapper_exit_code_state": exit_state,
                "status_conflict": status == "success" and exit_state == "nonzero",
                "existing_run_started_at_utc": guarded.get("started_at_utc"),
                "existing_run_finished_at_utc": guarded.get("finished_at_utc"),
                "existing_duration_ms": (
                    guarded.get("duration_ms")
                    if isinstance(guarded.get("duration_ms"), int)
                    else None
                ),
            }
            self._artifact_only_summary(spec, correlation)

    def run(self) -> dict[str, Any]:
        """Run a bounded, sidecar-style observation session."""

        started_ns = boottime_ns()
        started_utc = utc_now_iso()
        deadline_ns = started_ns + int(self.duration_seconds * 1_000_000_000)
        clock_ticks_per_second()
        observer_failure: str | None = None
        cycle = 0
        while boottime_ns() < deadline_ns:
            cycle += 1
            loop_started = boottime_ns()
            now_utc = utc_now_iso()
            try:
                headers = self.reader.headers()
            except Exception:
                observer_failure = "proc_inventory_unavailable"
                for active in self.active.values():
                    active.reasons.add(observer_failure)
                break
            self._discover(headers, loop_started)
            valid_samples: dict[ProcessIdentity, ValidCycleSample] = {}
            for identity, active in list(self.active.items()):
                if identity.pid not in headers or headers[identity.pid].identity != identity:
                    self._finish(active, at_ns=loop_started, at_utc=now_utc)
                    del self.active[identity]
                    continue
                sample_started = boottime_ns()
                try:
                    result = stable_tree_sample(self.reader, identity)
                except Exception:
                    result = TreeSampleResult(sample=None)
                    active.reasons.add("proc_snapshot_unavailable")
                active.stats.record(result, started_ns=sample_started)
                if result.sample is not None:
                    valid_samples[identity] = ValidCycleSample(
                        active=active,
                        completed_boottime_ns=result.sample.completed_boottime_ns,
                        previous_completed_boottime_ns=active.last_sample_boottime_ns,
                        previous_cycle=active.last_valid_sample_cycle,
                    )
                    active.record_sample(result.sample, at_utc=now_utc)
                    active.last_valid_sample_cycle = cycle
                elif not result.handoff_unstable_snapshot_count:
                    active.reasons.add("proc_snapshot_unavailable")
            self._record_overlap(valid_samples, cycle=cycle, at_utc=now_utc)
            elapsed_ns = boottime_ns() - loop_started
            remaining_ns = self.target_interval_ms * 1_000_000 - elapsed_ns
            if remaining_ns > 0:
                self.sleep(remaining_ns / 1_000_000_000)
        ended_ns = boottime_ns()
        ended_utc = utc_now_iso()
        for identity, active in list(self.active.items()):
            active.reasons.add(observer_failure or "observer_stopped_while_active")
            self._finish(active, at_ns=ended_ns, at_utc=ended_utc)
            del self.active[identity]
        self._record_artifact_only_runs(started_utc, ended_utc)
        session = {
            "schema_version": "1",
            "session_id": self.session_id,
            "started_at_utc": started_utc,
            "finished_at_utc": ended_utc,
            "observer_status": "failed" if observer_failure else "completed",
            "failure_class": observer_failure,
            "target_interval_ms": self.target_interval_ms,
            "duration_clock": "linux_clock_boottime",
            "observed_run_count": len(self.finished),
            "run_refs": [f"runs/{item['observation_id']}.json" for item in self.finished],
            "sanitization": {
                "command_line_persisted": False,
                "environment_persisted": False,
                "host_identity_persisted": False,
                "filesystem_path_persisted": False,
            },
        }
        _write_private_json(self.output_dir / self.session_id / "session.json", session)
        return session


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded sidecar observer CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-sec", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-interval-ms", type=int, default=TARGET_INTERVAL_MS)
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--workload-id", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the observer without changing any target workload behavior."""

    args = build_parser().parse_args(argv)
    if args.duration_sec <= 0 or args.target_interval_ms <= 0:
        raise SystemExit("duration and target interval must be positive")
    if (args.pid is None) != (args.workload_id is None):
        raise SystemExit("--pid and --workload-id must be supplied together")
    if args.workload_id is not None and args.workload_id != "synthetic.smoke":
        raise SystemExit("explicit PID mode is limited to synthetic.smoke")
    observer = ResourceEnvelopeObserver(
        reader=LinuxProcReader(),
        output_dir=args.output_dir,
        duration_seconds=args.duration_sec,
        target_interval_ms=args.target_interval_ms,
        explicit_pid=args.pid,
        explicit_workload_id=args.workload_id,
    )
    print(json.dumps(observer.run(), ensure_ascii=True, sort_keys=True))


def raise_system_exit() -> None:
    """Keep signal handling out of target workloads."""

    raise SystemExit(130)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda _signal, _frame: raise_system_exit())
    main()
