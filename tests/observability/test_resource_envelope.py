from __future__ import annotations

import datetime as dt
import json
import stat
from pathlib import Path

import pytest

from observability.linux_proc import ProcessHeader, ProcessIdentity, ProcessSample
from observability.resource_envelope import (
    ActiveRun,
    ResourceEnvelopeObserver,
    SamplingStats,
    StableTreeSample,
    TreeSampleResult,
    ValidCycleSample,
    WorkloadSpec,
    _chzzk_artifact_correlation,
    _chzzk_correlation,
    _steam_correlation,
    _write_private_json,
    build_run_summary,
    gap_threshold_ms,
    match_workloads,
)

CANONICAL_RUN_ID = "20260101T000000000000Z"
CANONICAL_BOUNDARY_ID = "20260101T000000Z"
CHZZK_WRAPPER_SCRIPT = "run_chzzk_fetch_load_guarded_write_orchestration_wsl.sh"


def header(pid: int, *, start: int = 1, user: int = 0) -> ProcessHeader:
    return ProcessHeader(ProcessIdentity(pid, start), 1, "python", user, 0, 0, 0)


def sample(at_ns: int, *, user: int = 0, rss: int = 100) -> StableTreeSample:
    return StableTreeSample(at_ns, (ProcessSample(header(10, user=user), rss),))


