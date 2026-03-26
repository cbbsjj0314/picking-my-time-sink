"""Normalize Steam price bronze rows into deduplicated silver rows."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from steam.normalize.bronze_to_silver_ccu import format_kst_iso, parse_timestamp, to_kst_datetime

LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    """Use a compact logger format for normalization scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def format_same_instant_iso(value: dt.datetime) -> str:
    """Format an aware datetime without changing the represented instant."""

    if value.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return value.replace(microsecond=0).isoformat()


def floor_to_kst_hour(value: dt.datetime) -> dt.datetime:
    """Floor a timezone-aware datetime to the KST top-of-hour bucket."""

    kst_value = to_kst_datetime(value)
    return kst_value.replace(minute=0, second=0, microsecond=0)


def normalize_currency_code(value: object) -> str | None:
    """Normalize currency code text while rejecting empty values."""

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_non_negative_int(value: object) -> int | None:
    """Normalize integer fields while rejecting negative values."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def extract_price_fields(payload: Any, *, steam_appid: int) -> dict[str, Any] | None:
    """Extract grounded paid-price fields from the raw appdetails payload."""

    if not isinstance(payload, dict):
        return None

    app_payload = payload.get(str(steam_appid))
    if not isinstance(app_payload, dict):
        return None
    if app_payload.get("success") is not True:
        return None

    data = app_payload.get("data")
    if not isinstance(data, dict):
        return None

    price_overview = data.get("price_overview")
    if not isinstance(price_overview, dict):
        return None

    currency_code = normalize_currency_code(price_overview.get("currency"))
    initial_price_minor = normalize_non_negative_int(price_overview.get("initial"))
    final_price_minor = normalize_non_negative_int(price_overview.get("final"))
    discount_percent = normalize_non_negative_int(price_overview.get("discount_percent"))

    if (
        currency_code is None
        or initial_price_minor is None
        or final_price_minor is None
        or discount_percent is None
        or discount_percent > 100
    ):
        return None

    return {
        "currency_code": currency_code,
        "discount_percent": discount_percent,
        "final_price_minor": final_price_minor,
        "initial_price_minor": initial_price_minor,
    }


def normalize_bronze_record(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalize one bronze row into silver schema for loadable KR paid prices."""

    canonical_game_id = int(row["canonical_game_id"])
    steam_appid = int(row["steam_appid"])
    collected_at = parse_timestamp(str(row["collected_at"]))
    price_fields = extract_price_fields(row.get("payload"), steam_appid=steam_appid)
    if price_fields is None:
        return None

    return {
        "bucket_time": format_kst_iso(floor_to_kst_hour(collected_at)),
        "canonical_game_id": canonical_game_id,
        "collected_at": format_same_instant_iso(collected_at),
        "currency_code": price_fields["currency_code"],
        "discount_percent": price_fields["discount_percent"],
        "final_price_minor": price_fields["final_price_minor"],
        "initial_price_minor": price_fields["initial_price_minor"],
        "is_free": None,
        "region": "kr",
        "steam_appid": steam_appid,
    }


def is_preferred_record(candidate: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """Choose the later collected_at record for duplicated price keys."""

    candidate_collected_at = parse_timestamp(str(candidate["collected_at"]))
    current_collected_at = parse_timestamp(str(current["collected_at"]))
    return candidate_collected_at > current_collected_at


def dedupe_silver_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate normalized rows by (canonical_game_id, bucket_time, region)."""

    deduped: dict[tuple[int, str, str], dict[str, Any]] = {}

    for record in records:
        key = (
            int(record["canonical_game_id"]),
            str(record["bucket_time"]),
            str(record["region"]),
        )
        current = deduped.get(key)
        if current is None or is_preferred_record(record, current):
            deduped[key] = record

    return sorted(
        deduped.values(),
        key=lambda item: (
            int(item["canonical_game_id"]),
            str(item["bucket_time"]),
            str(item["region"]),
        ),
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
        description="Normalize Steam price bronze JSONL to silver JSONL"
    )
    parser.add_argument("--input-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    return parser


def run(input_path: Path, output_path: Path) -> list[dict[str, Any]]:
    """Run bronze-to-silver transformation and write output file."""

    bronze_rows = load_jsonl(input_path)
    normalized_rows: list[dict[str, Any]] = []
    for row in bronze_rows:
        normalized = normalize_bronze_record(row)
        if normalized is not None:
            normalized_rows.append(normalized)

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
