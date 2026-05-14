from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from steam.observability import exporter


def write_result(
    jobs_dir: Path,
    cadence: str,
    run_id: str,
    payload: dict[str, Any],
) -> None:
    run_dir = jobs_dir / cadence / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def sample_value(
    samples: list[exporter.MetricSample],
    name: str,
    labels: dict[str, str] | None = None,
) -> float:
    expected_labels = labels or {}
    for sample in samples:
        if sample.name == name and dict(sample.labels) == expected_labels:
            return sample.value
    raise AssertionError(f"missing sample: {name} {expected_labels}")


def test_scheduler_metrics_read_latest_cadence_result(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    write_result(
        jobs_dir,
        exporter.JOB_CCU_30M,
        "older",
        {
            "duration_ms": 5000,
            "finished_at_utc": "2026-04-19T01:00:00Z",
            "partial_success": False,
            "status": "success",
            "triage": {"missing_evidence_records": 0},
        },
    )
    write_result(
        jobs_dir,
        exporter.JOB_CCU_30M,
        "newer",
        {
            "duration_ms": 38000,
            "finished_at_utc": "2026-04-19T21:02:39Z",
            "partial_success": True,
            "status": "partial_success",
            "triage": {"missing_evidence_records": 2},
        },
    )
    write_result(
        jobs_dir,
        exporter.JOB_DAILY,
        "daily-run",
        {
            "duration_ms": 33000,
            "finished_at_utc": "2026-04-19T18:20:35Z",
            "partial_success": True,
            "status": "partial_success",
            "triage": {"reviews_skipped_records": 3},
        },
    )

    samples = exporter.collect_scheduler_metrics(jobs_dir)

    assert sample_value(
        samples,
        "steam_scheduler_latest_run_status",
        {"cadence": "ccu-30m", "status": "partial_success"},
    ) == 1.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_run_status",
        {"cadence": "ccu-30m", "status": "success"},
    ) == 0.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_run_duration_seconds",
        {"cadence": "ccu-30m"},
    ) == 38.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_run_partial_success",
        {"cadence": "ccu-30m"},
    ) == 1.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_ccu_missing_evidence_records",
        {"cadence": "ccu-30m"},
    ) == 2.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_daily_reviews_skipped_records",
        {"cadence": "daily"},
    ) == 3.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_run_present",
        {"cadence": "price-1h"},
    ) == 0.0
    assert sample_value(
        samples,
        "steam_scheduler_latest_run_status",
        {"cadence": "price-1h", "status": "missing"},
    ) == 1.0


def test_app_catalog_summary_metrics_report_missing_and_completed(tmp_path: Path) -> None:
    missing_samples = exporter.collect_app_catalog_summary_metrics(tmp_path / "missing.json")
    assert sample_value(missing_samples, "steam_app_catalog_latest_summary_exists") == 0.0
    assert sample_value(
        missing_samples,
        "steam_app_catalog_latest_summary_status",
        {"status": "missing"},
    ) == 1.0

    summary_path = tmp_path / "latest.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "finished_at_utc": "2026-04-19T03:00:00Z",
                "response": {"payload_excerpt_or_json": {"app_count": 123}},
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )

    completed_samples = exporter.collect_app_catalog_summary_metrics(summary_path)
    assert sample_value(completed_samples, "steam_app_catalog_latest_summary_exists") == 1.0
    assert sample_value(
        completed_samples,
        "steam_app_catalog_latest_summary_status",
        {"status": "completed"},
    ) == 1.0
    assert sample_value(completed_samples, "steam_app_catalog_latest_summary_app_count") == 123.0


class FakeCursor:
    def __init__(self, values_by_sql: dict[str, object]) -> None:
        self.values_by_sql = values_by_sql
        self.current_sql = ""

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.current_sql = sql

    def fetchone(self) -> tuple[object]:
        return (self.values_by_sql[self.current_sql],)


class FakeConnection:
    def __init__(self, values_by_sql: dict[str, object]) -> None:
        self.values_by_sql = values_by_sql

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.values_by_sql)


