from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from observability.linux_proc import ProcessHeader, ProcessIdentity, ProcessSample
from observability.resource_envelope import (
    ActiveRun,
    ResourceEnvelopeObserver,
    SamplingStats,
    StableTreeSample,
    WorkloadSpec,
    _chzzk_correlation,
    _steam_correlation,
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

    stats.record(sample(0), started_ns=0)
    stats.record(sample(400_000_000), started_ns=100_000_000)

    assert gap_threshold_ms(100) == 250
    assert stats.max_observed_sample_gap_ms == 400
    assert stats.over_threshold_sample_gap_count == 1
    assert stats.total_sample_gap_excess_ms == 150


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
