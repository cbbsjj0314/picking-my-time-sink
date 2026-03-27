"""Service functions for latest Steam CCU API responses."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

GET_LATEST_BY_GAME_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    bucket_time,
    latest_ccu AS ccu,
    delta_ccu_day AS delta_ccu_abs,
    prev_day_same_bucket_ccu
FROM srv_game_latest_ccu
WHERE canonical_game_id = %s
LIMIT 1
"""

LIST_LATEST_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    bucket_time,
    latest_ccu AS ccu,
    delta_ccu_day AS delta_ccu_abs,
    prev_day_same_bucket_ccu
FROM srv_game_latest_ccu
ORDER BY priority, canonical_game_id
LIMIT %s
"""

GET_RECENT_90D_CCU_DAILY_BY_GAME_SQL = """
SELECT
    canonical_game_id,
    bucket_date,
    avg_ccu,
    peak_ccu
FROM agg_steam_ccu_daily
WHERE canonical_game_id = %s
  AND bucket_date >= ((NOW() AT TIME ZONE 'Asia/Seoul')::date - 89)
  AND bucket_date <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
ORDER BY bucket_date ASC
"""


def require_psycopg() -> tuple[Any, Any]:
    """Import psycopg and dict_row, then fail fast when unavailable."""

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for ccu service") from exc

    return psycopg, dict_row


def get_required_env(name: str) -> str:
    """Return required env value with explicit error on missing."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_pg_conninfo_from_env() -> str:
    """Build Postgres conninfo from POSTGRES_* env variables."""

    host = get_required_env("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = get_required_env("POSTGRES_DB")
    user = get_required_env("POSTGRES_USER")
    password = get_required_env("POSTGRES_PASSWORD")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def compute_delta_ccu_pct(delta_ccu_abs: int | None, prev_day_ccu: int | None) -> float | None:
    """Compute percentage delta when previous-day baseline is valid."""

    if delta_ccu_abs is None or prev_day_ccu is None or prev_day_ccu <= 0:
        return None
    return (delta_ccu_abs / prev_day_ccu) * 100.0


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one DB row from srv_game_latest_ccu to API response shape."""

    prev_day_ccu_raw = row.get("prev_day_same_bucket_ccu")
    prev_day_ccu = int(prev_day_ccu_raw) if prev_day_ccu_raw is not None else None

    delta_ccu_abs_raw = row.get("delta_ccu_abs")
    delta_ccu_abs = int(delta_ccu_abs_raw) if delta_ccu_abs_raw is not None else None

    return {
        "canonical_game_id": int(row["canonical_game_id"]),
        "canonical_name": str(row["canonical_name"]),
        "bucket_time": row["bucket_time"],
        "ccu": int(row["ccu"]),
        "delta_ccu_abs": delta_ccu_abs,
        "delta_ccu_pct": compute_delta_ccu_pct(delta_ccu_abs, prev_day_ccu),
        "missing_flag": prev_day_ccu is None,
    }


def get_latest_ccu_by_game(canonical_game_id: int) -> dict[str, Any] | None:
    """Return latest CCU row for one canonical game id from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(GET_LATEST_BY_GAME_SQL, (canonical_game_id,))
            row = cursor.fetchone()

    if row is None:
        return None
    return to_response_record(row)


def list_latest_ccu(limit: int = 50) -> list[dict[str, Any]]:
    """Return latest CCU rows for active games from serving view."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_LATEST_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]


def get_recent_90d_ccu_daily_by_game(canonical_game_id: int) -> list[dict[str, Any]]:
    """Return recent 90-day daily CCU rows for one game from the daily rollup table."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(GET_RECENT_90D_CCU_DAILY_BY_GAME_SQL, (canonical_game_id,))
            rows = cursor.fetchall()

    return [
        {
            "canonical_game_id": int(row["canonical_game_id"]),
            "bucket_date": row["bucket_date"],
            "avg_ccu": float(row["avg_ccu"]),
            "peak_ccu": int(row["peak_ccu"]),
        }
        for row in rows
    ]
