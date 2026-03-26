"""Fetch Steam reviews snapshots for tracked games and write bronze JSONL."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    sum_attempt_stats,
    summarize_attempts,
    utc_now_iso,
)
from steam.probe.common import decode_json_payload, request_with_retry

LOGGER = logging.getLogger(__name__)
REQUEST_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{app_id}"
REQUEST_PARAMS = {
    "json": 1,
    "filter": "all",
    "language": "all",
    "purchase_type": "all",
    "num_per_page": 20,
}


def configure_logging() -> None:
    """Use a compact logger format for ingest scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def require_psycopg() -> Any:
    """Import psycopg and fail fast when dependency is missing."""

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for Steam reviews ingest") from exc
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


def load_tracked_steam_games(conn: Any) -> list[dict[str, int]]:
    """Load active tracked games and their Steam app ids."""

    query = """
        SELECT
            tg.canonical_game_id,
            gei.external_id AS steam_appid
        FROM tracked_game AS tg
        INNER JOIN game_external_id AS gei
            ON gei.canonical_game_id = tg.canonical_game_id
           AND gei.source = 'steam'
        WHERE tg.is_active = TRUE
        ORDER BY tg.priority, tg.canonical_game_id
    """

    targets: list[dict[str, int]] = []
    with conn.cursor() as cursor:
        cursor.execute(query)
        for canonical_game_id, steam_appid_raw in cursor.fetchall():
            try:
                steam_appid = int(steam_appid_raw)
            except (TypeError, ValueError):
                LOGGER.warning(
                    "Skipping invalid steam_appid for canonical_game_id=%s: %s",
                    canonical_game_id,
                    steam_appid_raw,
                )
                continue

            targets.append(
                {
                    "canonical_game_id": int(canonical_game_id),
                    "steam_appid": steam_appid,
                }
            )

    return targets


def extract_query_summary(payload: Any) -> dict[str, int] | None:
    """Extract review summary totals from a Steam appreviews payload."""

    if not isinstance(payload, dict):
        return None

    query_summary = payload.get("query_summary")
    if not isinstance(query_summary, dict):
        return None

    parsed: dict[str, int] = {}
    for key in ("total_reviews", "total_positive", "total_negative"):
        value = query_summary.get(key)
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            return None
        if parsed_value < 0:
            return None
        parsed[key] = parsed_value

    return parsed


def fetch_reviews_for_app(
    *,
    steam_appid: int,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
) -> dict[str, Any]:
    """Fetch one app's reviews summary using shared retry defaults only."""

    request_url = REQUEST_URL_TEMPLATE.format(app_id=steam_appid)
    result = request_with_retry(
        url=request_url,
        params=REQUEST_PARAMS,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        jitter_max_seconds=jitter_max_seconds,
        max_backoff_seconds=max_backoff_seconds,
        logger=LOGGER,
    )

    payload = decode_json_payload(result.body)
    summary = extract_query_summary(payload)

    return {
        "status_code": result.status_code,
        "summary": summary,
        "error": result.error,
        "attempts": result.attempts,
        "attempt_stats": summarize_attempts(result.attempts),
    }


def build_bronze_record(
    *,
    canonical_game_id: int,
    steam_appid: int,
    collected_at: str,
    fetch_result: dict[str, Any],
) -> dict[str, Any]:
    """Build one bronze record with explicit UTC collected_at semantics."""

    summary = fetch_result["summary"]

    return {
        "attempts": fetch_result["attempts"],
        "canonical_game_id": canonical_game_id,
        "collected_at": collected_at,
        "error": fetch_result["error"],
        "http_status": fetch_result["status_code"],
        "steam_appid": steam_appid,
        "total_negative": None if summary is None else summary["total_negative"],
        "total_positive": None if summary is None else summary["total_positive"],
        "total_reviews": None if summary is None else summary["total_reviews"],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL file for bronze handoff."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for Steam reviews fetch script."""

    parser = argparse.ArgumentParser(description="Fetch Steam reviews snapshots into bronze JSONL")
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-base-sec", type=float, default=0.5)
    parser.add_argument("--jitter-max-sec", type=float, default=0.3)
    parser.add_argument("--max-backoff-sec", type=float, default=8.0)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def run(
    *,
    output_path: Path,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
    meta_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Fetch reviews for all tracked Steam games and write bronze output."""

    started_at_utc = utc_now_iso()
    resolved_meta_path = meta_path or default_meta_path(
        job_name="fetch_reviews_daily",
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

    try:
        psycopg = require_psycopg()
        conninfo = build_pg_conninfo_from_env()

        with psycopg.connect(conninfo=conninfo) as conn:
            targets = load_tracked_steam_games(conn)

        records_in = len(targets)
        attempt_summaries: list[dict[str, int]] = []
        records: list[dict[str, Any]] = []

        for target in targets:
            collected_at_utc = utc_now_iso()
            result = fetch_reviews_for_app(
                steam_appid=target["steam_appid"],
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                backoff_base_seconds=backoff_base_seconds,
                jitter_max_seconds=jitter_max_seconds,
                max_backoff_seconds=max_backoff_seconds,
            )
            attempt_summaries.append(result["attempt_stats"])
            records.append(
                build_bronze_record(
                    canonical_game_id=target["canonical_game_id"],
                    steam_appid=target["steam_appid"],
                    collected_at=collected_at_utc,
                    fetch_result=result,
                )
            )

        write_jsonl(output_path, records)
        LOGGER.info("Wrote %s bronze rows to %s", len(records), output_path)

        aggregated_attempt_stats = sum_attempt_stats(attempt_summaries)
        retry_count = aggregated_attempt_stats["retry_count"]
        timeout_count = aggregated_attempt_stats["timeout_count"]
        rate_limit_count = aggregated_attempt_stats["rate_limit_count"]
        records_out = len(records)
        success = True
        return records
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        finished_at_utc = utc_now_iso()
        execution_meta = build_execution_meta(
            job_name="fetch_reviews_daily",
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
        LOGGER.info("Saved fetch execution meta to %s", saved_meta_path)


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    run(
        output_path=args.output_path,
        timeout_seconds=args.timeout_sec,
        max_attempts=args.max_attempts,
        backoff_base_seconds=args.backoff_base_sec,
        jitter_max_seconds=args.jitter_max_sec,
        max_backoff_seconds=args.max_backoff_sec,
        meta_path=args.meta_path,
    )


if __name__ == "__main__":
    main()
