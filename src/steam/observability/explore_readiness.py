"""Read-only coverage readiness report for Steam Explore period columns."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "1.0"
EXPECTED_DAILY_ROLLUP_DAYS = 7
EXPECTED_RAW_7D_BUCKETS = 336
KST_TIME_ZONE = "Asia/Seoul"

EXPLORE_READINESS_SQL = f"""
WITH active_games AS (
    SELECT
        tg.canonical_game_id
    FROM tracked_game AS tg
    INNER JOIN dim_game AS dg
        ON dg.canonical_game_id = tg.canonical_game_id
    LEFT JOIN game_external_id AS gei
        ON gei.canonical_game_id = tg.canonical_game_id
       AND gei.source = 'steam'
    WHERE tg.is_active = TRUE
),
ccu_anchor AS (
    SELECT MAX(bucket_date) AS anchor_date
    FROM agg_steam_ccu_daily
),
daily_ccu_coverage AS (
    SELECT
        ag.canonical_game_id,
        COUNT(agg.bucket_date) FILTER (
            WHERE agg.bucket_date BETWEEN ca.anchor_date - 6 AND ca.anchor_date
        ) AS selected_daily_rollup_days,
        COUNT(agg.bucket_date) FILTER (
            WHERE agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date - 7
        ) AS previous_daily_rollup_days
    FROM active_games AS ag
    CROSS JOIN ccu_anchor AS ca
    LEFT JOIN agg_steam_ccu_daily AS agg
        ON agg.canonical_game_id = ag.canonical_game_id
       AND agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date
    GROUP BY ag.canonical_game_id
),
raw_ccu_complete_dates AS (
    SELECT (bucket_time AT TIME ZONE '{KST_TIME_ZONE}')::DATE AS bucket_date
    FROM fact_steam_ccu_30m
    GROUP BY (bucket_time AT TIME ZONE '{KST_TIME_ZONE}')::DATE
    HAVING COUNT(DISTINCT bucket_time) = 48
),
raw_ccu_anchor AS (
    SELECT MAX(bucket_date) AS anchor_date
    FROM raw_ccu_complete_dates
),
raw_ccu_coverage AS (
    SELECT
        ag.canonical_game_id,
        COUNT(raw_ccu.bucket_time) FILTER (
            WHERE (raw_ccu.bucket_time AT TIME ZONE '{KST_TIME_ZONE}')::DATE
                BETWEEN rca.anchor_date - 6 AND rca.anchor_date
        ) AS selected_raw_bucket_count,
        COUNT(raw_ccu.bucket_time) FILTER (
            WHERE (raw_ccu.bucket_time AT TIME ZONE '{KST_TIME_ZONE}')::DATE
                BETWEEN rca.anchor_date - 13 AND rca.anchor_date - 7
        ) AS previous_raw_bucket_count
    FROM active_games AS ag
    CROSS JOIN raw_ccu_anchor AS rca
    LEFT JOIN fact_steam_ccu_30m AS raw_ccu
        ON raw_ccu.canonical_game_id = ag.canonical_game_id
       AND (raw_ccu.bucket_time AT TIME ZONE '{KST_TIME_ZONE}')::DATE
            BETWEEN rca.anchor_date - 13 AND rca.anchor_date
    GROUP BY ag.canonical_game_id
),
review_anchor AS (
    SELECT MAX(snapshot_date) AS anchor_date
    FROM fact_steam_reviews_daily
),
review_coverage AS (
    SELECT
        ag.canonical_game_id,
        current_reviews.snapshot_date IS NOT NULL AS has_current_snapshot,
        boundary_7d.snapshot_date IS NOT NULL AS has_boundary_7d,
        boundary_14d.snapshot_date IS NOT NULL AS has_boundary_14d,
        boundary_30d.snapshot_date IS NOT NULL AS has_boundary_30d,
        boundary_60d.snapshot_date IS NOT NULL AS has_boundary_60d
    FROM active_games AS ag
    CROSS JOIN review_anchor AS ra
    LEFT JOIN fact_steam_reviews_daily AS current_reviews
        ON current_reviews.canonical_game_id = ag.canonical_game_id
       AND current_reviews.snapshot_date = ra.anchor_date
    LEFT JOIN fact_steam_reviews_daily AS boundary_7d
        ON boundary_7d.canonical_game_id = ag.canonical_game_id
       AND boundary_7d.snapshot_date = ra.anchor_date - 7
    LEFT JOIN fact_steam_reviews_daily AS boundary_14d
        ON boundary_14d.canonical_game_id = ag.canonical_game_id
       AND boundary_14d.snapshot_date = ra.anchor_date - 14
    LEFT JOIN fact_steam_reviews_daily AS boundary_30d
        ON boundary_30d.canonical_game_id = ag.canonical_game_id
       AND boundary_30d.snapshot_date = ra.anchor_date - 30
    LEFT JOIN fact_steam_reviews_daily AS boundary_60d
        ON boundary_60d.canonical_game_id = ag.canonical_game_id
       AND boundary_60d.snapshot_date = ra.anchor_date - 60
)
SELECT
    (SELECT COUNT(*) FROM active_games) AS active_game_count,
    (SELECT anchor_date FROM ccu_anchor) AS ccu_daily_anchor_date,
    (
        SELECT COUNT(*)
        FROM daily_ccu_coverage
        WHERE selected_daily_rollup_days = {EXPECTED_DAILY_ROLLUP_DAYS}
    ) AS selected_daily_ccu_coverage_count,
    (
        SELECT COUNT(*)
        FROM daily_ccu_coverage
        WHERE previous_daily_rollup_days = {EXPECTED_DAILY_ROLLUP_DAYS}
    ) AS previous_daily_ccu_coverage_count,
    (
        SELECT COUNT(*)
        FROM daily_ccu_coverage
        WHERE selected_daily_rollup_days = {EXPECTED_DAILY_ROLLUP_DAYS}
          AND previous_daily_rollup_days = {EXPECTED_DAILY_ROLLUP_DAYS}
    ) AS ccu_delta_daily_coverage_count,
    (SELECT anchor_date FROM raw_ccu_anchor) AS raw_complete_ccu_anchor_date,
    (
        SELECT COUNT(*)
        FROM raw_ccu_coverage
        WHERE selected_raw_bucket_count = {EXPECTED_RAW_7D_BUCKETS}
    ) AS selected_raw_bucket_coverage_count,
    (
        SELECT COUNT(*)
        FROM raw_ccu_coverage
        WHERE previous_raw_bucket_count = {EXPECTED_RAW_7D_BUCKETS}
    ) AS previous_raw_bucket_coverage_count,
    (
        SELECT COUNT(*)
        FROM raw_ccu_coverage
        WHERE selected_raw_bucket_count = {EXPECTED_RAW_7D_BUCKETS}
          AND previous_raw_bucket_count = {EXPECTED_RAW_7D_BUCKETS}
    ) AS player_hours_delta_coverage_count,
    (SELECT MIN(selected_raw_bucket_count) FROM raw_ccu_coverage)
        AS selected_raw_bucket_min,
    (SELECT MAX(selected_raw_bucket_count) FROM raw_ccu_coverage)
        AS selected_raw_bucket_max,
    (SELECT anchor_date FROM review_anchor) AS review_anchor_date,
    (
        SELECT COUNT(*) FROM review_coverage WHERE has_current_snapshot
    ) AS review_current_snapshot_count,
    (
        SELECT COUNT(*) FROM review_coverage WHERE has_boundary_7d
    ) AS review_boundary_7d_count,
    (
        SELECT COUNT(*) FROM review_coverage WHERE has_boundary_14d
    ) AS review_boundary_14d_count,
    (
        SELECT COUNT(*) FROM review_coverage WHERE has_boundary_30d
    ) AS review_boundary_30d_count,
    (
        SELECT COUNT(*) FROM review_coverage WHERE has_boundary_60d
    ) AS review_boundary_60d_count,
    (
        SELECT COUNT(*)
        FROM review_coverage
        WHERE has_current_snapshot AND has_boundary_7d
    ) AS review_7d_metric_coverage_count,
    (
        SELECT COUNT(*)
        FROM review_coverage
        WHERE has_current_snapshot AND has_boundary_7d AND has_boundary_14d
    ) AS review_7d_delta_coverage_count,
    (
        SELECT COUNT(*)
        FROM review_coverage
        WHERE has_current_snapshot AND has_boundary_30d
    ) AS review_30d_metric_coverage_count,
    (
        SELECT COUNT(*)
        FROM review_coverage
        WHERE has_current_snapshot AND has_boundary_30d AND has_boundary_60d
    ) AS review_30d_delta_coverage_count
