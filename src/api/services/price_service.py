"""Service functions for latest Steam price API responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.ccu_service import build_pg_conninfo_from_env, require_psycopg

PRICE_REGION_KR = "KR"

GET_LATEST_BY_GAME_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    bucket_time,
    region,
    currency_code,
    initial_price_minor,
    final_price_minor,
    discount_percent,
    is_free
FROM srv_game_latest_price
WHERE canonical_game_id = %s
LIMIT 1
"""

LIST_LATEST_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    bucket_time,
    region,
    currency_code,
    initial_price_minor,
    final_price_minor,
    discount_percent,
    is_free
FROM srv_game_latest_price
ORDER BY priority, canonical_game_id
LIMIT %s
"""


def to_public_price_region(value: object) -> str:
    """Return the current public latest-price region contract."""

    region = str(value).strip().upper()
    if region != PRICE_REGION_KR:
        raise ValueError(f"unexpected latest price region: {region}")
    return PRICE_REGION_KR


def _optional_int(value: Any) -> int | None:
    """Return int(value) while preserving None."""

    return int(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    """Return str(value) while preserving None."""

    return str(value) if value is not None else None


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one DB row from srv_game_latest_price to API response shape."""

    is_free_raw = row.get("is_free")

    return {
        "canonical_game_id": int(row["canonical_game_id"]),
        "canonical_name": str(row["canonical_name"]),
        "bucket_time": row["bucket_time"],
        "region": to_public_price_region(row["region"]),
        "currency_code": _optional_str(row.get("currency_code")),
        "initial_price_minor": _optional_int(row.get("initial_price_minor")),
        "final_price_minor": _optional_int(row.get("final_price_minor")),
        "discount_percent": _optional_int(row.get("discount_percent")),
        "is_free": None if is_free_raw is None else bool(is_free_raw),
    }


def get_latest_price_by_game(canonical_game_id: int) -> dict[str, Any] | None:
    """Return latest KR price row for one canonical game id from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(GET_LATEST_BY_GAME_SQL, (canonical_game_id,))
            row = cursor.fetchone()

    if row is None:
        return None
    return to_response_record(row)


def list_latest_price(limit: int = 50) -> list[dict[str, Any]]:
    """Return latest KR price rows for active games from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_LATEST_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]
