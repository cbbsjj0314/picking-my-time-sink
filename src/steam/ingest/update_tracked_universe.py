"""Update tracked Steam targets from required rankings seeds; catalog summary is optional."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steam.ingest.app_catalog_latest_summary import (
    DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH,
    extract_catalog_metadata,
)
from steam.probe.probe_rankings import (
    DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    DEFAULT_MOSTPLAYED_KR_PATH,
    DEFAULT_TOPSELLERS_GLOBAL_PATH,
    DEFAULT_TOPSELLERS_KR_PATH,
    parse_rankings_payload,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_RESULT_PATH = Path("tmp/steam/tracked_universe/update_result.jsonl")
DEFAULT_APP_CATALOG_PATH = DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH


@dataclass(frozen=True, slots=True)
class SeedSource:
    payload_path: Path
    source_label: str
    market: str
    rank_type: str
    default_priority: int


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    steam_appid: int
    title: str
    source_label: str
    market: str
    rank_type: str
    default_priority: int


@dataclass(frozen=True, slots=True)
class MergedCandidate:
    steam_appid: int
    selected_title: str
    selected_source_label: str
    market: str
    rank_type: str
    priority: int
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MappingSnapshot:
    steam_appid: int
    canonical_game_id: int | None
    canonical_name: str | None
    tracked_exists: bool


class MappingAttachConflict(RuntimeError):
    """Raised when attaching a mapping loses a race or hits unique constraints."""


DEFAULT_SEED_SOURCES: tuple[SeedSource, ...] = (
    SeedSource(
        payload_path=DEFAULT_TOPSELLERS_KR_PATH,
        source_label="steam_rank_topsellers_kr",
        market="kr",
        rank_type="top_selling",
        default_priority=1,
    ),
    SeedSource(
        payload_path=DEFAULT_TOPSELLERS_GLOBAL_PATH,
        source_label="steam_rank_topsellers_global",
        market="global",
        rank_type="top_selling",
        default_priority=2,
    ),
    SeedSource(
        payload_path=DEFAULT_MOSTPLAYED_KR_PATH,
        source_label="steam_rank_mostplayed_kr",
        market="kr",
        rank_type="top_played",
        default_priority=3,
    ),
    SeedSource(
        payload_path=DEFAULT_MOSTPLAYED_GLOBAL_PATH,
        source_label="steam_rank_mostplayed_global",
        market="global",
        rank_type="top_played",
        default_priority=4,
    ),
)


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
        raise RuntimeError("psycopg is required for tracked universe updates") from exc
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


def utc_now() -> dt.datetime:
    """Return a timezone-aware UTC timestamp truncated to seconds."""

    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def format_utc_iso(value: dt.datetime) -> str:
    """Serialize a UTC timestamp in a stable ISO format."""

    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_seed_sources(
    *,
    topsellers_kr_path: Path,
    topsellers_global_path: Path,
    mostplayed_kr_path: Path,
    mostplayed_global_path: Path,
) -> tuple[SeedSource, ...]:
    """Return default seed sources with any CLI path overrides applied."""

    return (
        SeedSource(
            payload_path=topsellers_kr_path,
            source_label="steam_rank_topsellers_kr",
            market="kr",
            rank_type="top_selling",
            default_priority=1,
        ),
        SeedSource(
            payload_path=topsellers_global_path,
            source_label="steam_rank_topsellers_global",
            market="global",
            rank_type="top_selling",
            default_priority=2,
        ),
        SeedSource(
            payload_path=mostplayed_kr_path,
            source_label="steam_rank_mostplayed_kr",
            market="kr",
            rank_type="top_played",
            default_priority=3,
        ),
        SeedSource(
            payload_path=mostplayed_global_path,
            source_label="steam_rank_mostplayed_global",
            market="global",
            rank_type="top_played",
            default_priority=4,
        ),
    )


def _normalize_steam_appid(value: object) -> int:
    return int(value)


def _normalize_title(value: object) -> str:
    return str(value).strip() if value is not None else ""


def read_json_file(path: Path) -> object:
    """Read one ranking payload JSON file with a clear error on failure."""

    if not path.exists():
        raise ValueError(f"Required rankings payload missing: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Required rankings payload unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Required rankings payload JSON decode failed: {path}") from exc


def load_required_rankings_observations(
    seed_sources: tuple[SeedSource, ...],
) -> list[CandidateObservation]:
    """Load and validate the required rankings payload artifacts."""

    observations: list[CandidateObservation] = []
    for source in seed_sources:
        payload = read_json_file(source.payload_path)
        rows = parse_rankings_payload(payload)
        if not rows:
            raise ValueError(
                f"Required rankings payload produced zero candidates: "
                f"{source.source_label} ({source.payload_path})"
            )

        for row in rows:
            observations.append(
                CandidateObservation(
                    steam_appid=_normalize_steam_appid(row["app_id"]),
                    title=_normalize_title(row["title"]),
                    source_label=source.source_label,
                    market=source.market,
                    rank_type=source.rank_type,
                    default_priority=source.default_priority,
                )
            )

    return observations


def merge_candidate_observations(observations: list[CandidateObservation]) -> list[MergedCandidate]:
    """Merge candidate observations by normalized steam appid."""

    grouped: dict[int, list[CandidateObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.steam_appid, []).append(observation)

    merged: list[MergedCandidate] = []
    for steam_appid in sorted(grouped):
        group = grouped[steam_appid]
        selected = min(group, key=lambda item: (item.default_priority, item.source_label))
        sources = tuple(sorted({item.source_label for item in group}))
        merged.append(
            MergedCandidate(
                steam_appid=steam_appid,
                selected_title=selected.title,
                selected_source_label=selected.source_label,
                market=selected.market,
                rank_type=selected.rank_type,
                priority=selected.default_priority,
                sources=sources,
            )
        )

    return sorted(merged, key=lambda item: (item.priority, item.steam_appid))


def load_optional_catalog_metadata(path: Path | None) -> dict[str, Any]:
    """Load optional App Catalog metadata without blocking the run."""

    if path is None:
        return {
            "app_count": None,
            "pagination": {},
            "snapshot_path": None,
            "top_level_keys": [],
        }

    try:
        return extract_catalog_metadata(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        LOGGER.warning("Optional App Catalog summary missing: %s", path)
    except OSError:
        LOGGER.warning("Optional App Catalog summary unreadable: %s", path)
    except (ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning("Optional App Catalog summary ignored for %s: %s", path, exc)

    return {
        "app_count": None,
        "pagination": {},
        "snapshot_path": None,
        "top_level_keys": [],
    }


def load_catalog_snapshot_appids(path: Path) -> frozenset[int]:
    """Load Steam appids from a completed App Catalog JSONL snapshot."""

    appids: set[int] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue

            try:
                row = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid App Catalog JSON at line {line_number} in {path}"
                ) from exc

            if not isinstance(row, dict):
                raise ValueError(f"Invalid App Catalog row at line {line_number} in {path}")

            try:
                steam_appid = int(row["appid"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid App Catalog appid at line {line_number} in {path}"
                ) from exc

            if steam_appid <= 0:
                raise ValueError(f"Invalid App Catalog appid at line {line_number} in {path}")

            appids.add(steam_appid)

    return frozenset(appids)


def resolve_optional_catalog_active_appids(
    *,
    catalog_metadata: dict[str, Any],
) -> frozenset[int] | None:
    """Return a completed App Catalog appid set when the optional handoff is usable."""

    pagination = catalog_metadata.get("pagination", {})
    if pagination.get("have_more_results") is True:
        LOGGER.info(
            "Skipping catalog-driven tracked filter because latest summary is paginated"
        )
        return None

    snapshot_path_value = catalog_metadata.get("snapshot_path")
    if not isinstance(snapshot_path_value, str) or not snapshot_path_value.strip():
        return None

    snapshot_path = Path(snapshot_path_value)
    try:
        appids = load_catalog_snapshot_appids(snapshot_path)
    except FileNotFoundError:
        LOGGER.warning("Optional App Catalog snapshot missing: %s", snapshot_path)
        return None
    except OSError:
        LOGGER.warning("Optional App Catalog snapshot unreadable: %s", snapshot_path)
        return None
    except ValueError as exc:
        LOGGER.warning("Optional App Catalog snapshot ignored for %s: %s", snapshot_path, exc)
        return None

    if not appids:
        LOGGER.warning("Optional App Catalog snapshot empty: %s", snapshot_path)
        return None

    return appids


def resolve_candidate_is_active(
    candidate: MergedCandidate,
    *,
    catalog_active_appids: frozenset[int] | None,
) -> bool:
    """Return tracked active state for one candidate under the thin catalog rule."""

    if catalog_active_appids is None:
        return True
    return candidate.steam_appid in catalog_active_appids


def validate_candidate(candidate: MergedCandidate, *, has_resolved_mapping: bool) -> str | None:
    """Return a skip reason when a candidate is unusable for this MVP."""

    if candidate.steam_appid <= 0:
        return "invalid_steam_appid"

    if not has_resolved_mapping and not candidate.selected_title.strip():
        return "missing_title_for_new_dim_game"

    return None


def build_result_row(
    *,
    candidate: MergedCandidate,
    run_seen_at_iso: str,
    tracked_action: str,
    skip_reason: str | None,
    canonical_game_id: int | None,
    canonical_name: str | None,
    is_active: bool | None,
    created_dim_game: bool | None,
    attached_mapping: bool | None,
) -> dict[str, Any]:
    """Build one deterministic result row for tracked universe updates."""

    return {
        "attached_mapping": attached_mapping,
        "canonical_game_id": canonical_game_id,
        "canonical_name": canonical_name,
        "created_dim_game": created_dim_game,
        "is_active": is_active,
        "market": candidate.market,
        "priority": candidate.priority,
        "rank_type": candidate.rank_type,
        "run_seen_at": run_seen_at_iso,
        "selected_source_label": candidate.selected_source_label,
        "skip_reason": skip_reason,
        "sources": list(candidate.sources),
        "steam_appid": candidate.steam_appid,
        "tracked_action": tracked_action,
    }


def process_candidate(
    candidate: MergedCandidate,
    *,
    run_seen_at: dt.datetime,
    is_active: bool,
    fetch_mapping: Any,
    insert_mapping_placeholder: Any,
    update_mapping_last_seen: Any,
    insert_dim_game: Any,
    attach_mapping: Any,
    upsert_tracked_game: Any,
) -> dict[str, Any]:
    """Apply one merged candidate using injected storage operations."""

    run_seen_at_iso = format_utc_iso(run_seen_at)
    mapping = fetch_mapping(candidate.steam_appid, for_update=False)
    if mapping is not None and mapping.canonical_game_id is not None:
        locked_mapping = fetch_mapping(candidate.steam_appid, for_update=True)
        if locked_mapping is None or locked_mapping.canonical_game_id is None:
            raise RuntimeError(
                f"Resolved mapping disappeared for steam_appid={candidate.steam_appid}"
            )

        update_mapping_last_seen(candidate.steam_appid, run_seen_at)
        upsert_tracked_game(
            locked_mapping.canonical_game_id,
            is_active,
            candidate.priority,
            list(candidate.sources),
            run_seen_at,
        )
        return build_result_row(
            candidate=candidate,
            run_seen_at_iso=run_seen_at_iso,
            tracked_action="updated" if locked_mapping.tracked_exists else "inserted",
            skip_reason=None,
            canonical_game_id=locked_mapping.canonical_game_id,
            canonical_name=locked_mapping.canonical_name,
            is_active=is_active,
            created_dim_game=False,
            attached_mapping=False,
        )

    skip_reason = validate_candidate(candidate, has_resolved_mapping=False)
    if skip_reason is not None:
        return build_result_row(
            candidate=candidate,
            run_seen_at_iso=run_seen_at_iso,
            tracked_action="skipped",
            skip_reason=skip_reason,
            canonical_game_id=None,
            canonical_name=None,
            is_active=None,
            created_dim_game=None,
            attached_mapping=None,
        )

    insert_mapping_placeholder(candidate.steam_appid, run_seen_at)
    locked_mapping = fetch_mapping(candidate.steam_appid, for_update=True)
    if locked_mapping is None:
        raise RuntimeError(f"Mapping placeholder missing for steam_appid={candidate.steam_appid}")

    if locked_mapping.canonical_game_id is not None:
        update_mapping_last_seen(candidate.steam_appid, run_seen_at)
        upsert_tracked_game(
            locked_mapping.canonical_game_id,
            is_active,
            candidate.priority,
            list(candidate.sources),
            run_seen_at,
        )
        return build_result_row(
            candidate=candidate,
            run_seen_at_iso=run_seen_at_iso,
            tracked_action="updated" if locked_mapping.tracked_exists else "inserted",
            skip_reason=None,
            canonical_game_id=locked_mapping.canonical_game_id,
            canonical_name=locked_mapping.canonical_name,
            is_active=is_active,
            created_dim_game=False,
            attached_mapping=False,
        )

    canonical_game_id = insert_dim_game(candidate.selected_title)
    attached_mapping = False
    try:
        attach_mapping(candidate.steam_appid, canonical_game_id, run_seen_at)
        attached_mapping = True
    except MappingAttachConflict:
        pass

    locked_mapping = fetch_mapping(candidate.steam_appid, for_update=True)
    if locked_mapping is None or locked_mapping.canonical_game_id is None:
        raise RuntimeError(
            f"Unexpected unresolved mapping after attach for steam_appid={candidate.steam_appid}"
        )

    if not attached_mapping:
        update_mapping_last_seen(candidate.steam_appid, run_seen_at)

    upsert_tracked_game(
        locked_mapping.canonical_game_id,
        is_active,
        candidate.priority,
        list(candidate.sources),
        run_seen_at,
    )
    return build_result_row(
        candidate=candidate,
        run_seen_at_iso=run_seen_at_iso,
        tracked_action="updated" if locked_mapping.tracked_exists else "inserted",
        skip_reason=None,
        canonical_game_id=locked_mapping.canonical_game_id,
        canonical_name=locked_mapping.canonical_name,
        is_active=is_active,
        created_dim_game=True,
        attached_mapping=attached_mapping,
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL output for tracked universe results."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


FETCH_MAPPING_SQL = """
SELECT
    gei.external_id,
    gei.canonical_game_id,
    dg.canonical_name,
    EXISTS (
        SELECT 1
        FROM tracked_game AS tg
        WHERE tg.canonical_game_id = gei.canonical_game_id
    ) AS tracked_exists
