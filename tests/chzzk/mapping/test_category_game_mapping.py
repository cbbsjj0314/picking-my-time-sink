from __future__ import annotations

from pathlib import Path

CANDIDATE_DDL_PATH = Path("sql/postgres/025_chzzk_category_game_candidate.sql")
MAPPING_DDL_PATH = Path("sql/postgres/026_chzzk_category_game_mapping.sql")


def test_trusted_mapping_table_declares_one_mapping_per_category() -> None:
    sql = MAPPING_DDL_PATH.read_text(encoding="utf-8").lower()

    assert "create table if not exists chzzk_category_game_mapping" in sql
    assert "chzzk_category_id text not null" in sql
    assert "canonical_game_id bigint not null" in sql
    assert (
        "constraint chzzk_category_game_mapping_pk primary key (chzzk_category_id)"
        in sql
    )
    assert "references dim_game (canonical_game_id)" in sql


def test_trusted_mapping_table_pins_status_and_source_contract() -> None:
    sql = MAPPING_DDL_PATH.read_text(encoding="utf-8").lower()

    assert "mapping_status text not null default 'trusted'" in sql
    assert "mapping_status in ('trusted')" in sql
    assert "source_kind text not null" in sql
    assert "length(btrim(chzzk_category_id)) > 0" in sql
    assert "length(btrim(source_kind)) > 0" in sql
    assert "source_kind in" not in sql
    assert "manual_hint" not in sql


def test_trusted_mapping_table_has_minimal_provenance_fields() -> None:
    sql = MAPPING_DDL_PATH.read_text(encoding="utf-8").lower()

    assert "source_kind text not null" in sql
    assert "reviewed_by text null" in sql
    assert "reviewed_at timestamptz not null default now()" in sql
    assert "created_at timestamptz not null default now()" in sql
    assert "updated_at timestamptz not null default now()" in sql


def test_trusted_mapping_table_does_not_create_serving_or_combined_surface() -> None:
    sql = MAPPING_DDL_PATH.read_text(encoding="utf-8").lower()

    forbidden_needles = [
        "create view",
        "srv_",
        "combined",
        "api",
        "web",
        "game_external_id",
        "tracked_universe",
        "tracked_game",
    ]
    for needle in forbidden_needles:
        assert needle not in sql


def test_candidate_table_remains_review_only_and_separate_from_trusted_mapping() -> None:
    candidate_sql = CANDIDATE_DDL_PATH.read_text(encoding="utf-8").lower()

    assert "create table if not exists chzzk_category_game_candidate" in candidate_sql
    assert "status in ('candidate', 'unresolved', 'rejected')" in candidate_sql
    assert "trusted" not in candidate_sql
    assert "approved" not in candidate_sql
    assert "mapping_status" not in candidate_sql
    assert "source_kind" not in candidate_sql
    assert "reviewed_by" not in candidate_sql
    assert "reviewed_at" not in candidate_sql
    assert "chzzk_category_game_mapping" not in candidate_sql
