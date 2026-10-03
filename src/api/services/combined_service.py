"""Service functions for separate Combined overview and activity API responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.ccu_service import build_pg_conninfo_from_env, require_psycopg

LIST_COMBINED_GAME_OVERVIEW_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    steam_appid,
    steam_source_available,
    chzzk_mapping_available,
    chzzk_category_id,
    category_name,
    category_type,
    latest_bucket_time
FROM srv_combined_game_overview
ORDER BY canonical_game_id ASC
LIMIT %s
"""


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one srv_combined_game_overview row to the public API shape."""

    return {
        "canonical_game_id": int(row["canonical_game_id"]),
        "canonical_name": str(row["canonical_name"]),
        "steam_appid": _optional_int(row.get("steam_appid")),
        "steam_source_available": bool(row["steam_source_available"]),
        "chzzk_mapping_available": bool(row["chzzk_mapping_available"]),
        "chzzk_category_id": _optional_str(row.get("chzzk_category_id")),
        "category_name": _optional_str(row.get("category_name")),
        "category_type": _optional_str(row.get("category_type")),
        "latest_bucket_time": row.get("latest_bucket_time"),
    }


def list_game_overview(limit: int = 50) -> list[dict[str, Any]]:
    """Return minimal Combined overview rows sorted by canonical game id."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_COMBINED_GAME_OVERVIEW_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]


LIST_COMBINED_GAME_ACTIVITY_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    steam_appid,
    ccu_period_anchor_date,
    period_avg_ccu_7d,
    period_peak_ccu_7d,
    chzzk_mapped_category_count,
    chzzk_viewer_hours_observed_7d,
    chzzk_peak_viewers_observed_7d,
    chzzk_observed_bucket_count_7d,
    chzzk_collection_bucket_count_7d,
    chzzk_observation_ratio_7d,
    chzzk_latest_observed_bucket_7d,
    bounded_sample_caveat
FROM srv_combined_game_activity_7d
ORDER BY canonical_game_id ASC
LIMIT %s
"""


def list_game_activity(limit: int = 50) -> list[dict[str, Any]]:
    """Read the activity serving boundary without recomputing its joins or metrics."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_COMBINED_GAME_ACTIVITY_SQL, (limit,))
            rows = cursor.fetchall()

    return [dict(row) for row in rows]