"""


@dataclass(frozen=True, slots=True)
class ExploreReadinessReport:
    """Coverage counts needed to explain Steam Explore period readiness."""

    active_game_count: int
    ccu_daily_anchor_date: dt.date | None
    selected_daily_ccu_coverage_count: int
    previous_daily_ccu_coverage_count: int
    ccu_delta_daily_coverage_count: int
    raw_complete_ccu_anchor_date: dt.date | None
    selected_raw_bucket_coverage_count: int
    previous_raw_bucket_coverage_count: int
    player_hours_delta_coverage_count: int
    selected_raw_bucket_min: int | None
    selected_raw_bucket_max: int | None
    review_anchor_date: dt.date | None
    review_current_snapshot_count: int
    review_boundary_7d_count: int
    review_boundary_14d_count: int
    review_boundary_30d_count: int
    review_boundary_60d_count: int
    review_7d_metric_coverage_count: int
    review_7d_delta_coverage_count: int
    review_30d_metric_coverage_count: int
    review_30d_delta_coverage_count: int


@dataclass(frozen=True, slots=True)
class ReadinessStatus:
    """Human and machine-readable status for one Explore column group."""

    label: str
    ready_count: int
    active_game_count: int
    message: str


def require_psycopg() -> tuple[Any, Any]:
    """Import psycopg and dict_row, then fail fast when unavailable."""

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency is locked.
        raise RuntimeError("psycopg is required for Explore readiness") from exc

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


def _optional_date(value: object) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise TypeError(f"Expected date-like value, got {type(value).__name__}")


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _required_int(row: Mapping[str, Any], name: str) -> int:
    value = row.get(name)
    return int(value) if value is not None else 0


def report_from_row(row: Mapping[str, Any]) -> ExploreReadinessReport:
    """Map one SQL row into an Explore readiness report."""

    return ExploreReadinessReport(
        active_game_count=_required_int(row, "active_game_count"),
        ccu_daily_anchor_date=_optional_date(row.get("ccu_daily_anchor_date")),
        selected_daily_ccu_coverage_count=_required_int(
            row, "selected_daily_ccu_coverage_count"
        ),
        previous_daily_ccu_coverage_count=_required_int(
            row, "previous_daily_ccu_coverage_count"
        ),
        ccu_delta_daily_coverage_count=_required_int(row, "ccu_delta_daily_coverage_count"),
        raw_complete_ccu_anchor_date=_optional_date(row.get("raw_complete_ccu_anchor_date")),
        selected_raw_bucket_coverage_count=_required_int(
            row, "selected_raw_bucket_coverage_count"
        ),
        previous_raw_bucket_coverage_count=_required_int(
            row, "previous_raw_bucket_coverage_count"
        ),
        player_hours_delta_coverage_count=_required_int(
            row, "player_hours_delta_coverage_count"
        ),
        selected_raw_bucket_min=_optional_int(row.get("selected_raw_bucket_min")),
        selected_raw_bucket_max=_optional_int(row.get("selected_raw_bucket_max")),
        review_anchor_date=_optional_date(row.get("review_anchor_date")),
        review_current_snapshot_count=_required_int(row, "review_current_snapshot_count"),
        review_boundary_7d_count=_required_int(row, "review_boundary_7d_count"),
        review_boundary_14d_count=_required_int(row, "review_boundary_14d_count"),
        review_boundary_30d_count=_required_int(row, "review_boundary_30d_count"),
        review_boundary_60d_count=_required_int(row, "review_boundary_60d_count"),
        review_7d_metric_coverage_count=_required_int(row, "review_7d_metric_coverage_count"),
        review_7d_delta_coverage_count=_required_int(row, "review_7d_delta_coverage_count"),
        review_30d_metric_coverage_count=_required_int(
            row, "review_30d_metric_coverage_count"
        ),
        review_30d_delta_coverage_count=_required_int(
            row, "review_30d_delta_coverage_count"
        ),
    )


def _status_for_count(
    ready_count: int,
    active_game_count: int,
    column_group: str,
) -> ReadinessStatus:
    if active_game_count <= 0:
        label = "no_active_games"
    elif ready_count <= 0:
        label = "waiting"
    elif ready_count >= active_game_count:
        label = "ready"
    else:
        label = "partial"

    return ReadinessStatus(
        label=label,
        ready_count=ready_count,
        active_game_count=active_game_count,
        message=f"{column_group}: {label} ({ready_count}/{active_game_count} active games)",
    )


def build_status(report: ExploreReadinessReport) -> dict[str, ReadinessStatus]:
    """Build readiness status for the Explore column groups."""

    total = report.active_game_count
    return {
        "period_avg_peak_ccu_7d": _status_for_count(
            report.selected_daily_ccu_coverage_count,
            total,
            "Avg/Peak CCU 7d",
        ),
        "period_avg_peak_ccu_7d_delta": _status_for_count(
            report.ccu_delta_daily_coverage_count,
            total,
            "Avg/Peak CCU 7d deltas",
        ),
        "estimated_player_hours_7d": _status_for_count(
            report.selected_raw_bucket_coverage_count,
            total,
            "Estimated Player-Hours 7d",
        ),
        "estimated_player_hours_7d_delta": _status_for_count(
            report.player_hours_delta_coverage_count,
            total,
            "Estimated Player-Hours 7d deltas",
        ),
        "review_current_snapshot": _status_for_count(
            report.review_current_snapshot_count,
            total,
            "Review cumulative snapshot",
        ),
        "review_7d_fields": _status_for_count(
            report.review_7d_metric_coverage_count,
            total,
            "Review 7d fields",
        ),
        "review_7d_delta_fields": _status_for_count(
            report.review_7d_delta_coverage_count,
            total,
            "Review 7d delta fields",
        ),
        "review_30d_fields": _status_for_count(
            report.review_30d_metric_coverage_count,
            total,
            "Review 30d fields",
        ),
        "review_30d_delta_fields": _status_for_count(
            report.review_30d_delta_coverage_count,
            total,
            "Review 30d delta fields",
        ),
    }


def collect_report() -> ExploreReadinessReport:
    """Fetch the read-only Explore readiness report from Postgres."""

    psycopg, dict_row = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(EXPLORE_READINESS_SQL)
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("Explore readiness query returned no rows")
    return report_from_row(row)


def _json_default(value: object) -> str:
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def report_to_payload(report: ExploreReadinessReport) -> dict[str, Any]:
    """Return stable JSON-ready report payload."""

    return {
        "schema_version": SCHEMA_VERSION,
        "expected_daily_rollup_days": EXPECTED_DAILY_ROLLUP_DAYS,
        "expected_raw_7d_buckets": EXPECTED_RAW_7D_BUCKETS,
        "report": asdict(report),
        "status": {name: asdict(status) for name, status in build_status(report).items()},
    }


def render_text(report: ExploreReadinessReport) -> str:
    """Render a concise operator-readable readiness report."""

    status = build_status(report)
    lines = [
        "Steam Explore coverage readiness",
        f"active_tracked_steam_games={report.active_game_count}",
        "",
        "CCU daily rollups:",
        f"  anchor_date={report.ccu_daily_anchor_date or 'missing'}",
        "  selected_7d_avg_peak_coverage="
        f"{report.selected_daily_ccu_coverage_count}/{report.active_game_count}",
        "  previous_7d_avg_peak_delta_coverage="
        f"{report.previous_daily_ccu_coverage_count}/{report.active_game_count}",
        "  delta_ready_coverage="
        f"{report.ccu_delta_daily_coverage_count}/{report.active_game_count}",
        "",
        "Raw CCU 30m player-hours:",
        f"  complete_kst_anchor_date={report.raw_complete_ccu_anchor_date or 'missing'}",
        "  selected_7d_bucket_coverage="
        f"{report.selected_raw_bucket_coverage_count}/{report.active_game_count}",
        "  previous_7d_bucket_coverage="
        f"{report.previous_raw_bucket_coverage_count}/{report.active_game_count}",
        "  delta_ready_coverage="
        f"{report.player_hours_delta_coverage_count}/{report.active_game_count}",
        "  selected_bucket_min_max="
        f"{report.selected_raw_bucket_min or 0}..{report.selected_raw_bucket_max or 0}/"
        f"{EXPECTED_RAW_7D_BUCKETS}",
        "",
        "Review snapshots:",
        f"  anchor_date={report.review_anchor_date or 'missing'}",
        f"  current={report.review_current_snapshot_count}/{report.active_game_count}",
        f"  anchor_minus_7={report.review_boundary_7d_count}/{report.active_game_count}",
        f"  anchor_minus_14={report.review_boundary_14d_count}/{report.active_game_count}",
        f"  anchor_minus_30={report.review_boundary_30d_count}/{report.active_game_count}",
        f"  anchor_minus_60={report.review_boundary_60d_count}/{report.active_game_count}",
        "  review_7d_ready="
        f"{report.review_7d_metric_coverage_count}/{report.active_game_count}",
        "  review_7d_delta_ready="
        f"{report.review_7d_delta_coverage_count}/{report.active_game_count}",
        "  review_30d_ready="
        f"{report.review_30d_metric_coverage_count}/{report.active_game_count}",
        "  review_30d_delta_ready="
        f"{report.review_30d_delta_coverage_count}/{report.active_game_count}",
        "",
        "Status:",
    ]
    lines.extend(f"  {item.message}" for item in status.values())
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the Explore readiness report."""

    parser = argparse.ArgumentParser(
        description="Report read-only Steam Explore period coverage readiness"
    )
    parser.add_argument("--json", action="store_true", help="Render machine-readable JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    report = collect_report()
    if args.json:
        print(
            json.dumps(
                report_to_payload(report),
                default=_json_default,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(render_text(report))


if __name__ == "__main__":
    main()
