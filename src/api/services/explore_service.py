"""Service functions for Steam Explore overview API responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.ccu_service import build_pg_conninfo_from_env, require_psycopg

LIST_EXPLORE_OVERVIEW_SQL = """
SELECT
    canonical_game_id,
    canonical_name,
    steam_appid,
    ccu_bucket_time,
    current_ccu,
    current_delta_ccu_abs,
    current_delta_ccu_pct,
    current_ccu_missing_flag,
    ccu_period_anchor_date,
    period_avg_ccu_7d,
    period_peak_ccu_7d,
    delta_period_avg_ccu_7d_abs,
    delta_period_avg_ccu_7d_pct,
    delta_period_peak_ccu_7d_abs,
    delta_period_peak_ccu_7d_pct,
    reviews_snapshot_date,
    total_reviews,
    total_positive,
    total_negative,
    positive_ratio,
    reviews_added_7d,
    reviews_added_30d,
    period_positive_ratio_7d,
    period_positive_ratio_30d,
    price_bucket_time,
    region,
    currency_code,
    initial_price_minor,
    final_price_minor,
    discount_percent,
    is_free
FROM srv_game_explore_period_metrics
ORDER BY period_avg_ccu_7d DESC NULLS LAST, canonical_game_id ASC
LIMIT %s
"""


def _optional_int(value: Any) -> int | None:
    """Return int(value) while preserving None."""

    return int(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    """Return float(value) while preserving None."""

    return float(value) if value is not None else None


def _optional_bool(value: Any) -> bool | None:
    """Return bool(value) while preserving None."""

    return bool(value) if value is not None else None


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one DB row from srv_game_explore_period_metrics to API response shape."""

    return {
        "canonical_game_id": int(row["canonical_game_id"]),
        "canonical_name": str(row["canonical_name"]),
        "steam_appid": _optional_int(row.get("steam_appid")),
        "ccu_bucket_time": row.get("ccu_bucket_time"),
        "current_ccu": _optional_int(row.get("current_ccu")),
        "current_delta_ccu_abs": _optional_int(row.get("current_delta_ccu_abs")),
        "current_delta_ccu_pct": _optional_float(row.get("current_delta_ccu_pct")),
        "current_ccu_missing_flag": bool(row["current_ccu_missing_flag"]),
        "ccu_period_anchor_date": row.get("ccu_period_anchor_date"),
        "period_avg_ccu_7d": _optional_float(row.get("period_avg_ccu_7d")),
        "period_peak_ccu_7d": _optional_int(row.get("period_peak_ccu_7d")),
        "delta_period_avg_ccu_7d_abs": _optional_float(
            row.get("delta_period_avg_ccu_7d_abs")
        ),
        "delta_period_avg_ccu_7d_pct": _optional_float(
            row.get("delta_period_avg_ccu_7d_pct")
        ),
        "delta_period_peak_ccu_7d_abs": _optional_int(
            row.get("delta_period_peak_ccu_7d_abs")
        ),
        "delta_period_peak_ccu_7d_pct": _optional_float(
            row.get("delta_period_peak_ccu_7d_pct")
        ),
        "reviews_snapshot_date": row.get("reviews_snapshot_date"),
        "total_reviews": _optional_int(row.get("total_reviews")),
        "total_positive": _optional_int(row.get("total_positive")),
        "total_negative": _optional_int(row.get("total_negative")),
        "positive_ratio": _optional_float(row.get("positive_ratio")),
        "reviews_added_7d": _optional_int(row.get("reviews_added_7d")),
        "reviews_added_30d": _optional_int(row.get("reviews_added_30d")),
        "period_positive_ratio_7d": _optional_float(
            row.get("period_positive_ratio_7d")
        ),
        "period_positive_ratio_30d": _optional_float(
            row.get("period_positive_ratio_30d")
        ),
        "price_bucket_time": row.get("price_bucket_time"),
        "region": str(row["region"]) if row.get("region") is not None else None,
        "currency_code": (
            str(row["currency_code"]) if row.get("currency_code") is not None else None
        ),
        "initial_price_minor": _optional_int(row.get("initial_price_minor")),
        "final_price_minor": _optional_int(row.get("final_price_minor")),
        "discount_percent": _optional_int(row.get("discount_percent")),
        "is_free": _optional_bool(row.get("is_free")),
    }


def list_explore_overview(limit: int = 50) -> list[dict[str, Any]]:
    """Return Explore overview rows sorted by 7-day average CCU, nulls last."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_EXPLORE_OVERVIEW_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]
