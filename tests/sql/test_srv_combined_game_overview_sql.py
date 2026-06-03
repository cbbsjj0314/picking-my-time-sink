from __future__ import annotations

from pathlib import Path

VIEW_PATH = Path("sql/postgres/028_srv_combined_game_overview.sql")


def _read_sql() -> str:
    return VIEW_PATH.read_text(encoding="utf-8").lower()


def test_combined_view_exists_and_uses_approved_inputs() -> None:
    sql = _read_sql()

    assert "create or replace view srv_combined_game_overview" in sql
    assert "from srv_game_explore_period_metrics as steam" in sql
    assert "from srv_chzzk_category_game_mapping as mapping" in sql
    assert "chzzk_category_game_candidate" not in sql
    assert "get /chzzk/category-game-mappings" not in sql
    assert "/chzzk/category-game-mappings" not in sql


def test_combined_view_exposes_only_approved_fields() -> None:
    sql = _read_sql()

    for expected in [
        "steam.canonical_game_id",
        "steam.canonical_name",
        "steam.steam_appid",
        "true as steam_source_available",
        "mapping.chzzk_category_id is not null as chzzk_mapping_available",
        "mapping.chzzk_category_id",
        "mapping.category_name",
        "mapping.category_type",
        "mapping.latest_bucket_time",
    ]:
        assert expected in sql

    forbidden_needles = [
        "latest_viewers_observed",
        "viewer_hours_observed",
        "avg_viewers_observed",
        "peak_viewers_observed",
        "viewer_per_channel_observed",
        "unique_channels_observed",
        "coverage",
        "rank_position",
        "ranking",
        "kpi",
        "score",
        "recommendation",
        "candidate_id",
        "candidate_status",
        "mapping_status",
        "source_kind",
        "reviewed_by",
        "reviewed_at",
        "fallback",
        "unresolved",
        "rejected",
    ]
    for needle in forbidden_needles:
        assert needle not in sql


def test_combined_view_preserves_steam_row_driver_with_nullable_mapping() -> None:
    sql = _read_sql()

    assert "from srv_game_explore_period_metrics as steam" in sql
    assert "left join trusted_mapping_guard as mapping" in sql
    assert "mapping.mapped_canonical_game_id = steam.canonical_game_id" in sql
    assert "mapping.mapping_guard_rank = 1" in sql


def test_combined_view_uses_non_semantic_deterministic_mapping_guard() -> None:
    sql = _read_sql()

    assert "trusted_mapping_guard as" in sql
    assert "row_number() over" in sql
    assert "partition by mapping.mapped_canonical_game_id" in sql
    assert "order by mapping.chzzk_category_id asc" in sql

    semantic_needles = [
        "representative",
        "best",
        "primary",
        "coverage",
        "latest_viewers",
        "viewer_hours",
        "score",
        "rank_position",
        "ranking",
    ]
    for needle in semantic_needles:
        assert needle not in sql
