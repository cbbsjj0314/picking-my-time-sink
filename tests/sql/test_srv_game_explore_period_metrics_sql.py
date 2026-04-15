from __future__ import annotations

from pathlib import Path

VIEW_PATH = Path("sql/postgres/024_srv_game_explore_period_metrics.sql")


def test_explore_view_pins_active_universe_and_metric_anchors() -> None:
    sql = VIEW_PATH.read_text(encoding="utf-8").lower()

    assert "create or replace view srv_game_explore_period_metrics" in sql
    assert "from tracked_game as tg" in sql
    assert "where tg.is_active = true" in sql
    assert "select max(bucket_date) as anchor_date" in sql
    assert "from agg_steam_ccu_daily" in sql
    assert "select max(snapshot_date) as anchor_date" in sql
    assert "from fact_steam_reviews_daily" in sql


def test_explore_view_requires_full_7d_ccu_windows() -> None:
    sql = VIEW_PATH.read_text(encoding="utf-8").lower()

    assert "ca.anchor_date - 6" in sql
    assert "ca.anchor_date - 13" in sql
    assert "ca.anchor_date - 7" in sql
    assert "count(agg.bucket_date) filter" in sql
    assert ") = 7" in sql
    assert "period_avg_ccu_7d" in sql
    assert "period_peak_ccu_7d" in sql
    assert "delta_period_avg_ccu_7d_pct" in sql
    assert "previous_period_avg_ccu_7d <= 0.0" in sql
    assert "previous_period_peak_ccu_7d <= 0" in sql


def test_explore_view_uses_review_boundary_snapshots_without_gap_fill() -> None:
    sql = VIEW_PATH.read_text(encoding="utf-8").lower()

    assert "current_reviews.snapshot_date = ra.anchor_date" in sql
    assert "boundary_7d.snapshot_date = ra.anchor_date - 7" in sql
    assert "boundary_30d.snapshot_date = ra.anchor_date - 30" in sql
    assert "total_reviews - boundary_7d_total_reviews < 0" in sql
    assert "positive_added_7d > reviews_added_7d" in sql
    assert "positive_added_30d > reviews_added_30d" in sql
    assert "period_positive_ratio_7d" in sql
    assert "period_positive_ratio_30d" in sql


def test_explore_view_keeps_top_selling_out_of_explore_contract() -> None:
    sql = VIEW_PATH.read_text(encoding="utf-8").lower()

    assert "srv_game_latest_ccu" in sql
    assert "srv_game_latest_price" in sql
    assert "srv_rank_latest_kr_top_selling" not in sql
    assert "fact_steam_rank_daily" not in sql
