from __future__ import annotations

import datetime as dt
import json
import stat
from pathlib import Path

from observability.linux_proc import ProcessHeader, ProcessIdentity, ProcessSample
from observability.resource_envelope import (
    ActiveRun,
    ResourceEnvelopeObserver,
    SamplingStats,
    StableTreeSample,
    TreeSampleResult,
    ValidCycleSample,
    WorkloadSpec,
    _chzzk_correlation,
    _steam_correlation,
    _write_private_json,
    build_run_summary,
    gap_threshold_ms,
    match_workloads,
)


def header(pid: int, *, start: int = 1, user: int = 0) -> ProcessHeader:
    return ProcessHeader(ProcessIdentity(pid, start), 1, "python", user, 0, 0, 0)


def sample(at_ns: int, *, user: int = 0, rss: int = 100) -> StableTreeSample:
    return StableTreeSample(at_ns, (ProcessSample(header(10, user=user), rss),))


def test_workload_matching_never_returns_raw_command_line() -> None:
    matches = match_workloads(
        ("python", "-m", "steam.ingest.run_steam_cadence_job", "ccu-30m", "secret=value")
    )

    assert [item.workload_id for item in matches] == ["steam.ccu-30m"]


def test_sampling_gap_uses_excess_over_threshold_only(monkeypatch) -> None:
    clock = iter([0, 100_000_000, 400_000_000])
    monkeypatch.setattr("observability.resource_envelope.boottime_ns", lambda: next(clock))
    stats = SamplingStats(target_interval_ms=100)

    stats.record(TreeSampleResult(sample(0)), started_ns=0)
    stats.record(TreeSampleResult(sample(400_000_000)), started_ns=100_000_000)

    assert gap_threshold_ms(100) == 250
    assert stats.max_observed_sample_gap_ms == 400
    assert stats.over_threshold_sample_gap_count == 1
    assert stats.total_sample_gap_excess_ms == 150


def active_run(workload_id: str, *, pid: int, start: int = 1) -> ActiveRun:
    return ActiveRun(
        spec=WorkloadSpec(workload_id, "synthetic"),
        root=ProcessIdentity(pid, start),
        root_pid=pid,
        started_boottime_ns=0,
        stats=SamplingStats(100),
    )


def valid_cycle_sample(
    active: ActiveRun,
    *,
    previous_ns: int,
    completed_ns: int,
    previous_cycle: int = 1,
) -> ValidCycleSample:
    return ValidCycleSample(
        active=active,
        previous_completed_boottime_ns=previous_ns,
        completed_boottime_ns=completed_ns,
        previous_cycle=previous_cycle,
    )


def test_overlap_records_only_consecutive_valid_sample_intersections(tmp_path: Path) -> None:
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path,
        duration_seconds=1,
    )
    left = active_run("steam.ccu-30m", pid=10)
    right = active_run("steam.price-1h", pid=20)
    observer.active = {left.root: left, right.root: right}

    observer._record_overlap(
        {
            left.root: valid_cycle_sample(
                left, previous_ns=100_000_000, completed_ns=200_000_000
            ),
            right.root: valid_cycle_sample(
                right, previous_ns=105_000_000, completed_ns=205_000_000
            ),
        },
        cycle=2,
        at_utc="2026-01-01T00:00:00Z",
    )

    for run, other_id in ((left, "steam.price-1h"), (right, "steam.ccu-30m")):
        assert run.overlap_ids == {other_id}
        assert run.overlap_sample_count == 1
        assert run.peak_other_run_count == 1
        assert run.overlap_first_utc == "2026-01-01T00:00:00Z"
        assert run.overlap_last_utc == "2026-01-01T00:00:00Z"
        assert run.overlap_lower_bound_ms == 95

    left.stats.valid_sample_count = 2
    summary = build_run_summary(
        left,
        session_id="session",
        observation_id="observation",
        ticks_per_second=1,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )
    assert summary["overlap"] == {
        "observed": True,
        "workload_ids": ["steam.price-1h"],
        "peak_other_run_count": 1,
        "first_observed_at_utc": "2026-01-01T00:00:00Z",
        "last_observed_at_utc": "2026-01-01T00:00:00Z",
        "sample_count": 1,
        "observed_overlap_lower_bound_ms": 95,
        "duration_clock": "linux_clock_boottime",
    }