def test_db_freshness_metrics_use_env_connection_and_dataset_timestamps(
    monkeypatch,
) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "steam")
    monkeypatch.setenv("POSTGRES_USER", "steam")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")

    values_by_sql = {
        exporter.DB_FRESHNESS_SOURCES[0].sql: dt.date(2026, 4, 20),
        exporter.DB_FRESHNESS_SOURCES[1].sql: dt.date(2026, 4, 20),
        exporter.DB_FRESHNESS_SOURCES[2].sql: dt.datetime(
            2026, 4, 20, 6, 0, tzinfo=exporter.KST
        ),
        exporter.DB_FRESHNESS_SOURCES[3].sql: dt.datetime(
            2026, 4, 20, 6, 30, tzinfo=exporter.KST
        ),
        exporter.DB_FRESHNESS_SOURCES[4].sql: dt.date(2026, 4, 20),
    }
    seen_conninfo: list[str] = []

    def fake_connect(conninfo: str) -> FakeConnection:
        seen_conninfo.append(conninfo)
        return FakeConnection(values_by_sql)

    samples = exporter.collect_db_freshness_metrics(
        now=dt.datetime(2026, 4, 20, 7, 0, tzinfo=exporter.KST),
        connect=fake_connect,
    )

    assert "host=localhost" in seen_conninfo[0]
    assert sample_value(samples, "steam_db_freshness_query_success") == 1.0
    assert sample_value(
        samples,
        "steam_db_dataset_freshness_available",
        {"dataset": "ccu_30m"},
    ) == 1.0
    assert sample_value(
        samples,
        "steam_db_dataset_freshness_age_seconds",
        {"dataset": "ccu_30m"},
    ) == 1800.0


def test_chzzk_scheduler_metrics_parse_read_only_query_output() -> None:
    now = dt.datetime(2026, 5, 14, 5, 0, tzinfo=dt.UTC)

    def fake_runner() -> str:
        return json.dumps(
            {
                "last_result": 0,
                "latest_run_time": "2026-05-14T04:29:00Z",
                "missed_runs": 0,
                "new_instance_ignored_events": 2,
                "task_available": True,
                "task_enabled": True,
            }
        )

    samples = exporter.collect_chzzk_scheduler_metrics(now=now, runner=fake_runner)

    assert sample_value(samples, "chzzk_guarded_write_scheduler_task_available") == 1.0
    assert sample_value(samples, "chzzk_guarded_write_scheduler_task_enabled") == 1.0
    assert sample_value(samples, "chzzk_guarded_write_scheduler_last_result") == 0.0
    assert sample_value(samples, "chzzk_guarded_write_scheduler_latest_run_age_seconds") == 1860.0
    assert sample_value(samples, "chzzk_guarded_write_scheduler_recent_missing_intervals") == 0.0
    assert sample_value(
        samples,
        "chzzk_guarded_write_scheduler_recent_new_instance_ignored_events",
    ) == 2.0


def test_chzzk_scheduler_metrics_fail_closed_when_query_unavailable() -> None:
    def fake_runner() -> str:
        raise OSError("scheduler unavailable")

    samples = exporter.collect_chzzk_scheduler_metrics(
        now=dt.datetime(2026, 5, 14, 5, 0, tzinfo=dt.UTC),
        runner=fake_runner,
    )

    assert sample_value(samples, "chzzk_guarded_write_scheduler_task_available") == 0.0
    assert sample_value(samples, "chzzk_guarded_write_scheduler_task_enabled") == 0.0
    assert sample_value(samples, "chzzk_guarded_write_scheduler_last_result") == -1.0


