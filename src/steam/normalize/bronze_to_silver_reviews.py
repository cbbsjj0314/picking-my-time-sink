"""Normalize Steam reviews bronze rows into deduplicated silver rows."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from steam.normalize.bronze_to_silver_ccu import parse_timestamp, to_kst_datetime

LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    """Use a compact logger format for normalization scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def format_utc_iso(value: dt.datetime) -> str:
    """Format an aware datetime in UTC while preserving the same instant."""

    if value.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_review_count(value: Any) -> int | None:
    """Normalize review counts while preserving invalid values as missing."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def compute_positive_ratio(total_positive: int, total_reviews: int) -> float | None:
    """Compute positive ratio for valid positive total review counts only."""

    if total_reviews <= 0:
        return None
    return total_positive / total_reviews


def build_skip_reason(
    *,
    total_reviews: int | None,
    total_positive: int | None,
    total_negative: int | None,
) -> str | None:
    """Return a compact skip reason for invalid review summary rows."""

    if total_reviews is None or total_positive is None or total_negative is None:
        return "missing_review_counts"
    if total_reviews <= 0:
        return "non_positive_total_reviews"
    if total_positive > total_reviews or total_negative > total_reviews:
        return "invalid_review_totals"
    return None


def normalize_bronze_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one bronze row into silver schema with KST snapshot semantics."""

    canonical_game_id = int(row["canonical_game_id"])
    steam_appid = int(row["steam_appid"])
    collected_at = parse_timestamp(str(row["collected_at"]))
    normalized_collected_at = format_utc_iso(collected_at)
    snapshot_date = to_kst_datetime(collected_at).date().isoformat()

    total_reviews = normalize_review_count(row.get("total_reviews"))
    total_positive = normalize_review_count(row.get("total_positive"))
    total_negative = normalize_review_count(row.get("total_negative"))
    skipped_reason = build_skip_reason(
        total_reviews=total_reviews,
        total_positive=total_positive,
        total_negative=total_negative,
    )

    positive_ratio = None
    if skipped_reason is None and total_reviews is not None and total_positive is not None:
        positive_ratio = compute_positive_ratio(total_positive, total_reviews)
        if positive_ratio is None:
            skipped_reason = "non_positive_total_reviews"

    return {
        "canonical_game_id": canonical_game_id,
        "collected_at": normalized_collected_at,
        "positive_ratio": positive_ratio,
        "skipped_reason": skipped_reason,
        "snapshot_date": snapshot_date,
        "steam_appid": steam_appid,
        "total_negative": total_negative,
        "total_positive": total_positive,
        "total_reviews": total_reviews,
    }


def is_preferred_record(candidate: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """Choose the better record for a duplicated (game, snapshot_date) key."""

    candidate_skipped = candidate.get("skipped_reason") is not None
    current_skipped = current.get("skipped_reason") is not None
    if candidate_skipped != current_skipped:
        return not candidate_skipped

    candidate_collected_at = parse_timestamp(str(candidate["collected_at"]))
    current_collected_at = parse_timestamp(str(current["collected_at"]))
    return candidate_collected_at > current_collected_at


def dedupe_silver_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate normalized rows by (canonical_game_id, snapshot_date)."""

    deduped: dict[tuple[int, str], dict[str, Any]] = {}

    for record in records:
        key = (int(record["canonical_game_id"]), str(record["snapshot_date"]))
        current = deduped.get(key)
        if current is None or is_preferred_record(record, current):
            deduped[key] = record

    return sorted(
        deduped.values(),
        key=lambda item: (int(item["canonical_game_id"]), str(item["snapshot_date"])),
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

    parser = argparse.ArgumentParser(
        description="Normalize Steam reviews bronze JSONL to silver JSONL"
    )
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