FROM game_external_id AS gei
LEFT JOIN dim_game AS dg
    ON dg.canonical_game_id = gei.canonical_game_id
WHERE gei.source = 'steam'
  AND gei.external_id = %s
"""


def _fetch_mapping_row(
    cursor: Any,
    steam_appid: int,
    *,
    for_update: bool,
) -> MappingSnapshot | None:
    query = FETCH_MAPPING_SQL + (" FOR UPDATE OF gei" if for_update else "")
    cursor.execute(query, (str(steam_appid),))
    row = cursor.fetchone()
    if row is None:
        return None

    return MappingSnapshot(
        steam_appid=steam_appid,
        canonical_game_id=int(row[1]) if row[1] is not None else None,
        canonical_name=str(row[2]) if row[2] is not None else None,
        tracked_exists=bool(row[3]),
    )


def _insert_mapping_placeholder(cursor: Any, steam_appid: int, run_seen_at: dt.datetime) -> None:
    cursor.execute(
        """
        INSERT INTO game_external_id (
            source,
            external_id,
            canonical_game_id,
            first_seen_at,
            last_seen_at
        )
        VALUES ('steam', %s, NULL, %s, %s)
        ON CONFLICT (source, external_id) DO NOTHING
        """,
        (str(steam_appid), run_seen_at, run_seen_at),
    )


def _update_mapping_last_seen(cursor: Any, steam_appid: int, run_seen_at: dt.datetime) -> None:
    cursor.execute(
        """
        UPDATE game_external_id
        SET last_seen_at = %s
        WHERE source = 'steam'
          AND external_id = %s
        """,
        (run_seen_at, str(steam_appid)),
    )


def _insert_dim_game(cursor: Any, canonical_name: str) -> int:
    cursor.execute(
        "INSERT INTO dim_game (canonical_name) VALUES (%s) RETURNING canonical_game_id",
        (canonical_name,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to insert dim_game row")
    return int(row[0])


def _attach_mapping(
    cursor: Any,
    steam_appid: int,
    canonical_game_id: int,
    run_seen_at: dt.datetime,
) -> None:
    try:
        cursor.execute(
            """
            UPDATE game_external_id
            SET canonical_game_id = %s,
                last_seen_at = %s
            WHERE source = 'steam'
              AND external_id = %s
              AND canonical_game_id IS NULL
            """,
            (canonical_game_id, run_seen_at, str(steam_appid)),
        )
    except Exception as exc:
        unique_violation = getattr(getattr(exc, "sqlstate", None), "value", None)
        if unique_violation is None:
            unique_violation = getattr(exc, "sqlstate", None)
        if unique_violation == "23505":
            raise MappingAttachConflict("mapping attach hit unique constraint") from exc
        raise


def _upsert_tracked_game(
    cursor: Any,
    canonical_game_id: int,
    is_active: bool,
    priority: int,
    sources: list[str],
    run_seen_at: dt.datetime,
) -> None:
    cursor.execute(
        """
        INSERT INTO tracked_game (
            canonical_game_id,
            is_active,
            priority,
            sources,
            first_seen_at,
            last_seen_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (canonical_game_id)
        DO UPDATE SET
            is_active = EXCLUDED.is_active,
            priority = EXCLUDED.priority,
            sources = EXCLUDED.sources, -- MVP: current-run attribution only.
            last_seen_at = EXCLUDED.last_seen_at
        """,
        (canonical_game_id, is_active, priority, sources, run_seen_at, run_seen_at),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for tracked universe updates."""

    parser = argparse.ArgumentParser(
        description="Update tracked Steam universe from rankings seeds"
    )
    parser.add_argument(
        "--topsellers-global-path",
        type=Path,
        default=DEFAULT_SEED_SOURCES[1].payload_path,
    )
    parser.add_argument(
        "--topsellers-kr-path",
        type=Path,
        default=DEFAULT_SEED_SOURCES[0].payload_path,
    )
    parser.add_argument(
        "--mostplayed-global-path",
        type=Path,
        default=DEFAULT_SEED_SOURCES[3].payload_path,
    )
    parser.add_argument(
        "--mostplayed-kr-path",
        type=Path,
        default=DEFAULT_SEED_SOURCES[2].payload_path,
    )
    parser.add_argument("--app-catalog-path", type=Path, default=DEFAULT_APP_CATALOG_PATH)
    parser.add_argument("--result-path", type=Path, default=DEFAULT_RESULT_PATH)
    return parser


def run(
    *,
    topsellers_global_path: Path,
    topsellers_kr_path: Path,
    mostplayed_global_path: Path,
    mostplayed_kr_path: Path,
    app_catalog_path: Path | None,
    result_path: Path,
) -> list[dict[str, Any]]:
    """Run the tracked universe updater against required rankings seeds."""

    seed_sources = resolve_seed_sources(
        topsellers_kr_path=topsellers_kr_path,
        topsellers_global_path=topsellers_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
        mostplayed_global_path=mostplayed_global_path,
    )
    observations = load_required_rankings_observations(seed_sources)
    merged_candidates = merge_candidate_observations(observations)
    if not merged_candidates:
        raise ValueError("Merged tracked-universe seed set is empty")

    catalog_metadata = load_optional_catalog_metadata(app_catalog_path)
    if catalog_metadata["app_count"] is not None:
        LOGGER.info(
            "Loaded optional App Catalog metadata: app_count=%s pagination=%s snapshot_path=%s",
            catalog_metadata["app_count"],
            catalog_metadata["pagination"],
            catalog_metadata["snapshot_path"],
        )
    catalog_active_appids = resolve_optional_catalog_active_appids(
        catalog_metadata=catalog_metadata
    )

    psycopg = require_psycopg()
    conninfo = build_pg_conninfo_from_env()
    run_seen_at = utc_now()
    results: list[dict[str, Any]] = []

    with psycopg.connect(conninfo) as conn:
        for candidate in merged_candidates:
            with conn.transaction():
                with conn.cursor() as cursor:
                    is_active = resolve_candidate_is_active(
                        candidate,
                        catalog_active_appids=catalog_active_appids,
                    )
                    result = process_candidate(
                        candidate,
                        run_seen_at=run_seen_at,
                        is_active=is_active,
                        fetch_mapping=lambda steam_appid, for_update: _fetch_mapping_row(
                            cursor, steam_appid, for_update=for_update
                        ),
                        insert_mapping_placeholder=lambda steam_appid, seen_at: (
                            _insert_mapping_placeholder(
                                cursor,
                                steam_appid,
                                seen_at,
                            )
                        ),
                        update_mapping_last_seen=lambda steam_appid, seen_at: (
                            _update_mapping_last_seen(
                                cursor,
                                steam_appid,
                                seen_at,
                            )
                        ),
                        insert_dim_game=lambda canonical_name: _insert_dim_game(
                            cursor,
                            canonical_name,
                        ),
                        attach_mapping=lambda steam_appid, canonical_game_id, seen_at: (
                            _attach_mapping(
                                cursor,
                                steam_appid,
                                canonical_game_id,
                                seen_at,
                            )
                        ),
                        upsert_tracked_game=lambda canonical_game_id,
                        is_active,
                        priority,
                        sources,
                        seen_at: (
                            _upsert_tracked_game(
                                cursor,
                                canonical_game_id,
                                is_active,
                                priority,
                                sources,
                                seen_at,
                            )
                        ),
                    )
            results.append(result)

    write_jsonl(result_path, results)
    return results


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    results = run(
        topsellers_global_path=args.topsellers_global_path,
        topsellers_kr_path=args.topsellers_kr_path,
        mostplayed_global_path=args.mostplayed_global_path,
        mostplayed_kr_path=args.mostplayed_kr_path,
        app_catalog_path=args.app_catalog_path,
        result_path=args.result_path,
    )
    LOGGER.info("Wrote %s tracked universe result rows to %s", len(results), args.result_path)


if __name__ == "__main__":
    main()