def test_chzzk_wrapper_metrics_use_sanitized_latest_evidence(tmp_path: Path) -> None:
    older = tmp_path / "20260514T035900Z"
    newer = tmp_path / "20260514T042900Z"
    for run_dir in (older, newer):
        (run_dir / "trace").mkdir(parents=True)
    (older / "trace" / "end.json").write_text('{"exit_code":"0"}', encoding="utf-8")
    (older / "guarded-write-result.json").write_text(
        json.dumps({"guarded_write": {}, "status": "hard_failure"}),
        encoding="utf-8",
    )
    (newer / "trace" / "end.json").write_text(
        '{"exit_code":"0","recorded_at_utc":"2026-05-14T04:31:00Z"}',
        encoding="utf-8",
    )
    (newer / "no-write-result.json").write_text('{"status":"success"}', encoding="utf-8")
    (newer / "guarded-write-result.json").write_text(
        json.dumps(
            {
                "guarded_write": {
                    "category": {"committed_row_count": 25},
                    "channel": {"committed_row_count": 60},
                },
                "status": "success",
            }
        ),
        encoding="utf-8",
    )

    samples = exporter.collect_chzzk_wrapper_metrics(
        now=dt.datetime(2026, 5, 14, 5, 0, tzinfo=dt.UTC),
        wrapper_dir=tmp_path,
    )

    assert sample_value(
        samples,
        "chzzk_guarded_write_wrapper_latest_run_status",
        {"status": "success"},
    ) == 1.0
    assert sample_value(
        samples,
        "chzzk_guarded_write_wrapper_latest_committed_rows",
        {"dataset": "category"},
    ) == 25.0
    assert sample_value(samples, "chzzk_guarded_write_wrapper_latest_run_age_seconds") == 1740.0
    assert sample_value(
        samples,
        "chzzk_guarded_write_wrapper_latest_committed_rows",
        {"dataset": "channel"},
    ) == 60.0


class FakeChzzkCursor:
    def __init__(self) -> None:
        self.current_result: tuple[object, ...] = (None,)

    def __enter__(self) -> FakeChzzkCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        if sql == "SELECT MAX(bucket_time) FROM fact_chzzk_category_30m":
            self.current_result = (dt.datetime(2026, 5, 14, 4, 0, tzinfo=dt.UTC),)
        elif sql == "SELECT MAX(bucket_time) FROM fact_chzzk_category_channel_30m":
            self.current_result = (dt.datetime(2026, 5, 14, 4, 30, tzinfo=dt.UTC),)
        elif sql == "SELECT COUNT(*) FROM fact_chzzk_category_30m WHERE bucket_time = %s":
            self.current_result = (25,)
        elif sql == "SELECT COUNT(*) FROM fact_chzzk_category_channel_30m WHERE bucket_time = %s":
            self.current_result = (60,)
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self) -> tuple[object, ...]:
        return self.current_result


class FakeChzzkConnection:
    def __enter__(self) -> FakeChzzkConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeChzzkCursor:
        return FakeChzzkCursor()


def test_chzzk_db_metrics_use_select_only_latest_bucket_counts(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "steam")
    monkeypatch.setenv("POSTGRES_USER", "steam")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    seen_conninfo: list[str] = []

    def fake_connect(conninfo: str) -> FakeChzzkConnection:
        seen_conninfo.append(conninfo)
        return FakeChzzkConnection()

    samples = exporter.collect_chzzk_db_metrics(
        now=dt.datetime(2026, 5, 14, 5, 0, tzinfo=dt.UTC),
        connect=fake_connect,
    )

    assert "host=localhost" in seen_conninfo[0]
    assert sample_value(
        samples,
        "chzzk_db_dataset_freshness_age_seconds",
        {"dataset": "category_30m"},
    ) == 3600.0
    assert sample_value(
        samples,
        "chzzk_db_dataset_freshness_age_seconds",
        {"dataset": "category_channel_30m"},
    ) == 1800.0
    assert sample_value(
        samples,
        "chzzk_db_latest_bucket_rows",
        {"dataset": "category_30m"},
    ) == 25.0
    assert sample_value(
        samples,
        "chzzk_db_latest_bucket_rows",
        {"dataset": "category_channel_30m"},
    ) == 60.0


def test_render_prometheus_text_escapes_labels() -> None:
    text = exporter.render_prometheus_text(
        [
            exporter.MetricSample(
                "steam_scheduler_latest_run_present",
                1.0,
                {"cadence": 'quote"and\\slash'},
            )
        ]
    )

    assert '# TYPE steam_scheduler_latest_run_present gauge' in text
    assert 'cadence="quote\\"and\\\\slash"' in text
