from __future__ import annotations

from pathlib import Path

from observability import linux_proc
from observability.linux_proc import (
    ProcessHeader,
    ProcessIdentity,
    ProcessSample,
    parse_stat,
    parse_vmrss_bytes,
)
from observability.resource_envelope import (
    HANDOFF_ADDITIONAL_RETRY_LIMIT,
    ActiveRun,
    ResourceEnvelopeObserver,
    SamplingStats,
    StableTreeSample,
    WorkloadSpec,
    build_run_summary,
    stable_tree_sample,
)


def header(
    pid: int,
    *,
    ppid: int = 1,
    start: int = 1,
    user: int = 0,
    system: int = 0,
    child_user: int = 0,
    child_system: int = 0,
) -> ProcessHeader:
    return ProcessHeader(
        identity=ProcessIdentity(pid, start),
        ppid=ppid,
        comm="python",
        utime_ticks=user,
        stime_ticks=system,
        cutime_ticks=child_user,
        cstime_ticks=child_system,
    )


class FakeReader:
    def __init__(
        self,
        snapshots: list[dict[int, ProcessHeader]],
        rss: dict[int, int],
        *,
        failed_sample_calls: set[int] | None = None,
    ) -> None:
        self.snapshots = snapshots
        self.rss = rss
        self.index = 0
        self.failed_sample_calls = failed_sample_calls or set()
        self.sample_index = 0

    def headers(self) -> dict[int, ProcessHeader]:
        result = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return result

    def sample(self, item: ProcessHeader) -> ProcessSample | None:
        self.sample_index += 1
        if self.sample_index in self.failed_sample_calls:
            return None
        return ProcessSample(item, self.rss[item.identity.pid])


def test_parse_stat_accepts_parentheses_and_spaces_in_comm() -> None:
    fields = ["S", "12"] + ["0"] * 18
    fields[11] = "10"
    fields[12] = "3"
    fields[13] = "4"
    fields[14] = "2"
    fields[19] = "99"

    parsed = parse_stat("42 (name with ) parenthesis) " + " ".join(fields))

    assert parsed.identity == ProcessIdentity(42, 99)
    assert parsed.ppid == 12
    assert parsed.child_cpu_ticks == (4, 2)


def test_parse_vmrss_uses_linux_kib_units() -> None:
    assert parse_vmrss_bytes("Name:\tpython\nVmRSS:\t123 kB\n") == 123 * 1024


def test_clock_ticks_per_second_uses_runtime_sysconf(monkeypatch) -> None:
    monkeypatch.setattr(linux_proc.os, "sysconf", lambda name: 250 if name == "SC_CLK_TCK" else 0)

    assert linux_proc.clock_ticks_per_second() == 250


def test_direct_child_cpu_handoff_is_counted_once_before_and_after_reap() -> None:
    root_live = header(10, user=5, system=2)
    child_live = header(11, ppid=10, user=7, system=3)
    live_reader = FakeReader([{10: root_live, 11: child_live}] * 2, {10: 100, 11: 200})
    live = stable_tree_sample(live_reader, root_live.identity, now_ns=lambda: 100)

    root_reaped = header(10, user=5, system=2, child_user=7, child_system=3)
    reaped_reader = FakeReader([{10: root_reaped}] * 2, {10: 100})
    reaped = stable_tree_sample(reaped_reader, root_reaped.identity, now_ns=lambda: 200)

    assert live.sample is not None and reaped.sample is not None
    assert live.sample.cpu_ticks == reaped.sample.cpu_ticks == (12, 5)


def test_nested_descendant_handoff_is_counted_once_at_each_stable_state() -> None:
    root = header(10, user=1)
    child = header(11, ppid=10, user=2)
    grandchild = header(12, ppid=11, user=3)
    all_live = stable_tree_sample(
        FakeReader([{10: root, 11: child, 12: grandchild}] * 2, {10: 1, 11: 1, 12: 1}),
        root.identity,
        now_ns=lambda: 100,
    )

    child_waited = header(11, ppid=10, user=2, child_user=3)
    grandchild_reaped = stable_tree_sample(
        FakeReader([{10: root, 11: child_waited}] * 2, {10: 1, 11: 1}),
        root.identity,
        now_ns=lambda: 200,
    )

    root_waited = header(10, user=1, child_user=5)
    child_reaped = stable_tree_sample(
        FakeReader([{10: root_waited}] * 2, {10: 1}),
        root_waited.identity,
        now_ns=lambda: 300,
    )

    assert (
        all_live.sample is not None
        and grandchild_reaped.sample is not None
        and child_reaped.sample is not None
    )
    assert (
        all_live.sample.cpu_ticks
        == grandchild_reaped.sample.cpu_ticks
        == child_reaped.sample.cpu_ticks
        == (6, 0)
    )