def test_overlap_excludes_an_invalid_current_interval(tmp_path: Path) -> None:
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path,
        duration_seconds=1,
    )
    left = active_run("steam.ccu-30m", pid=10)
    right = active_run("steam.price-1h", pid=20)
    observer.active = {left.root: left, right.root: right}

    observer._record_overlap(
        {left.root: valid_cycle_sample(left, previous_ns=0, completed_ns=100_000_000)},
        cycle=2,
        at_utc="2026-01-01T00:00:00Z",
    )

    assert left.overlap_ids == set()
    assert left.overlap_sample_count == 0
    assert left.peak_other_run_count == 0
    assert left.overlap_lower_bound_ms == 0


def test_overlap_excludes_an_exited_run_left_in_the_active_registry(tmp_path: Path) -> None:
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path,
        duration_seconds=1,
    )
    left = active_run("steam.ccu-30m", pid=10)
    stale = active_run("steam.price-1h", pid=20)
    observer.active = {left.root: left, stale.root: stale}

    observer._record_overlap(
        {left.root: valid_cycle_sample(left, previous_ns=0, completed_ns=100_000_000)},
        cycle=2,
        at_utc="2026-01-01T00:00:00Z",
    )

    assert left.overlap_ids == set()
    assert left.overlap_sample_count == 0
    assert left.peak_other_run_count == 0
    assert left.overlap_lower_bound_ms == 0


def test_overlap_excludes_valid_samples_with_a_threshold_exceeding_gap(tmp_path: Path) -> None:
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path,
        duration_seconds=1,
    )
    left = active_run("steam.ccu-30m", pid=10)
    right = active_run("steam.price-1h", pid=20)

    observer._record_overlap(
        {
            left.root: valid_cycle_sample(left, previous_ns=0, completed_ns=300_000_000),
            right.root: valid_cycle_sample(right, previous_ns=0, completed_ns=300_000_000),
        },
        cycle=2,
        at_utc="2026-01-01T00:00:00Z",
    )

    assert left.overlap_ids == right.overlap_ids == set()
    assert left.overlap_lower_bound_ms == right.overlap_lower_bound_ms == 0


def test_recovered_handoff_retry_keeps_a_sampling_cycle_complete(monkeypatch) -> None:
    monkeypatch.setattr("observability.resource_envelope.boottime_ns", lambda: 0)
    active = active_run("synthetic.smoke", pid=10)
    active.stats.record(
        TreeSampleResult(sample(0), handoff_retry_count=1, handoff_unstable_snapshot_count=1),
        started_ns=0,
    )

    summary = build_run_summary(
        active,
        session_id="session",
        observation_id="observation",
        ticks_per_second=1,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )

    assert summary["cpu"]["handoff_retry_count"] == 1
    assert summary["cpu"]["handoff_unstable_snapshot_count"] == 1
    assert summary["sampling"]["invalid_snapshot_count"] == 0
    assert summary["completeness"]["state"] == "complete"


def test_unresolved_handoff_retry_marks_partial_without_cpu_estimate(monkeypatch) -> None:
    monkeypatch.setattr("observability.resource_envelope.boottime_ns", lambda: 0)
    active = active_run("synthetic.smoke", pid=10)
    active.stats.record(
        TreeSampleResult(
            sample=None,
            handoff_retry_count=2,
            handoff_unstable_snapshot_count=3,
            handoff_retry_exhausted=True,
        ),
        started_ns=0,
    )

    summary = build_run_summary(
        active,
        session_id="session",
        observation_id="observation",
        ticks_per_second=1,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )

    assert summary["cpu"]["handoff_retry_count"] == 2
    assert summary["cpu"]["handoff_unstable_snapshot_count"] == 3
    assert summary["sampling"]["invalid_snapshot_count"] == 1
    assert summary["cpu"]["total_seconds"] is None
    assert summary["completeness"]["state"] == "incomplete"
    assert "cpu_handoff_snapshot_unstable" in summary["completeness"]["reasons"]


