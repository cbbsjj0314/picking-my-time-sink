"""Aggregate Steam CCU gold fact rows into daily rollups."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    utc_now_iso,
)
from steam.normalize.bronze_to_silver_ccu import parse_timestamp, to_kst_datetime

LOGGER = logging.getLogger(__name__)


SELECT_FACT_ROWS_SQL = """
SELECT
    canonical_game_id,
    bucket_time,
    ccu
FROM fact_steam_ccu_30m
ORDER BY canonical_game_id, bucket_time
"""


UPSERT_SQL = """
INSERT INTO agg_steam_ccu_daily (
    canonical_game_id,
    bucket_date,
    avg_ccu,
    peak_ccu
)
VALUES (%s, %s, %s, %s)
ON CONFLICT (canonical_game_id, bucket_date)
DO UPDATE SET
    avg_ccu = EXCLUDED.avg_ccu,
    peak_ccu = EXCLUDED.peak_ccu,
    ingested_at = NOW()
"""


SELECT_AGG_KEYS_SQL = """
SELECT
    canonical_game_id,
    bucket_date
FROM agg_steam_ccu_daily
ORDER BY canonical_game_id, bucket_date
"""


DELETE_AGG_ROW_SQL = """
DELETE FROM agg_steam_ccu_daily
WHERE canonical_game_id = %s
  AND bucket_date = %s
"""


def configure_logging() -> None:
    """Use a compact logger format for normalization scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def require_psycopg() -> Any:
    """Import psycopg and fail fast when dependency is missing."""

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for Steam CCU daily rollup") from exc
    return psycopg


def get_required_env(name: str) -> str:
    """Read required environment variable or raise clear error."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_pg_conninfo_from_env() -> str:
    """Build Postgres conninfo from environment variables."""

    host = get_required_env("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = get_required_env("POSTGRES_DB")
    user = get_required_env("POSTGRES_USER")
    password = get_required_env("POSTGRES_PASSWORD")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL output for aggregation results."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def parse_bucket_time(value: Any) -> dt.datetime:
    """Parse one fact bucket timestamp with explicit timezone handling."""

    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            raise ValueError("bucket_time must include timezone")
        return value
    return parse_timestamp(str(value))


def bucket_date_from_bucket_time(bucket_time: dt.datetime) -> dt.date:
    """Derive KST bucket_date from the fact bucket_time instant."""

    return to_kst_datetime(bucket_time).date()


def build_result_row(
    *,
    canonical_game_id: int,
    bucket_date: dt.date,
    avg_ccu: float,
    peak_ccu: int,
) -> dict[str, Any]:
    """Build deterministic result row for one daily CCU rollup."""

    return {
        "avg_ccu": avg_ccu,
        "bucket_date": bucket_date.isoformat(),
        "canonical_game_id": canonical_game_id,
        "peak_ccu": peak_ccu,
    }


def upsert_agg_ccu_daily_row(
    cursor: Any,
    *,
    canonical_game_id: int,
    bucket_date: dt.date,
    avg_ccu: float,
    peak_ccu: int,
) -> None:
    """Upsert one daily CCU rollup row using the table grain PK."""

    cursor.execute(
        UPSERT_SQL,
        (
            canonical_game_id,
            bucket_date,
            avg_ccu,
            peak_ccu,
        ),
    )


def load_agg_keys(cursor: Any) -> set[tuple[int, dt.date]]:
    """Load existing daily rollup keys for stale-row reconciliation."""

    cursor.execute(SELECT_AGG_KEYS_SQL)
    return {
        (int(canonical_game_id), bucket_date)
        for canonical_game_id, bucket_date in cursor.fetchall()
    }


def delete_agg_ccu_daily_row(
    cursor: Any,
    *,
    canonical_game_id: int,
    bucket_date: dt.date,
) -> None:
    """Delete one daily CCU rollup row by primary key."""

    cursor.execute(DELETE_AGG_ROW_SQL, (canonical_game_id, bucket_date))


def load_fact_rows(cursor: Any) -> list[dict[str, Any]]:
    """Load all CCU fact rows needed for a full daily rollup recompute."""

    cursor.execute(SELECT_FACT_ROWS_SQL)
    return [
        {
            "bucket_time": bucket_time,
            "canonical_game_id": canonical_game_id,
            "ccu": ccu,
        }
        for canonical_game_id, bucket_time, ccu in cursor.fetchall()
    ]


def process_fact_rows(
    fact_rows: list[Mapping[str, Any]],
    *,
    upsert_row: Callable[[int, dt.date, float, int], None],
    delete_missing_rows: Callable[[set[tuple[int, dt.date]]], None] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate fact rows into daily rollups and upsert them."""

    grouped: dict[tuple[int, dt.date], dict[str, float | int]] = {}

    for row in fact_rows:
        canonical_game_id = int(row["canonical_game_id"])
        bucket_time = parse_bucket_time(row["bucket_time"])
        bucket_date = bucket_date_from_bucket_time(bucket_time)
        ccu = int(row["ccu"])

        key = (canonical_game_id, bucket_date)
        current = grouped.get(key)
        if current is None:
            grouped[key] = {
                "count": 1,
                "peak_ccu": ccu,
                "sum_ccu": ccu,
            }
            continue

        current["count"] = int(current["count"]) + 1
        current["sum_ccu"] = int(current["sum_ccu"]) + ccu
        current["peak_ccu"] = max(int(current["peak_ccu"]), ccu)

    if delete_missing_rows is not None:
        delete_missing_rows(set(grouped))

    results: list[dict[str, Any]] = []
    for canonical_game_id, bucket_date in sorted(grouped):
        aggregate = grouped[(canonical_game_id, bucket_date)]
        avg_ccu = int(aggregate["sum_ccu"]) / int(aggregate["count"])
        peak_ccu = int(aggregate["peak_ccu"])
        upsert_row(canonical_game_id, bucket_date, avg_ccu, peak_ccu)
        results.append(
            build_result_row(
                canonical_game_id=canonical_game_id,
                bucket_date=bucket_date,
                avg_ccu=avg_ccu,
                peak_ccu=peak_ccu,
            )
        )

    return results


