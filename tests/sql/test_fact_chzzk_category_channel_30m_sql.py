from __future__ import annotations

from pathlib import Path

DDL_PATH = Path("sql/postgres/016_fact_chzzk_category_channel_30m.sql")


def test_chzzk_category_channel_fact_declares_observed_channel_grain() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "create table if not exists fact_chzzk_category_channel_30m" in sql
    assert "chzzk_category_id text not null" in sql
    assert "bucket_time timestamptz not null" in sql
    assert "channel_id text not null" in sql
    assert "category_type text not null" in sql
    assert "category_name text not null" in sql
    assert "concurrent_user_count integer not null" in sql
    assert "collected_at timestamptz not null" in sql
    assert "ingested_at timestamptz not null default now()" in sql
    assert "primary key (" in sql
    assert "chzzk_category_id" in sql
    assert "bucket_time" in sql
    assert "channel_id" in sql


def test_chzzk_category_channel_fact_pins_forbidden_fields_out_of_ddl() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    forbidden_fields = [
        "channel_name",
        "top_channel",
        "live_title",
        "thumbnail",
        "raw_provider_payload",
        "canonical_game_id",
        "game_external_id",
        "srv_",
    ]
    for field_name in forbidden_fields:
        assert field_name not in sql


def test_chzzk_category_channel_fact_has_minimum_quality_constraints() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "category_type in ('game', 'sports', 'entertainment', 'etc')" in sql
    assert "length(btrim(chzzk_category_id)) > 0" in sql
    assert "length(btrim(category_name)) > 0" in sql
    assert "length(btrim(channel_id)) > 0" in sql
    assert "concurrent_user_count >= 0" in sql
    assert "asia/seoul" in sql
    assert "bucket_time desc" in sql
