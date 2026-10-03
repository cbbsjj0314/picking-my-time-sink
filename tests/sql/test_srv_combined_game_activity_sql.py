"""Execute the checked-in view against synthetic inputs; never connect to live DBs."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import duckdb
import pytest

VIEW_PATH = Path("sql/postgres/029_srv_combined_game_activity_7d.sql")
ANCHOR = dt.date(2026, 10, 3)


@pytest.fixture
def db():
    with duckdb.connect(":memory:") as conn:
        conn.execute("""
            CREATE TABLE srv_game_explore_period_metrics (
                canonical_game_id BIGINT, canonical_name TEXT, steam_appid BIGINT,
                ccu_period_anchor_date DATE, period_avg_ccu_7d DOUBLE,
                period_peak_ccu_7d BIGINT
            );
            CREATE TABLE srv_chzzk_category_game_mapping (
                mapped_canonical_game_id BIGINT, chzzk_category_id TEXT
            );
            CREATE TABLE fact_chzzk_category_30m (
                chzzk_category_id TEXT, bucket_time TIMESTAMPTZ, concurrent_sum INTEGER,
                PRIMARY KEY (chzzk_category_id, bucket_time)
            );
        """)
        conn.executemany(
            "INSERT INTO srv_game_explore_period_metrics VALUES (?, ?, ?, ?, ?, ?)",
            [(i, f"Synthetic Game {i}", 100 + i, ANCHOR, 100.0, 200) for i in range(1, 5)],
        )
        conn.execute("""
            INSERT INTO srv_chzzk_category_game_mapping VALUES
                (1, 'a'), (1, 'b'), (1, 'unseen'), (2, 'missing'), (3, 'zero'),
                (99, 'inactive');
        """)
        conn.execute(VIEW_PATH.read_text())
        yield conn


def rows(db):
    # Cast only at the test output boundary to avoid DuckDB's optional pytz adapter.
    result = db.execute("""
        SELECT * REPLACE (CAST(chzzk_latest_observed_bucket_7d AS VARCHAR)
            AS chzzk_latest_observed_bucket_7d)
        FROM srv_combined_game_activity_7d ORDER BY canonical_game_id
    """)
    columns = [column[0] for column in result.description]
    records = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    for record in records:
        latest = record["chzzk_latest_observed_bucket_7d"]
        if latest is not None:
            record["chzzk_latest_observed_bucket_7d"] = dt.datetime.fromisoformat(latest)
    return records


def add_facts(db, facts):
    db.executemany("INSERT INTO fact_chzzk_category_30m VALUES (?, ?, ?)", facts)


def test_view_has_only_approved_persisted_inputs_and_no_activity_shortcuts():
    sql = VIEW_PATH.read_text().lower()
    relations = set(re.findall(r"(?:from|join)\s+([a-z_0-9]+)", sql))
    assert relations == {
        "srv_chzzk_category_game_mapping", "srv_game_explore_period_metrics",
        "fact_chzzk_category_30m", "trusted_categories", "shared_windows", "window_facts",
        "game_buckets", "mapped_games", "game_activity", "collection_buckets",
    }
    for forbidden in ("336", "row_number", "candidate", "fuzzy", "fallback", "score",
                      "ranking", "recommendation", "generate_series"):
        assert forbidden not in sql
    # The upstream boundary is the existing active tracked-game universe.
    steam_sql = Path("sql/postgres/024_srv_game_explore_period_metrics.sql").read_text().lower()
    assert "where tg.is_active = true" in steam_sql
    mapping_sql = Path("sql/postgres/027_srv_chzzk_category_game_mapping.sql").read_text().lower()
    assert "where mapping.mapping_status = 'trusted'" in mapping_sql


def test_merges_categories_before_peak_hours_and_distinct_game_bucket_count(db):
    add_facts(db, [
        ('a', '2026-10-01 00:00:00+09', 10),
        ('b', '2026-10-01 00:00:00+09', 20),
        ('a', '2026-10-01 00:30:00+09', 4),
        ('unmapped', '2026-10-01 01:00:00+09', 500),
    ])
    result = rows(db)
    assert [row["canonical_game_id"] for row in result] == [1, 2, 3]
    game = result[0]
    assert game["chzzk_mapped_category_count"] == 3
    assert game["chzzk_viewer_hours_observed_7d"] == 17
    assert game["chzzk_peak_viewers_observed_7d"] == 30
    assert game["chzzk_observed_bucket_count_7d"] == 2
    assert game["chzzk_collection_bucket_count_7d"] == 3
    assert game["chzzk_observation_ratio_7d"] == pytest.approx(2 / 3)
    assert game["chzzk_latest_observed_bucket_7d"] == dt.datetime.fromisoformat(
        '2026-10-01T00:30:00+09:00'
    )
    assert game["period_avg_ccu_7d"] == 100
    assert game["period_peak_ccu_7d"] == 200
    assert game["bounded_sample_caveat"] == "bounded_sample"


def test_global_denominator_includes_unmapped_and_inactive_game_categories(db):
    add_facts(db, [
        ('unmapped', '2026-10-01 00:00:00+09', 100),
        ('inactive', '2026-10-01 00:00:00+09', 100),
        ('inactive', '2026-10-01 00:30:00+09', 100),
    ])
    for game in rows(db):
        assert game["chzzk_collection_bucket_count_7d"] == 2
        assert game["chzzk_observed_bucket_count_7d"] == 0
        assert game["chzzk_observation_ratio_7d"] == 0
        assert game["chzzk_viewer_hours_observed_7d"] is None
        assert game["chzzk_peak_viewers_observed_7d"] is None
        assert game["chzzk_latest_observed_bucket_7d"] is None


def test_shared_steam_anchor_uses_exact_kst_boundaries_not_latest_chzzk_date(db):
    add_facts(db, [
        ('a', '2026-09-26 14:30:00+00', 1000),  # Before Sep 27 KST.
        ('a', '2026-09-26 15:00:00+00', 2),
        ('a', '2026-10-03 14:30:00+00', 6),
        ('a', '2026-10-03 15:00:00+00', 1000),  # Oct 4 KST.
        ('a', '2026-10-10 00:00:00+09', 1000),
    ])
    game = rows(db)[0]
    assert game["ccu_period_anchor_date"] == ANCHOR
    assert game["chzzk_viewer_hours_observed_7d"] == 4
    assert game["chzzk_peak_viewers_observed_7d"] == 6
    assert game["chzzk_observed_bucket_count_7d"] == 2
    assert game["chzzk_collection_bucket_count_7d"] == 2


def test_missing_differs_from_persisted_observed_zero(db):
    add_facts(db, [('zero', '2026-10-01 00:00:00+09', 0)])
    missing, zero = rows(db)[1:]
    assert missing["chzzk_observed_bucket_count_7d"] == 0
    assert missing["chzzk_observation_ratio_7d"] == 0
    for field in ("chzzk_viewer_hours_observed_7d", "chzzk_peak_viewers_observed_7d",
                  "chzzk_latest_observed_bucket_7d"):
        assert missing[field] is None
    assert zero["chzzk_viewer_hours_observed_7d"] == 0
    assert zero["chzzk_peak_viewers_observed_7d"] == 0
    assert zero["chzzk_observed_bucket_count_7d"] == 1
    assert zero["chzzk_observation_ratio_7d"] == 1
    assert zero["chzzk_latest_observed_bucket_7d"] is not None


def test_anchor_with_no_global_buckets_has_zero_counts_but_null_ratio(db):
    for game in rows(db):
        assert game["chzzk_collection_bucket_count_7d"] == 0
        assert game["chzzk_observed_bucket_count_7d"] == 0
        assert game["chzzk_observation_ratio_7d"] is None
        assert game["chzzk_viewer_hours_observed_7d"] is None
        assert game["chzzk_peak_viewers_observed_7d"] is None
        assert game["chzzk_latest_observed_bucket_7d"] is None


def test_null_anchor_keeps_all_window_derived_chzzk_fields_unknown(db):
    add_facts(db, [('a', '2026-10-01 00:00:00+09', 10)])
    db.execute("UPDATE srv_game_explore_period_metrics SET ccu_period_anchor_date = NULL")
    for game in rows(db):
        assert game["ccu_period_anchor_date"] is None
        assert game["chzzk_mapped_category_count"] >= 1
        for field, value in game.items():
            if field.startswith("chzzk_") and field.endswith("_7d"):
                assert value is None, field

