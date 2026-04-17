"""Load Steam rankings runtime payloads and upsert the gold fact table."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    utc_now_iso,
)
from steam.normalize.bronze_to_silver_ccu import to_kst_datetime
from steam.probe.probe_rankings import (
    DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    DEFAULT_MOSTPLAYED_KR_PATH,
    DEFAULT_TOPSELLERS_GLOBAL_PATH,
    DEFAULT_TOPSELLERS_KR_PATH,
    parse_rankings_payload,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_RESULT_PATH = Path("tmp/steam/rankings/payload_to_gold_result.jsonl")


@dataclass(frozen=True, slots=True)
class RankingPayloadSource:
    payload_path: Path
    market: str
    rank_type: str


DEFAULT_PAYLOAD_SOURCES: tuple[RankingPayloadSource, ...] = (
    RankingPayloadSource(
        payload_path=DEFAULT_TOPSELLERS_KR_PATH,
        market="kr",
        rank_type="top_selling",
    ),
    RankingPayloadSource(
        payload_path=DEFAULT_TOPSELLERS_GLOBAL_PATH,
        market="global",
        rank_type="top_selling",
    ),
    RankingPayloadSource(
        payload_path=DEFAULT_MOSTPLAYED_KR_PATH,
        market="kr",
        rank_type="top_played",
    ),
    RankingPayloadSource(
        payload_path=DEFAULT_MOSTPLAYED_GLOBAL_PATH,
        market="global",
        rank_type="top_played",
    ),
)

UPSERT_SQL = """
INSERT INTO fact_steam_rank_daily (
    snapshot_date,
    market,
    rank_type,
    rank_position,
    steam_appid,
    canonical_game_id,
    collected_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (snapshot_date, market, rank_type, rank_position)
DO UPDATE SET
    steam_appid = EXCLUDED.steam_appid,
    canonical_game_id = EXCLUDED.canonical_game_id,
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
        raise RuntimeError("psycopg is required for Steam rankings gold upsert") from exc
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


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for rankings payload to gold upsert."""

    parser = argparse.ArgumentParser(
        description="Load Steam rankings runtime payloads into gold fact table"
    )
    parser.add_argument(
        "--topsellers-kr-path",
        type=Path,
        default=DEFAULT_TOPSELLERS_KR_PATH,
    )
    parser.add_argument(
        "--topsellers-global-path",
        type=Path,
        default=DEFAULT_TOPSELLERS_GLOBAL_PATH,
    )
    parser.add_argument(
        "--mostplayed-kr-path",
        type=Path,
        default=DEFAULT_MOSTPLAYED_KR_PATH,
    )
    parser.add_argument(
        "--mostplayed-global-path",
        type=Path,
        default=DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    )
    parser.add_argument("--result-path", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("--meta-path", type=Path, default=None)
    parser.add_argument("--max-rows", type=int, default=100)
    return parser


def read_json_file(path: Path) -> object:
    """Read one payload JSON file with a clear error on failure."""

    if not path.exists():
        raise ValueError(f"Required rankings payload missing: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Required rankings payload unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Required rankings payload JSON decode failed: {path}") from exc


def runtime_artifact_collected_at(path: Path) -> dt.datetime:
    """Use runtime artifact write time as the collected_at anchor."""

    try:
        stat_result = path.stat()
    except OSError as exc:
        raise ValueError(f"Required rankings payload unreadable: {path}") from exc
    return dt.datetime.fromtimestamp(stat_result.st_mtime, tz=dt.UTC)


def load_canonical_mapping_by_steam_appid(conn: Any) -> dict[int, int]:
    """Load resolved Steam app id to canonical game mappings."""

    query = """
        SELECT
            external_id,
            canonical_game_id
        FROM game_external_id
        WHERE source = 'steam'
          AND canonical_game_id IS NOT NULL
    """

    mapping: dict[int, int] = {}
    with conn.cursor() as cursor:
        cursor.execute(query)
        for external_id_raw, canonical_game_id_raw in cursor.fetchall():
            try:
                steam_appid = int(external_id_raw)
                canonical_game_id = int(canonical_game_id_raw)
            except (TypeError, ValueError):
                continue
            mapping[steam_appid] = canonical_game_id
    return mapping


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL output for upsert results."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def upsert_fact_rank_row(
    cursor: Any,
    *,
    snapshot_date: dt.date,
    market: str,
    rank_type: str,
    rank_position: int,
    steam_appid: int,
    canonical_game_id: int | None,
    collected_at: dt.datetime,
) -> None:
    """Upsert one ranking fact row using table grain PK."""

    cursor.execute(
        UPSERT_SQL,
        (
            snapshot_date,
            market,
            rank_type,
            rank_position,
            steam_appid,
            canonical_game_id,
            collected_at,
        ),
    )


def build_result_row(
    *,
    snapshot_date: dt.date,
    market: str,
    rank_type: str,
    rank_position: int,
    steam_appid: int,
    canonical_game_id: int | None,
) -> dict[str, Any]:
    """Build deterministic result row for one rankings gold-load decision."""

    return {
        "canonical_game_id": canonical_game_id,
        "market": market,
        "rank_position": rank_position,
        "rank_type": rank_type,
        "snapshot_date": snapshot_date.isoformat(),
        "steam_appid": steam_appid,
    }


def process_payload_sources(
    payload_sources: tuple[RankingPayloadSource, ...],
    *,
    mapping_by_steam_appid: dict[int, int],
    upsert_row: Callable[[dt.date, str, str, int, int, int | None, dt.datetime], None],
    max_rows: int = 100,
) -> list[dict[str, Any]]:
    """Process rankings payload files with injected storage operations."""

    results: list[dict[str, Any]] = []
    for source in payload_sources:
        payload = read_json_file(source.payload_path)
        rows = parse_rankings_payload(payload, max_rows=max_rows)
        if not rows:
            raise ValueError(
                f"Required rankings payload produced zero rows: "
                f"{source.market}/{source.rank_type} ({source.payload_path})"
            )

        collected_at = runtime_artifact_collected_at(source.payload_path)
        snapshot_date = to_kst_datetime(collected_at).date()

        for row in rows:
            rank_position = int(row["rank"])
            steam_appid = int(row["app_id"])
            canonical_game_id = mapping_by_steam_appid.get(steam_appid)
            upsert_row(
                snapshot_date,
                source.market,
                source.rank_type,
                rank_position,
                steam_appid,
                canonical_game_id,
                collected_at,
            )
            results.append(
                build_result_row(
                    snapshot_date=snapshot_date,
                    market=source.market,
                    rank_type=source.rank_type,
                    rank_position=rank_position,
                    steam_appid=steam_appid,
                    canonical_game_id=canonical_game_id,
                )
            )

    return results


def run(
    *,
    topsellers_kr_path: Path = DEFAULT_TOPSELLERS_KR_PATH,
    topsellers_global_path: Path = DEFAULT_TOPSELLERS_GLOBAL_PATH,
    mostplayed_kr_path: Path = DEFAULT_MOSTPLAYED_KR_PATH,
    mostplayed_global_path: Path = DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    result_path: Path | None = DEFAULT_RESULT_PATH,
    meta_path: Path | None = None,
    max_rows: int = 100,
) -> list[dict[str, Any]]:
    """Upsert rankings runtime payload rows into the gold fact table."""

    started_at_utc = utc_now_iso()
    resolved_meta_path = meta_path or default_meta_path(
        job_name="payload_to_gold_rankings",
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

    payload_sources = (
        RankingPayloadSource(
            payload_path=topsellers_kr_path,
            market="kr",
            rank_type="top_selling",
        ),
        RankingPayloadSource(
            payload_path=topsellers_global_path,
            market="global",
            rank_type="top_selling",
        ),
        RankingPayloadSource(
            payload_path=mostplayed_kr_path,
            market="kr",
            rank_type="top_played",
        ),
        RankingPayloadSource(
            payload_path=mostplayed_global_path,
            market="global",
            rank_type="top_played",
        ),
    )

    results: list[dict[str, Any]] = []
    try:
        psycopg = require_psycopg()
        conninfo = build_pg_conninfo_from_env()

        with psycopg.connect(conninfo=conninfo) as conn:
            mapping_by_steam_appid = load_canonical_mapping_by_steam_appid(conn)
            records_in = len(payload_sources)
            with conn.cursor() as cursor:

                def db_upsert(
                    snapshot_date: dt.date,
                    market: str,
                    rank_type: str,
                    rank_position: int,
                    steam_appid: int,
                    canonical_game_id: int | None,
                    collected_at: dt.datetime,
                ) -> None:
                    upsert_fact_rank_row(
                        cursor,
                        snapshot_date=snapshot_date,
                        market=market,
                        rank_type=rank_type,
                        rank_position=rank_position,
                        steam_appid=steam_appid,
                        canonical_game_id=canonical_game_id,
                        collected_at=collected_at,
                    )

                results = process_payload_sources(
                    payload_sources,
                    mapping_by_steam_appid=mapping_by_steam_appid,
                    upsert_row=db_upsert,
                    max_rows=max_rows,
                )

        if result_path is not None:
            write_jsonl(result_path, results)
            LOGGER.info("Wrote %s rankings gold result rows to %s", len(results), result_path)

        records_out = len(results)
        success = True
        return results
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        execution_meta = build_execution_meta(
            job_name="payload_to_gold_rankings",
            started_at_utc=started_at_utc,
            finished_at_utc=utc_now_iso(),
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
        save_execution_meta(execution_meta, resolved_meta_path)


def main() -> None:
    """CLI entrypoint for rankings payload to gold upsert."""

    configure_logging()
    args = build_parser().parse_args()
    run(
        topsellers_kr_path=args.topsellers_kr_path,
        topsellers_global_path=args.topsellers_global_path,
        mostplayed_kr_path=args.mostplayed_kr_path,
        mostplayed_global_path=args.mostplayed_global_path,
        result_path=args.result_path,
        meta_path=args.meta_path,
        max_rows=args.max_rows,
    )


if __name__ == "__main__":
    main()