def write_chzzk_artifact(
    wrapper_dir: Path,
    *,
    boundary_id: str = CANONICAL_BOUNDARY_ID,
    run_id: str = CANONICAL_RUN_ID,
    status: str = "success",
    wrapper_pid: object = "99",
    exit_code: object = "0",
) -> Path:
    run_dir = wrapper_dir / boundary_id
    (run_dir / "trace").mkdir(parents=True)
    (run_dir / "trace" / "start.json").write_text(
        json.dumps(
            {
                "boundary_id": boundary_id,
                "script": CHZZK_WRAPPER_SCRIPT,
                "wrapper_pid": wrapper_pid,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace" / "end.json").write_text(
        json.dumps({"boundary_id": boundary_id, "exit_code": exit_code}),
        encoding="utf-8",
    )
    (run_dir / "guarded-write-result.json").write_text(
        json.dumps(
            {
                "duration_ms": 1000,
                "finished_at_utc": "2026-01-01T00:00:01Z",
                "job_name": "chzzk_fetch_load_manual_orchestration",
                "provider": "chzzk",
                "result_ref": f"{run_id}/result.json",
                "run_id": run_id,
                "started_at_utc": "2026-01-01T00:00:00Z",
                "status": status,
                "raw": "not-exported",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def write_chzzk_no_write_terminal_artifact(
    wrapper_dir: Path,
    *,
    run_id: str = CANONICAL_RUN_ID,
    status: str = "hard_failure",
    exit_code: object = "1",
) -> Path:
    run_dir = write_chzzk_artifact(
        wrapper_dir,
        run_id=run_id,
        status=status,
        exit_code=exit_code,
    )
    guarded_path = run_dir / "guarded-write-result.json"
    guarded_path.replace(run_dir / "no-write-result.json")
    return run_dir


def correlation_summary_text(correlation: dict[str, object]) -> str:
    active = active_run("synthetic.smoke", pid=10)
    return json.dumps(
        build_run_summary(
            active,
            session_id="session",
            observation_id="observation",
            ticks_per_second=1,
            correlation=correlation,
        )
    )


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
    result_path = tmp_path / "ccu-30m" / CANONICAL_RUN_ID / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "job_name": "ccu-30m",
                "run_id": CANONICAL_RUN_ID,
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
        "existing_run_id": CANONICAL_RUN_ID,
        "existing_result_status": "partial_success",
        "existing_duration_ms": 1000,
        "existing_run_started_at_utc": "2026-01-01T00:00:00Z",
        "existing_run_finished_at_utc": "2026-01-01T00:00:01Z",
        "status_conflict": False,
    }


@pytest.mark.parametrize(
    "hostile_run_id",
    [
        "/private/path/run",
        "credential-token-like-value",
        "host.example.internal",
        "line\nbreak\x1f",
        "x" * 256,
    ],
)
def test_steam_correlation_rejects_hostile_run_id_without_persisting_it(
    tmp_path: Path,
    hostile_run_id: str,
) -> None:
    result_path = tmp_path / "ccu-30m" / CANONICAL_RUN_ID / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "job_name": "ccu-30m",
                "run_id": hostile_run_id,
                "started_at_utc": "2026-01-01T00:00:00Z",
                "finished_at_utc": "2026-01-01T00:00:01Z",
                "duration_ms": 1000,
                "status": "success",
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
    text = correlation_summary_text(result)

    assert result == {"state": "unreadable", "contract": "steam_cadence_result_v1"}
    assert hostile_run_id not in text
    assert json.dumps(hostile_run_id)[1:-1] not in text


def test_chzzk_status_exit_conflict_is_not_reclassified(tmp_path: Path) -> None:
    run_dir = write_chzzk_artifact(tmp_path, exit_code="1")
    no_write = json.loads((run_dir / "guarded-write-result.json").read_text(encoding="utf-8"))
    no_write["status"] = "hard_failure"
    (run_dir / "no-write-result.json").write_text(json.dumps(no_write), encoding="utf-8")

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result["state"] == "matched"
    assert result["existing_run_id"] == CANONICAL_RUN_ID
    assert result["existing_result_status"] == "success"
    assert result["existing_result_phase"] == "guarded_write"
    assert result["wrapper_exit_code_state"] == "nonzero"
    assert result["status_conflict"] is True
    assert "raw" not in result


def test_process_observed_chzzk_lock_busy_status_is_preserved(tmp_path: Path) -> None:
    write_chzzk_artifact(tmp_path, status="lock_busy", exit_code="75")

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result["state"] == "matched"
    assert result["existing_run_id"] == CANONICAL_RUN_ID
    assert result["existing_result_status"] == "lock_busy"
    assert result["existing_result_phase"] == "guarded_write"
    assert result["wrapper_exit_code_state"] == "nonzero"
    assert result["status_conflict"] is False


def test_process_observed_chzzk_no_write_hard_failure_is_terminal(
    tmp_path: Path,
) -> None:
    write_chzzk_no_write_terminal_artifact(tmp_path)

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result == {
        "state": "matched",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": CANONICAL_BOUNDARY_ID,
        "existing_run_id": CANONICAL_RUN_ID,
        "existing_result_status": "hard_failure",
        "existing_result_phase": "no_write_terminal",
        "wrapper_exit_code_state": "nonzero",
        "status_conflict": False,
    }
    summary = correlation_summary_text(result)
    assert "no-write-result.json" not in summary
    assert str(tmp_path) not in summary


@pytest.mark.parametrize("guarded_payload", ["{", json.dumps({"status": []})])
def test_invalid_guarded_result_does_not_fallback_to_valid_no_write(
    tmp_path: Path,
    guarded_payload: str,
) -> None:
    run_dir = write_chzzk_no_write_terminal_artifact(tmp_path)
    (run_dir / "guarded-write-result.json").write_text(guarded_payload, encoding="utf-8")

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result == {
        "state": "unreadable",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": CANONICAL_BOUNDARY_ID,
    }


@pytest.mark.parametrize(
    "invalid_evidence",
    [
        "malformed_result",
        "noncanonical_run_id",
        "invalid_provider",
        "invalid_binding",
        "nonterminal_status",
        "missing_end",
        "malformed_end",
        "mismatched_end_boundary",
        "zero_exit",
        "invalid_exit",
    ],
)
def test_invalid_no_write_terminal_evidence_fails_closed(
    tmp_path: Path,
    invalid_evidence: str,
) -> None:
    run_dir = write_chzzk_no_write_terminal_artifact(tmp_path)
    result_path = run_dir / "no-write-result.json"
    end_path = run_dir / "trace" / "end.json"
    if invalid_evidence == "malformed_result":
        result_path.write_text("{", encoding="utf-8")
    elif invalid_evidence in {
        "noncanonical_run_id",
        "invalid_provider",
        "invalid_binding",
        "nonterminal_status",
    }:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if invalid_evidence == "noncanonical_run_id":
            payload["run_id"] = "not-canonical"
            payload["result_ref"] = "not-canonical/result.json"
        elif invalid_evidence == "invalid_provider":
            payload["provider"] = "other"
        elif invalid_evidence == "invalid_binding":
            payload["result_ref"] = "20260101T003000000000Z/result.json"
        else:
            payload["status"] = "partial_success"
        result_path.write_text(json.dumps(payload), encoding="utf-8")
    elif invalid_evidence == "missing_end":
        end_path.unlink()
    elif invalid_evidence == "malformed_end":
        end_path.write_text("{", encoding="utf-8")
    else:
        end = json.loads(end_path.read_text(encoding="utf-8"))
        if invalid_evidence == "mismatched_end_boundary":
            end["boundary_id"] = "20260101T003000Z"
        elif invalid_evidence == "zero_exit":
            end["exit_code"] = "0"
        else:
            end["exit_code"] = "not-an-exit"
        end_path.write_text(json.dumps(end), encoding="utf-8")

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result == {
        "state": "unreadable",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": CANONICAL_BOUNDARY_ID,
    }


def test_process_observed_chzzk_unknown_status_fails_closed(tmp_path: Path) -> None:
    write_chzzk_artifact(tmp_path, status="invented")

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)

    assert result == {
        "state": "unreadable",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": CANONICAL_BOUNDARY_ID,
    }


@pytest.mark.parametrize(
    "hostile_run_id",
    [
        "/private/path/run",
        "credential-token-like-value",
        "host.example.internal",
        "line\nbreak\x1f",
        "x" * 256,
    ],
)
def test_chzzk_correlation_rejects_hostile_run_id_without_persisting_it(
    tmp_path: Path,
    hostile_run_id: str,
) -> None:
    write_chzzk_artifact(tmp_path, run_id=hostile_run_id)

    result = _chzzk_correlation(99, wrapper_dir=tmp_path)
    text = correlation_summary_text(result)

    assert result["state"] == "unreadable"
    assert "existing_run_id" not in result
    assert hostile_run_id not in text
    assert json.dumps(hostile_run_id)[1:-1] not in text


def test_canonical_chzzk_artifact_only_evidence_stays_process_unmatched(
    tmp_path: Path,
) -> None:
    wrapper_dir = tmp_path / "wrapper"
    write_chzzk_artifact(wrapper_dir)
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=wrapper_dir,
    )

    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert len(observer.finished) == 1
    summary = observer.finished[0]
    assert summary["correlation"]["state"] == "unmatched"
    assert summary["correlation"]["existing_run_id"] == CANONICAL_RUN_ID
    assert summary["correlation"]["existing_result_status"] == "success"
    assert summary["correlation"]["existing_result_phase"] == "guarded_write"
    assert summary["completeness"] == {
        "state": "incomplete",
        "meaning": "no_known_observation_contract_gap",
        "reasons": ["process_not_observed"],
    }
    assert summary["memory"]["peak_aggregate_rss_bytes"] is None


def test_no_write_terminal_artifact_only_evidence_stays_process_unmatched(
    tmp_path: Path,
) -> None:
    wrapper_dir = tmp_path / "wrapper"
    write_chzzk_no_write_terminal_artifact(wrapper_dir)
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=wrapper_dir,
    )

    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert len(observer.finished) == 1
    summary = observer.finished[0]
    assert summary["correlation"]["state"] == "unmatched"
    assert summary["correlation"]["existing_result_status"] == "hard_failure"
    assert summary["correlation"]["existing_result_phase"] == "no_write_terminal"
    assert summary["completeness"] == {
        "state": "incomplete",
        "meaning": "no_known_observation_contract_gap",
        "reasons": ["process_not_observed"],
    }
    assert summary["memory"]["peak_aggregate_rss_bytes"] is None
    assert summary["cpu"]["total_seconds"] is None


def test_chzzk_artifact_only_lock_busy_status_is_preserved(tmp_path: Path) -> None:
    wrapper_dir = tmp_path / "wrapper"
    write_chzzk_artifact(wrapper_dir, status="lock_busy", exit_code="75")
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=wrapper_dir,
    )

    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert len(observer.finished) == 1
    correlation = observer.finished[0]["correlation"]
    assert correlation["state"] == "unmatched"
    assert correlation["existing_result_status"] == "lock_busy"
    assert correlation["wrapper_exit_code_state"] == "nonzero"
    assert correlation["status_conflict"] is False


