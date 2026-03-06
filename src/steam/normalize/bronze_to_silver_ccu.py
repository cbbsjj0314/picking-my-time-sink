"""Normalize Steam CCU bronze rows into deduplicated silver rows."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def configure_logging() -> None:
    """Use a compact logger format for normalization scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_timestamp(value: str) -> dt.datetime:
    """Parse ISO timestamp with explicit timezone."""

    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def to_kst_datetime(value: dt.datetime) -> dt.datetime:
    """Convert a timezone-aware datetime to KST."""

    if value.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return value.astimezone(KST)


def floor_to_kst_half_hour(value: dt.datetime) -> dt.datetime:
    """Floor datetime to KST bucket boundary (HH:00 or HH:30)."""

    kst_value = to_kst_datetime(value)
    minute = 0 if kst_value.minute < 30 else 30
    return kst_value.replace(minute=minute, second=0, microsecond=0)


def format_kst_iso(value: dt.datetime) -> str:
    """Format datetime in KST with explicit timezone offset."""

    return to_kst_datetime(value).isoformat(timespec="seconds")


def normalize_ccu(value: Any) -> int | None:
    """Normalize CCU numeric value while preserving missing as None."""

    if value is None:
        return None

    try:
        ccu = int(value)
    except (TypeError, ValueError):
        return None

    if ccu < 0:
        return None
    return ccu


def normalize_bronze_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one bronze row into silver schema with KST bucket semantics."""

    canonical_game_id = int(row["canonical_game_id"])
    steam_appid = int(row["steam_appid"])

    collected_at = parse_timestamp(str(row["collected_at"]))
    collected_at_kst = to_kst_datetime(collected_at)

    raw_bucket_time = row.get("bucket_time")
    bucket_source = parse_timestamp(str(raw_bucket_time)) if raw_bucket_time else collected_at_kst
    bucket_time = floor_to_kst_half_hour(bucket_source)

    ccu = normalize_ccu(row.get("ccu"))
    missing_reason = row.get("missing_reason")
    if ccu is None and not missing_reason:
        missing_reason = "missing_ccu"

    return {
        "canonical_game_id": canonical_game_id,
        "steam_appid": steam_appid,
        "bucket_time": format_kst_iso(bucket_time),
        "collected_at": format_kst_iso(collected_at_kst),
        "ccu": ccu,
        "missing_reason": missing_reason,
    }


def is_preferred_record(candidate: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """Choose the better record for a duplicated (game, bucket) key."""

    candidate_has_ccu = candidate.get("ccu") is not None
    current_has_ccu = current.get("ccu") is not None

    if candidate_has_ccu != current_has_ccu:
        return candidate_has_ccu

    candidate_collected_at = parse_timestamp(str(candidate["collected_at"]))
    current_collected_at = parse_timestamp(str(current["collected_at"]))
    return candidate_collected_at > current_collected_at


def dedupe_silver_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate normalized rows by (canonical_game_id, bucket_time)."""

    deduped: dict[tuple[int, str], dict[str, Any]] = {}

    for record in records:
        key = (int(record["canonical_game_id"]), str(record["bucket_time"]))
        current = deduped.get(key)
        if current is None or is_preferred_record(record, current):
            deduped[key] = record

    return sorted(
        deduped.values(),
        key=lambda item: (int(item["canonical_game_id"]), str(item["bucket_time"])),
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dictionaries."""

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
    """Write rows as deterministic JSONL for reproducible reruns."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for bronze-to-silver normalization."""

    parser = argparse.ArgumentParser(description="Normalize Steam CCU bronze JSONL to silver JSONL")
    parser.add_argument("--input-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    return parser


def run(input_path: Path, output_path: Path) -> list[dict[str, Any]]:
    """Run bronze-to-silver transformation and write output file."""

    bronze_rows = load_jsonl(input_path)
    normalized_rows = [normalize_bronze_record(row) for row in bronze_rows]
    deduped_rows = dedupe_silver_records(normalized_rows)
    write_jsonl(output_path, deduped_rows)
    LOGGER.info("Wrote %s silver rows to %s", len(deduped_rows), output_path)
    return deduped_rows


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    run(input_path=args.input_path, output_path=args.output_path)


if __name__ == "__main__":
    main()