def test_summary_marks_sampling_gap_partial_and_keeps_vmrss_caveats() -> None:
    active = ActiveRun(
        spec=WorkloadSpec("synthetic.smoke", "synthetic"),
        root=ProcessIdentity(10, 1),
        root_pid=10,
        started_boottime_ns=0,
        stats=SamplingStats(100),
    )
    active.first_sample_boottime_ns = 0
    active.last_sample_boottime_ns = 400_000_000
    active.exit_detected_boottime_ns = 500_000_000
    active.first_sample_at_utc = "2026-01-01T00:00:00Z"
    active.last_sample_at_utc = "2026-01-01T00:00:00Z"
    active.exit_detected_at_utc = "2026-01-01T00:00:01Z"
    active.peak_rss_bytes = 123
    active.process_count_at_peak = 1
    active.cpu_user_ticks = 10
    active.cpu_system_ticks = 2
    active.stats.valid_sample_count = 2
    active.stats.over_threshold_sample_gap_count = 1

    summary = build_run_summary(
        active,
        session_id="session",
        observation_id="observation",
        ticks_per_second=10,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )

    assert summary["completeness"]["state"] == "partial"
    assert "sampling_gap_exceeded" in summary["completeness"]["reasons"]
    assert summary["memory"] == {
        "metric_kind": "maximum_sampled_sum_of_process_tree_vmrss",
        "peak_aggregate_rss_bytes": 123,
        "process_count_at_peak": 1,
        "temporal_peak_may_be_missed": True,
        "shared_pages_may_be_double_counted": True,
        "vmrss_accounting_may_be_approximate": True,
    }


def test_summary_does_not_serialize_sensitive_internal_values() -> None:
    active = ActiveRun(
        spec=WorkloadSpec("synthetic.smoke", "synthetic"),
        root=ProcessIdentity(10, 1),
        root_pid=10,
        started_boottime_ns=0,
        stats=SamplingStats(100),
    )
    active.stats.valid_sample_count = 1
    active.peak_rss_bytes = 10
    active.process_count_at_peak = 1
    active.cpu_user_ticks = 1
    active.cpu_system_ticks = 0
    active.first_sample_boottime_ns = 0
    active.exit_detected_boottime_ns = 1
    active.first_sample_at_utc = "2026-01-01T00:00:00Z"
    active.exit_detected_at_utc = "2026-01-01T00:00:00Z"

    text = json.dumps(
        build_run_summary(
            active,
            session_id="session",
            observation_id="observation",
            ticks_per_second=1,
            correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
        )
    )

    for forbidden in ("cmdline", "POSTGRES_PASSWORD", "/home/user", "hostname"):
        assert forbidden not in text


def test_existing_wall_timestamps_do_not_control_observed_elapsed() -> None:
    active = ActiveRun(
        spec=WorkloadSpec("synthetic.smoke", "synthetic"),
        root=ProcessIdentity(10, 1),
        root_pid=10,
        started_boottime_ns=0,
        stats=SamplingStats(100),
    )
    active.stats.valid_sample_count = 1
    active.first_sample_boottime_ns = 5_000_000_000
    active.exit_detected_boottime_ns = 7_000_000_000
    active.first_sample_at_utc = "2030-01-01T00:00:00Z"
    active.exit_detected_at_utc = "2000-01-01T00:00:00Z"

    summary = build_run_summary(
        active,
        session_id="session",
        observation_id="observation",
        ticks_per_second=1,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )

    assert summary["timing"]["observed_elapsed_ms"] == 2000


