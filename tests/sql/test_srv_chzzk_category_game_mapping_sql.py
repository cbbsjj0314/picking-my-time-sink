from __future__ import annotations

from pathlib import Path

VIEW_PATH = Path("sql/postgres/027_srv_chzzk_category_game_mapping.sql")


def _read_sql() -> str:
    return VIEW_PATH.read_text(encoding="utf-8").lower()


def test_trusted_mapping_view_pins_name_and_trusted_source() -> None:
    sql = _read_sql()

    assert "create or replace view srv_chzzk_category_game_mapping" in sql
    assert "from chzzk_category_game_mapping as mapping" in sql
    assert "where mapping.mapping_status = 'trusted'" in sql
    assert "chzzk_category_game_candidate" not in sql


def test_trusted_mapping_view_joins_canonical_game_identity() -> None:
    sql = _read_sql()

    assert "inner join dim_game as game" in sql
    assert "game.canonical_game_id = mapping.canonical_game_id" in sql
    assert "mapping.canonical_game_id as mapped_canonical_game_id" in sql
    assert "game.canonical_name as mapped_canonical_game_name" in sql
    assert "game.canonical_game_name" not in sql


def test_trusted_mapping_view_uses_nullable_latest_category_context() -> None:
    sql = _read_sql()

    assert "latest_category_rows as" in sql
    assert "select distinct on (chzzk_category_id)" in sql
    assert "from fact_chzzk_category_30m" in sql
    assert (
        "order by chzzk_category_id, bucket_time desc, collected_at desc, ingested_at desc"
        in sql
    )
    assert "left join latest_category_rows as latest" in sql
    assert "latest.category_name" in sql
    assert "latest.category_type" in sql
    assert "latest.latest_bucket_time" in sql


def test_trusted_mapping_view_keeps_private_and_unrelated_surfaces_out() -> None:
    sql = _read_sql()

    forbidden_needles = [
        "reviewed_by",
        "source_kind",
        "reviewed_at",
        "manual_hint",
        "candidate_status",
        "status as",
        "game_external_id",
        "tracked_game",
        "tracked_universe",
        "app_catalog",
        "combined",
        "/chzzk/",
    ]
    for needle in forbidden_needles:
        assert needle not in sql