@pytest.mark.parametrize("marker_state", ["missing", "malformed", "boundary_mismatch"])
def test_chzzk_artifact_only_invalid_start_marker_fails_closed(
    tmp_path: Path,
    marker_state: str,
) -> None:
    wrapper_dir = tmp_path / "wrapper"
    run_dir = write_chzzk_artifact(wrapper_dir)
    start_path = run_dir / "trace" / "start.json"
    if marker_state == "missing":
        start_path.unlink()
    elif marker_state == "malformed":
        start_path.write_text(json.dumps({"wrapper_pid": "not-a-pid"}), encoding="utf-8")
    else:
        start_path.write_text(
            json.dumps(
                {
                    "boundary_id": "20260101T003000Z",
                    "script": CHZZK_WRAPPER_SCRIPT,
                    "wrapper_pid": "99",
                }
            ),
            encoding="utf-8",
        )

    result = _chzzk_artifact_correlation(run_dir)
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=wrapper_dir,
    )
    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert result == {"state": "unreadable", "contract": "chzzk_guarded_wrapper_v1"}
    assert observer.finished == []


def test_chzzk_artifact_only_mismatched_end_boundary_fails_closed(tmp_path: Path) -> None:
    run_dir = write_chzzk_artifact(tmp_path)
    (run_dir / "trace" / "end.json").write_text(
        json.dumps({"boundary_id": "20260101T003000Z", "exit_code": "0"}),
        encoding="utf-8",
    )

    result = _chzzk_artifact_correlation(run_dir)
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=tmp_path,
    )
    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert result == {
        "state": "unreadable",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": CANONICAL_BOUNDARY_ID,
    }
    assert "existing_result_status" not in result
    assert observer.finished == []


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("provider", "other"),
        ("job_name", "other_job"),
        ("result_ref", "20260101T003000000000Z/result.json"),
    ],
)
def test_chzzk_artifact_only_broken_result_binding_fails_closed(
    tmp_path: Path,
    field: str,
    invalid_value: str,
) -> None:
    run_dir = write_chzzk_artifact(tmp_path)
    result_path = run_dir / "guarded-write-result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload[field] = invalid_value
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _chzzk_artifact_correlation(run_dir)

    assert result == {
        "state": "unreadable",
        "contract": "chzzk_guarded_wrapper_v1",
        "wrapper_boundary_id": CANONICAL_BOUNDARY_ID,
    }
    assert "existing_result_status" not in result