def test_pid_reuse_creates_a_distinct_active_run_identity(tmp_path: Path) -> None:
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path,
        duration_seconds=1,
        explicit_pid=10,
        explicit_workload_id="synthetic.smoke",
    )
    original = header(10, start=1)
    reused = header(10, start=2)

    observer._discover({10: original}, now=1)
    observer._discover({10: reused}, now=2)

    assert set(observer.active) == {original.identity, reused.identity}
    assert observer.active[original.identity].root != observer.active[reused.identity].root


def test_late_attach_cannot_be_complete() -> None:
    active = active_run("synthetic.smoke", pid=10)
    active.stats.valid_sample_count = 1
    active.record_sample(sample(300_000_000), at_utc="2026-01-01T00:00:00Z")

    summary = build_run_summary(
        active,
        session_id="session",
        observation_id="observation",
        ticks_per_second=1,
        correlation={"state": "not_applicable", "contract": "synthetic_pid_smoke"},
    )

    assert summary["completeness"]["state"] == "partial"
    assert "late_attach" in summary["completeness"]["reasons"]


def test_private_json_write_uses_restrictive_modes_and_leaves_no_temp_file(tmp_path: Path) -> None:
    output = tmp_path / "private" / "run.json"
    payload = {"workload": {"id": "synthetic.smoke"}, "measurement": 1}

    _write_private_json(output, payload)

    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(output.parent.glob(".*.tmp"))
    written = output.read_text(encoding="utf-8")
    for forbidden in ("cmdline", "POSTGRES_PASSWORD", "/home/user", "hostname"):
        assert forbidden not in written


def test_steam_correlation_uses_unique_time_and_workload_match(tmp_path: Path) -> None:
    result_path = tmp_path / "ccu-30m" / "run-a" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "job_name": "ccu-30m",
                "run_id": "run-a",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "finished_at_utc": "2026-01-01T00:00:01Z",
                "duration_ms": 1000,
                "status": "partial_success",
                "paths": {"private": "/not-allowed"},
            }
        ),
        encoding="utf-8",
    )

    result = _steam_correlation(
        WorkloadSpec("steam.ccu-30m", "steam", "ccu-30m"),
        started_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        finished_at=dt.datetime(2026, 1, 1, 0, 0, 1, tzinfo=dt.UTC),
        jobs_dir=tmp_path,
    )

    assert result == {
        "state": "matched",
        "contract": "steam_cadence_result_v1",
        "existing_run_id": "run-a",
        "existing_result_status": "partial_success",
        "existing_duration_ms": 1000,
        "existing_run_started_at_utc": "2026-01-01T00:00:00Z",
        "existing_run_finished_at_utc": "2026-01-01T00:00:01Z",
        "status_conflict": False,
    }


def test_chzzk_status_exit_conflict_is_not_reclassified(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260101T000000Z"
    (run_dir / "trace").mkdir(parents=True)
    (run_dir / "trace" / "start.json").write_text(
        json.dumps({"wrapper_pid": "99"}), encoding="utf-8"
    )
    (run_dir / "trace" / "end.json").write_text(
        json.dumps({"exit_code": "1"}), encoding="utf-8"
    )
    (run_dir / "guarded-write-result.json").write_text(
        json.dumps({"run_id": "guarded", "status": "success", "raw": "not-exported"}),
        encoding="utf-8",
    )

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result["state"] == "matched"
    assert result["existing_result_status"] == "success"
    assert result["wrapper_exit_code_state"] == "nonzero"
    assert result["status_conflict"] is True
    assert "raw" not in result


def test_new_result_without_observed_process_becomes_incomplete_evidence(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    result_path = jobs_dir / "ccu-30m" / "run-a" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "job_name": "ccu-30m",
                "run_id": "run-a",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "finished_at_utc": "2026-01-01T00:00:01Z",
                "duration_ms": 1000,
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=jobs_dir,
        wrapper_dir=tmp_path / "wrapper",
    )

    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert len(observer.finished) == 1
    assert observer.finished[0]["completeness"] == {
        "state": "incomplete",
        "meaning": "no_known_observation_contract_gap",
        "reasons": ["process_not_observed"],
    }
    assert observer.finished[0]["memory"]["peak_aggregate_rss_bytes"] is None
