"""Service functions for latest Steam rankings API responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.ccu_service import build_pg_conninfo_from_env, require_psycopg

LIST_LATEST_SQL = """
SELECT
    snapshot_date,
    rank_position,
    steam_appid,
    canonical_game_id,
    canonical_name
FROM srv_rank_latest_kr_top_selling
ORDER BY rank_position ASC
LIMIT %s
"""


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one DB row from srv_rank_latest_kr_top_selling to API response shape."""

    canonical_game_id_raw = row.get("canonical_game_id")
    canonical_name_raw = row.get("canonical_name")

    return {
        "snapshot_date": row["snapshot_date"],
        "rank_position": int(row["rank_position"]),
        "steam_appid": int(row["steam_appid"]),
        "canonical_game_id": (
            int(canonical_game_id_raw) if canonical_game_id_raw is not None else None
        ),
        "canonical_name": (
            str(canonical_name_raw) if canonical_name_raw is not None else None
        ),
    }


def list_latest_rankings(limit: int = 50) -> list[dict[str, Any]]:
    """Return latest KR top-selling ranking rows from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_LATEST_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]
