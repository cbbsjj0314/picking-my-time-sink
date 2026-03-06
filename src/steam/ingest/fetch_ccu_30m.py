"""Fetch Steam CCU snapshots for tracked games and write bronze JSONL."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Any

from steam.normalize.bronze_to_silver_ccu import floor_to_kst_half_hour, format_kst_iso
from steam.probe.common import decode_json_payload, request_with_retry

LOGGER = logging.getLogger(__name__)
CCU_ENDPOINT = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"


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
        raise RuntimeError("psycopg is required for Steam CCU ingest") from exc
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


def extract_player_count(payload: Any) -> int | None:
    """Extract player_count from Steam API payload."""

    if not isinstance(payload, dict):
        return None

    response = payload.get("response")
    if not isinstance(response, dict):
        return None

    value = response.get("player_count")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed >= 0 else None


def fetch_ccu_for_app(
    *,
    steam_appid: int,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
) -> dict[str, Any]:
    """Fetch one app's CCU and return status + parsed payload."""

    params: dict[str, str | int] = {"appid": steam_appid}
    steam_api_key = os.getenv("STEAM_API_KEY")
    if steam_api_key:
        params["key"] = steam_api_key

    result = request_with_retry(
        url=CCU_ENDPOINT,
        params=params,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        jitter_max_seconds=jitter_max_seconds,
        max_backoff_seconds=max_backoff_seconds,
        logger=LOGGER,
    )

    payload = decode_json_payload(result.body)
    ccu = extract_player_count(payload)

    missing_reason: str | None = None
    if ccu is None:
        if result.error:
            missing_reason = f"request_error:{result.error.get('type', 'unknown')}"
        elif result.status_code is None:
            missing_reason = "missing_status_code"
        elif result.status_code >= 400:
            missing_reason = f"http_{result.status_code}"
        else:
            missing_reason = "missing_player_count"

    return {
        "status_code": result.status_code,
        "ccu": ccu,
        "missing_reason": missing_reason,
        "attempts": result.attempts,
    }


def build_bronze_record(
    *,
    canonical_game_id: int,
    steam_appid: int,
    collected_at: dt.datetime,
    fetch_result: dict[str, Any],
) -> dict[str, Any]:
    """Build one bronze record using KST bucket semantics."""

    bucket_time = floor_to_kst_half_hour(collected_at)

    return {
        "canonical_game_id": canonical_game_id,
        "steam_appid": steam_appid,
        "collected_at": format_kst_iso(collected_at),
        "bucket_time": format_kst_iso(bucket_time),
        "http_status": fetch_result["status_code"],
        "ccu": fetch_result["ccu"],
        "missing_reason": fetch_result["missing_reason"],
        "attempts": fetch_result["attempts"],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL file for bronze handoff."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for Steam CCU fetch script."""

    parser = argparse.ArgumentParser(description="Fetch Steam CCU snapshots into bronze JSONL")
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-base-sec", type=float, default=0.5)
    parser.add_argument("--jitter-max-sec", type=float, default=0.3)
    parser.add_argument("--max-backoff-sec", type=float, default=8.0)
    return parser


def run(
    *,
    output_path: Path,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
) -> list[dict[str, Any]]:
    """Fetch CCU for all tracked Steam games and write bronze output."""

    psycopg = require_psycopg()
    conninfo = build_pg_conninfo_from_env()

    with psycopg.connect(conninfo=conninfo) as conn:
        targets = load_tracked_steam_games(conn)

    records: list[dict[str, Any]] = []
    for target in targets:
        collected_at = dt.datetime.now(dt.UTC)
        result = fetch_ccu_for_app(
            steam_appid=target["steam_appid"],
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            backoff_base_seconds=backoff_base_seconds,
            jitter_max_seconds=jitter_max_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )

        records.append(
            build_bronze_record(
                canonical_game_id=target["canonical_game_id"],
                steam_appid=target["steam_appid"],
                collected_at=collected_at,
                fetch_result=result,
            )
        )

    write_jsonl(output_path, records)
    LOGGER.info("Wrote %s bronze rows to %s", len(records), output_path)
    return records


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
    )


if __name__ == "__main__":
    main()