@pytest.mark.parametrize(
    "hostile_boundary_id",
    ["host.example.internal", "credential-token-like-value", "line\nbreak\x1f", "x" * 128],
)
def test_chzzk_artifact_only_rejects_hostile_boundary_without_persisting_it(
    tmp_path: Path,
    hostile_boundary_id: str,
) -> None:
    run_dir = write_chzzk_artifact(tmp_path, boundary_id=hostile_boundary_id)

    result = _chzzk_artifact_correlation(run_dir)
    text = correlation_summary_text(result)
    observer = ResourceEnvelopeObserver(
        reader=None,  # type: ignore[arg-type]
        output_dir=tmp_path / "output",
        duration_seconds=1,
        jobs_dir=tmp_path / "jobs",
        wrapper_dir=tmp_path,
    )
    observer._record_artifact_only_runs("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z")

    assert result == {"state": "unreadable", "contract": "chzzk_guarded_wrapper_v1"}
    assert hostile_boundary_id not in text
    assert json.dumps(hostile_boundary_id)[1:-1] not in text
    assert observer.finished == []


def test_new_result_without_observed_process_becomes_incomplete_evidence(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    result_path = jobs_dir / "ccu-30m" / CANONICAL_RUN_ID / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "job_name": "ccu-30m",
                "run_id": CANONICAL_RUN_ID,
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
