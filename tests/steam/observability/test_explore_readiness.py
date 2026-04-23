from __future__ import annotations

import datetime as dt
import json

from steam.observability import explore_readiness


def sample_row() -> dict[str, object]:
    return {
        "active_game_count": "10",
        "ccu_daily_anchor_date": dt.date(2026, 4, 24),
        "selected_daily_ccu_coverage_count": "8",
        "previous_daily_ccu_coverage_count": 6,
        "ccu_delta_daily_coverage_count": 5,
        "raw_complete_ccu_anchor_date": "2026-04-23",
        "selected_raw_bucket_coverage_count": 0,
        "previous_raw_bucket_coverage_count": 0,
        "player_hours_delta_coverage_count": 0,
        "selected_raw_bucket_min": 120,
        "selected_raw_bucket_max": 335,
        "review_anchor_date": dt.datetime(2026, 4, 24, 12, 0),
        "review_current_snapshot_count": 10,
        "review_boundary_7d_count": 9,
        "review_boundary_14d_count": 7,
        "review_boundary_30d_count": 0,
        "review_boundary_60d_count": 0,
        "review_7d_metric_coverage_count": 9,
        "review_7d_delta_coverage_count": 7,
        "review_30d_metric_coverage_count": 0,
        "review_30d_delta_coverage_count": 0,
    }


def test_report_from_row_maps_dates_and_counts() -> None:
    report = explore_readiness.report_from_row(sample_row())

    assert report.active_game_count == 10
    assert report.ccu_daily_anchor_date == dt.date(2026, 4, 24)
    assert report.raw_complete_ccu_anchor_date == dt.date(2026, 4, 23)
    assert report.review_anchor_date == dt.date(2026, 4, 24)
    assert report.selected_daily_ccu_coverage_count == 8
    assert report.selected_raw_bucket_min == 120
    assert report.selected_raw_bucket_max == 335


def test_build_status_reports_ready_partial_and_waiting() -> None:
    report = explore_readiness.report_from_row(sample_row())

    status = explore_readiness.build_status(report)

    assert status["period_avg_peak_ccu_7d"].label == "partial"
    assert status["period_avg_peak_ccu_7d_delta"].label == "partial"
    assert status["estimated_player_hours_7d"].label == "waiting"
    assert status["review_current_snapshot"].label == "ready"
    assert status["review_30d_fields"].label == "waiting"


def test_render_text_includes_stable_readiness_lines() -> None:
    report = explore_readiness.report_from_row(sample_row())

    text = explore_readiness.render_text(report)

    assert "Steam Explore coverage readiness" in text
    assert "active_tracked_steam_games=10" in text
    assert "anchor_date=2026-04-24" in text
    assert "complete_kst_anchor_date=2026-04-23" in text
    assert "selected_bucket_min_max=120..335/336" in text
    assert "Avg/Peak CCU 7d: partial (8/10 active games)" in text
    assert "Estimated Player-Hours 7d: waiting (0/10 active games)" in text


def test_report_to_payload_is_json_ready_with_status() -> None:
    report = explore_readiness.report_from_row(sample_row())

    payload = explore_readiness.report_to_payload(report)
    rendered = json.dumps(
        payload,
        default=explore_readiness._json_default,
        sort_keys=True,
    )

    assert '"schema_version": "1.0"' in rendered
    assert '"expected_raw_7d_buckets": 336' in rendered
    assert payload["status"]["review_current_snapshot"]["label"] == "ready"


def test_collect_report_executes_read_only_sql_with_dict_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def execute(self, sql: str) -> None:
            captured["sql"] = sql

        def fetchone(self) -> dict[str, object]:
            return sample_row()

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def cursor(self, row_factory=None) -> FakeCursor:
            captured["row_factory"] = row_factory
            return FakeCursor()

    class FakePsycopg:
        @staticmethod
        def connect(*, conninfo: str) -> FakeConnection:
            captured["conninfo"] = conninfo
            return FakeConnection()

    monkeypatch.setattr(
        explore_readiness,
        "require_psycopg",
        lambda: (FakePsycopg, dict_row_sentinel),
    )
    monkeypatch.setattr(explore_readiness, "build_pg_conninfo_from_env", lambda: "fake")

    report = explore_readiness.collect_report()

    assert captured["conninfo"] == "fake"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["sql"] == explore_readiness.EXPLORE_READINESS_SQL
    assert report.active_game_count == 10


def test_sql_pins_explore_coverage_semantics() -> None:
    sql = explore_readiness.EXPLORE_READINESS_SQL.lower()

    assert "from tracked_game as tg" in sql
    assert "where tg.is_active = true" in sql
    assert "from agg_steam_ccu_daily" in sql
    assert "selected_daily_rollup_days = 7" in sql
    assert "previous_daily_rollup_days = 7" in sql
    assert "from fact_steam_ccu_30m" in sql
    assert "at time zone 'asia/seoul'" in sql
    assert "having count(distinct bucket_time) = 48" in sql
    assert "selected_raw_bucket_count = 336" in sql
    assert "previous_raw_bucket_count = 336" in sql
    assert "from fact_steam_reviews_daily" in sql
    assert "current_reviews.snapshot_date = ra.anchor_date" in sql
    assert "boundary_7d.snapshot_date = ra.anchor_date - 7" in sql
    assert "boundary_14d.snapshot_date = ra.anchor_date - 14" in sql
    assert "boundary_30d.snapshot_date = ra.anchor_date - 30" in sql
    assert "boundary_60d.snapshot_date = ra.anchor_date - 60" in sql
    assert "insert " not in sql
    assert "update " not in sql
    assert "delete " not in sql
