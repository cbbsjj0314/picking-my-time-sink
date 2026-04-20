from __future__ import annotations

from pathlib import Path

DDL_PATH = Path("sql/postgres/015_fact_chzzk_category_30m.sql")


def test_chzzk_category_fact_declares_provider_specific_category_grain() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "create table if not exists fact_chzzk_category_30m" in sql
    assert "chzzk_category_id text not null" in sql
    assert "bucket_time timestamptz not null" in sql
    assert "category_type text not null" in sql
    assert "category_name text not null" in sql
    assert "concurrent_sum integer not null" in sql
    assert "live_count integer not null" in sql
    assert "top_channel_id text not null" in sql
    assert "top_channel_name text not null" in sql
    assert "top_channel_concurrent integer not null" in sql
    assert "primary key (chzzk_category_id, bucket_time)" in sql


def test_chzzk_category_fact_keeps_mapping_and_serving_deferred() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "canonical_game_id" not in sql
    assert "game_external_id" not in sql
    assert "srv_" not in sql


def test_chzzk_category_fact_has_minimum_quality_constraints() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "category_type in ('game', 'sports', 'etc')" in sql
    assert "live_count > 0" in sql
    assert "concurrent_sum >= 0" in sql
    assert "top_channel_concurrent <= concurrent_sum" in sql
    assert "asia/seoul" in sql