def test_handoff_instability_retries_and_recovers_a_valid_sample() -> None:
    root_before = header(10, user=1)
    child = header(11, ppid=10, user=3)
    root_after = header(10, user=1, child_user=3)
    root_stable = header(10, user=1)
    reader = FakeReader(
        [
            {10: root_before, 11: child},
            {10: root_after},
            {10: root_stable},
            {10: root_stable},
        ],
        {10: 1, 11: 1},
    )

    result = stable_tree_sample(reader, root_before.identity, now_ns=lambda: 100)

    assert result.sample is not None
    assert result.handoff_retry_count == 1
    assert result.handoff_unstable_snapshot_count == 1


def test_child_disappearance_during_sample_retries_and_recovers_complete_evidence() -> None:
    root_before = header(10, user=1)
    child = header(11, ppid=10, user=3)
    root_after = header(10, user=1, child_user=3)
    reader = FakeReader(
        [
            {10: root_before, 11: child},
            {10: root_after},
            {10: root_after},
            {10: root_after},
        ],
        {10: 1, 11: 1},
        failed_sample_calls={2},
    )

    result = stable_tree_sample(reader, root_before.identity, now_ns=lambda: 100)
    stats = SamplingStats(100)
    stats.record(result, started_ns=0)
    active = ActiveRun(
        spec=WorkloadSpec("synthetic.smoke", "synthetic"),
        root=root_before.identity,
        root_pid=10,
        started_boottime_ns=0,
        stats=stats,
    )
    assert result.sample is not None
    active.record_sample(result.sample, at_utc="2026-01-01T00:00:00Z")
    summary = build_run_summary(
        active,
        session_id="session",
        observation_id="observation",
        ticks_per_second=1,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )

    assert result.handoff_retry_count == 1
    assert result.handoff_unstable_snapshot_count == 1
    assert stats.invalid_snapshot_count == 0
    assert summary["completeness"]["state"] == "complete"


def test_handoff_retry_then_ordinary_sample_failure_is_explicitly_incomplete(
    monkeypatch,
    tmp_path: Path,
) -> None:
    clock_ns = [0]
    monkeypatch.setattr("observability.resource_envelope.boottime_ns", lambda: clock_ns[0])

    def advance_clock(seconds: float) -> None:
        clock_ns[0] += int(seconds * 1_000_000_000)

    root_before = header(10, start=0, user=1)
    child = header(11, ppid=10, user=3)
    root_after = header(10, start=0, user=1, child_user=3)
    reader = FakeReader(
        [
            {10: root_before, 11: child},
            {10: root_before, 11: child},
            {10: root_after},
            {10: root_after},
            {10: root_after},
        ],
        {10: 1, 11: 1},
        failed_sample_calls={3},
    )
    observer = ResourceEnvelopeObserver(
        reader=reader,  # type: ignore[arg-type]
        output_dir=tmp_path,
        duration_seconds=0.1,
        explicit_pid=10,
        explicit_workload_id="synthetic.smoke",
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=tmp_path / "wrapper",
        sleep=advance_clock,
    )

    session = observer.run()
    summary = observer.finished[0]

    assert session["observed_run_count"] == 1
    assert summary["cpu"]["handoff_retry_count"] == 1
    assert summary["cpu"]["handoff_unstable_snapshot_count"] == 1
    assert summary["sampling"]["invalid_snapshot_count"] == 0
    assert summary["cpu"]["total_seconds"] is None
    assert summary["completeness"]["state"] == "incomplete"
    assert "proc_snapshot_unavailable" in summary["completeness"]["reasons"]


def test_handoff_instability_exhausts_the_fixed_retry_bound() -> None:
    root_before = header(10, user=1)
    child = header(11, ppid=10, user=3)
    root_after = header(10, user=1, child_user=3)
    reader = FakeReader(
        [{10: root_before, 11: child}, {10: root_after}]
        * (HANDOFF_ADDITIONAL_RETRY_LIMIT + 1),
        {10: 1, 11: 1},
    )

    result = stable_tree_sample(reader, root_before.identity, now_ns=lambda: 100)

    assert result.sample is None
    assert result.handoff_retry_count == HANDOFF_ADDITIONAL_RETRY_LIMIT
    assert result.handoff_unstable_snapshot_count == HANDOFF_ADDITIONAL_RETRY_LIMIT + 1
    assert result.handoff_retry_exhausted is True


def test_peak_rss_is_the_sum_of_live_tree_vmrss_samples() -> None:
    root = header(10)
    child = header(11, ppid=10)
    sample = StableTreeSample(
        completed_boottime_ns=1,
        samples=(ProcessSample(root, 128), ProcessSample(child, 512)),
    )

    assert sample.rss_bytes == 640
