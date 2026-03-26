"""Load Steam price silver rows and upsert into the gold fact table."""

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
from steam.normalize.bronze_to_silver_ccu import format_kst_iso, parse_timestamp

LOGGER = logging.getLogger(__name__)


UPSERT_SQL = """
INSERT INTO fact_steam_price_1h (
    canonical_game_id,
    bucket_time,
    region,
    currency_code,
    initial_price_minor,
    final_price_minor,
    discount_percent,
    is_free,
    collected_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (canonical_game_id, bucket_time, region)
DO UPDATE SET
    currency_code = EXCLUDED.currency_code,
    initial_price_minor = EXCLUDED.initial_price_minor,
    final_price_minor = EXCLUDED.final_price_minor,
    discount_percent = EXCLUDED.discount_percent,
    is_free = EXCLUDED.is_free,
    collected_at = EXCLUDED.collected_at,
    ingested_at = NOW()
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
        raise RuntimeError("psycopg is required for Steam price gold upsert") from exc
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows from a file."""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                row = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number} in {path}") from exc
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL output for upsert results."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def upsert_fact_price_row(
    cursor: Any,
    *,
    canonical_game_id: int,
    bucket_time: dt.datetime,
    region: str,
    currency_code: str,
    initial_price_minor: int,
    final_price_minor: int,
    discount_percent: int,
    is_free: bool | None,
    collected_at: dt.datetime,
) -> None:
    """Upsert one gold fact row using table grain PK."""

    cursor.execute(
        UPSERT_SQL,
        (
            canonical_game_id,
            bucket_time,
            region,
            currency_code,
            initial_price_minor,
            final_price_minor,
            discount_percent,
            is_free,
            collected_at,
        ),
    )


def build_result_row(
    *,
    canonical_game_id: int,
    bucket_time: dt.datetime,
    region: str,
    currency_code: str,
    final_price_minor: int,
    discount_percent: int,
    is_free: bool | None,
) -> dict[str, Any]:
    """Build deterministic result row for one price gold-load decision."""

    return {
        "bucket_time": format_kst_iso(bucket_time),
        "canonical_game_id": canonical_game_id,
        "currency_code": currency_code,
        "discount_percent": discount_percent,
        "final_price_minor": final_price_minor,
        "is_free": is_free,
        "region": region,
    }


def process_silver_rows(
    silver_rows: list[Mapping[str, Any]],
    *,
    upsert_row: Callable[
        [int, dt.datetime, str, str, int, int, int, bool | None, dt.datetime],
        None,
    ],
) -> list[dict[str, Any]]:
    """Process normalized silver rows with injected storage operations."""

    results: list[dict[str, Any]] = []
    for row in silver_rows:
        canonical_game_id = int(row["canonical_game_id"])
        bucket_time = parse_timestamp(str(row["bucket_time"]))
        region = str(row["region"])
        currency_code = str(row["currency_code"])
        initial_price_minor = int(row["initial_price_minor"])
        final_price_minor = int(row["final_price_minor"])
        discount_percent = int(row["discount_percent"])
        is_free_raw = row.get("is_free")
        if is_free_raw is None:
            is_free = None
        elif isinstance(is_free_raw, bool):
            is_free = is_free_raw
        else:
            raise ValueError("is_free must be boolean or null")
        collected_at = parse_timestamp(str(row["collected_at"]))

        upsert_row(
            canonical_game_id,
            bucket_time,
            region,
            currency_code,
            initial_price_minor,
            final_price_minor,
            discount_percent,
            is_free,
            collected_at,
        )
        results.append(
            build_result_row(
                canonical_game_id=canonical_game_id,
                bucket_time=bucket_time,
                region=region,
                currency_code=currency_code,
                final_price_minor=final_price_minor,
                discount_percent=discount_percent,
                is_free=is_free,
            )
        )

    return results


def run(
    input_path: Path,
    result_path: Path | None = None,
    meta_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Upsert silver rows into the price gold fact table."""

    started_at_utc = utc_now_iso()
    resolved_meta_path = meta_path or default_meta_path(
        job_name="silver_to_gold_price",
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
        silver_rows = load_jsonl(input_path)
        records_in = len(silver_rows)

        psycopg = require_psycopg()
        conninfo = build_pg_conninfo_from_env()

        with psycopg.connect(conninfo=conninfo) as conn:
            with conn.cursor() as cursor:

                def db_upsert(
                    canonical_game_id: int,
                    bucket_time: dt.datetime,
                    region: str,
                    currency_code: str,
                    initial_price_minor: int,
                    final_price_minor: int,
                    discount_percent: int,
                    is_free: bool | None,
                    collected_at: dt.datetime,
                ) -> None:
                    upsert_fact_price_row(
                        cursor,
                        canonical_game_id=canonical_game_id,
                        bucket_time=bucket_time,
                        region=region,
                        currency_code=currency_code,
                        initial_price_minor=initial_price_minor,
                        final_price_minor=final_price_minor,
                        discount_percent=discount_percent,
                        is_free=is_free,
                        collected_at=collected_at,
                    )

                results = process_silver_rows(
                    silver_rows,
                    upsert_row=db_upsert,
                )

        if result_path is not None:
            write_jsonl(result_path, results)
            LOGGER.info("Wrote %s gold result rows to %s", len(results), result_path)

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
            job_name="silver_to_gold_price",
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
        LOGGER.info("Saved silver-to-gold execution meta to %s", saved_meta_path)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for silver-to-gold loading."""

    parser = argparse.ArgumentParser(description="Upsert Steam price silver JSONL into gold fact")
    parser.add_argument("--input-path", type=Path, required=True)
    parser.add_argument("--result-path", type=Path, default=None)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    run(input_path=args.input_path, result_path=args.result_path, meta_path=args.meta_path)


if __name__ == "__main__":
    main()
