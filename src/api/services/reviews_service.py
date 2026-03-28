"""Service functions for latest Steam reviews API responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.ccu_service import build_pg_conninfo_from_env, require_psycopg

GET_LATEST_BY_GAME_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    snapshot_date,
    total_reviews,
    total_positive,
    total_negative,
    positive_ratio,
    delta_total_reviews,
    delta_positive_ratio,
    prev_day_total_reviews
FROM srv_game_latest_reviews
WHERE canonical_game_id = %s
LIMIT 1
"""

LIST_LATEST_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    snapshot_date,
    total_reviews,
    total_positive,
    total_negative,
    positive_ratio,
    delta_total_reviews,
    delta_positive_ratio,
    prev_day_total_reviews
FROM srv_game_latest_reviews
ORDER BY priority, canonical_game_id
LIMIT %s
"""


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one DB row from srv_game_latest_reviews to API response shape."""

    delta_total_reviews_raw = row.get("delta_total_reviews")
    delta_positive_ratio_raw = row.get("delta_positive_ratio")

    return {
        "canonical_game_id": int(row["canonical_game_id"]),
        "canonical_name": str(row["canonical_name"]),
        "snapshot_date": row["snapshot_date"],
        "total_reviews": int(row["total_reviews"]),
        "total_positive": int(row["total_positive"]),
        "total_negative": int(row["total_negative"]),
        "positive_ratio": float(row["positive_ratio"]),
        "delta_total_reviews": (
            int(delta_total_reviews_raw) if delta_total_reviews_raw is not None else None
        ),
        "delta_positive_ratio": (
            float(delta_positive_ratio_raw) if delta_positive_ratio_raw is not None else None
        ),
        "missing_flag": row.get("prev_day_total_reviews") is None,
    }


def get_latest_reviews_by_game(canonical_game_id: int) -> dict[str, Any] | None:
    """Return latest reviews row for one canonical game id from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(GET_LATEST_BY_GAME_SQL, (canonical_game_id,))
            row = cursor.fetchone()

    if row is None:
        return None
    return to_response_record(row)


def list_latest_reviews(limit: int = 50) -> list[dict[str, Any]]:
    """Return latest reviews rows for active games from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_LATEST_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]