def run(
    result_path: Path | None = None,
    meta_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Aggregate CCU fact rows into daily rollups and upsert results."""

    started_at_utc = utc_now_iso()
    resolved_meta_path = meta_path or default_meta_path(
        job_name="gold_to_agg_ccu_daily",
        started_at_utc=started_at_utc,
    )

    success = False
    http_status: int | None = None
    retry_count = 0
    timeout_count = 0
    rate_limit_count = 0
    records_in = 0
    records_out = 0
    error_type: str | None = None
    error_message: str | None = None

    results: list[dict[str, Any]] = []
    try:
        psycopg = require_psycopg()
        conninfo = build_pg_conninfo_from_env()

        with psycopg.connect(conninfo=conninfo) as conn:
            with conn.cursor() as cursor:
                fact_rows = load_fact_rows(cursor)
                records_in = len(fact_rows)

                def db_upsert(
                    canonical_game_id: int,
                    bucket_date: dt.date,
                    avg_ccu: float,
                    peak_ccu: int,
                ) -> None:
                    upsert_agg_ccu_daily_row(
                        cursor,
                        canonical_game_id=canonical_game_id,
                        bucket_date=bucket_date,
                        avg_ccu=avg_ccu,
                        peak_ccu=peak_ccu,
                    )

                def db_delete_missing(
                    current_keys: set[tuple[int, dt.date]],
                ) -> None:
                    existing_keys = load_agg_keys(cursor)
                    stale_keys = sorted(existing_keys - current_keys)
                    for canonical_game_id, bucket_date in stale_keys:
                        delete_agg_ccu_daily_row(
                            cursor,
                            canonical_game_id=canonical_game_id,
                            bucket_date=bucket_date,
                        )

                results = process_fact_rows(
                    fact_rows,
                    upsert_row=db_upsert,
                    delete_missing_rows=db_delete_missing,
                )

        if result_path is not None:
            write_jsonl(result_path, results)
            LOGGER.info("Wrote %s daily rollup rows to %s", len(results), result_path)

        records_out = len(results)
        success = True
        return results
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        finished_at_utc = utc_now_iso()
        execution_meta = build_execution_meta(
            job_name="gold_to_agg_ccu_daily",
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            success=success,
            http_status=http_status,
            retry_count=retry_count,
            timeout_count=timeout_count,
            rate_limit_count=rate_limit_count,
            records_in=records_in,
            records_out=records_out,
            error_type=error_type,
            error_message=error_message,
        )
        saved_meta_path = save_execution_meta(execution_meta, resolved_meta_path)
        LOGGER.info("Saved daily rollup execution meta to %s", saved_meta_path)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for daily CCU rollup aggregation."""

    parser = argparse.ArgumentParser(description="Aggregate Steam CCU daily rollups")
    parser.add_argument("--result-path", type=Path, default=None)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    run(result_path=args.result_path, meta_path=args.meta_path)


if __name__ == "__main__":
    main()
