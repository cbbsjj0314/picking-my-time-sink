"""Service functions for Chzzk category source API responses."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from api.services.ccu_service import build_pg_conninfo_from_env, require_psycopg

EXPECTED_BUCKETS_1D = 48
EXPECTED_BUCKETS_7D = 336
BOUNDED_SAMPLE_CAVEAT = "bounded_sample"

LIST_CATEGORY_OVERVIEW_SQL = """
WITH category_aggregates AS (
    SELECT
        chzzk_category_id,
        COUNT(DISTINCT bucket_time) AS observed_bucket_count,
        MIN(bucket_time) AS bucket_time_min,
        MAX(bucket_time) AS bucket_time_max,
        SUM(concurrent_sum * 0.5) AS viewer_hours_observed,
        AVG(concurrent_sum::DOUBLE PRECISION) AS avg_viewers_observed,
        MAX(concurrent_sum) AS peak_viewers_observed,
        SUM(live_count) AS live_count_observed_total,
        AVG(live_count::DOUBLE PRECISION) AS avg_channels_observed,
        MAX(live_count) AS peak_channels_observed
    FROM fact_chzzk_category_30m
    GROUP BY chzzk_category_id
),
latest_metadata AS (
    SELECT DISTINCT ON (chzzk_category_id)
        chzzk_category_id,
        category_name,
        category_type
    FROM fact_chzzk_category_30m
    ORDER BY chzzk_category_id, bucket_time DESC, collected_at DESC, ingested_at DESC
)
SELECT
    agg.chzzk_category_id,
    meta.category_name,
    meta.category_type,
    agg.observed_bucket_count,
    agg.bucket_time_min,
    agg.bucket_time_max,
    agg.viewer_hours_observed,
    agg.avg_viewers_observed,
    agg.peak_viewers_observed,
    agg.live_count_observed_total,
    agg.avg_channels_observed,
    agg.peak_channels_observed
FROM category_aggregates AS agg
INNER JOIN latest_metadata AS meta
    ON meta.chzzk_category_id = agg.chzzk_category_id
ORDER BY
    agg.viewer_hours_observed DESC,
    agg.peak_viewers_observed DESC,
    agg.chzzk_category_id ASC
LIMIT %s
"""


def _finite_float(value: Any) -> float:
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError("non-finite Chzzk category metric")
    return numeric_value


def _coverage_status(observed_bucket_count: int) -> str:
    if observed_bucket_count >= EXPECTED_BUCKETS_7D:
        return "full_7d_candidate_available"
    if observed_bucket_count >= EXPECTED_BUCKETS_1D:
        return "full_1d_candidate_available"
    if observed_bucket_count <= 1:
        return "observed_bucket_only"
    return "partial_window"


def to_response_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one aggregate DB row to the public Chzzk category overview shape."""

    observed_bucket_count = int(row["observed_bucket_count"])
    return {
        "chzzk_category_id": str(row["chzzk_category_id"]),
        "category_name": str(row["category_name"]),
        "category_type": str(row["category_type"]),
        "observed_bucket_count": observed_bucket_count,
        "bucket_time_min": row["bucket_time_min"],
        "bucket_time_max": row["bucket_time_max"],
        "viewer_hours_observed": _finite_float(row["viewer_hours_observed"]),
        "avg_viewers_observed": _finite_float(row["avg_viewers_observed"]),
        "peak_viewers_observed": int(row["peak_viewers_observed"]),
        "live_count_observed_total": int(row["live_count_observed_total"]),
        "avg_channels_observed": _finite_float(row["avg_channels_observed"]),
        "peak_channels_observed": int(row["peak_channels_observed"]),
        "full_1d_candidate_available": observed_bucket_count >= EXPECTED_BUCKETS_1D,
        "full_7d_candidate_available": observed_bucket_count >= EXPECTED_BUCKETS_7D,
        "missing_1d_bucket_count": max(0, EXPECTED_BUCKETS_1D - observed_bucket_count),
        "missing_7d_bucket_count": max(0, EXPECTED_BUCKETS_7D - observed_bucket_count),
        "coverage_status": _coverage_status(observed_bucket_count),
        "bounded_sample_caveat": BOUNDED_SAMPLE_CAVEAT,
    }


def list_category_overview(limit: int = 50) -> list[dict[str, Any]]:
    """Return Chzzk category observed sample metrics from the category fact table."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(LIST_CATEGORY_OVERVIEW_SQL, (limit,))
            rows = cursor.fetchall()

    return [to_response_record(row) for row in rows]
