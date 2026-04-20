"""Normalize Chzzk live-list payloads into category 30-minute fact rows."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ALLOWED_CATEGORY_TYPES = frozenset({"GAME", "SPORTS", "ETC"})

UPSERT_SQL = """
INSERT INTO fact_chzzk_category_30m (
    chzzk_category_id,
    bucket_time,
    category_type,
    category_name,
    concurrent_sum,
    live_count,
    top_channel_id,
    top_channel_name,
    top_channel_concurrent,
    collected_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (chzzk_category_id, bucket_time)
DO UPDATE SET
    category_type = EXCLUDED.category_type,
    category_name = EXCLUDED.category_name,
    concurrent_sum = EXCLUDED.concurrent_sum,
    live_count = EXCLUDED.live_count,
    top_channel_id = EXCLUDED.top_channel_id,
    top_channel_name = EXCLUDED.top_channel_name,
    top_channel_concurrent = EXCLUDED.top_channel_concurrent,
    collected_at = EXCLUDED.collected_at,
    ingested_at = NOW()
"""


@dataclass(frozen=True, slots=True)
class ChzzkCategoryFactRow:
    """Candidate fact row for one Chzzk category and 30-minute bucket."""

    chzzk_category_id: str
    bucket_time: dt.datetime
    category_type: str
    category_name: str
    concurrent_sum: int
    live_count: int
    top_channel_id: str
    top_channel_name: str
    top_channel_concurrent: int
    collected_at: dt.datetime


@dataclass(slots=True)
class _CategoryAggregate:
    category_type: str
    category_name: str
    concurrent_sum: int
    live_count: int
    top_channel_id: str
    top_channel_name: str
    top_channel_concurrent: int


def parse_timestamp(value: str | dt.datetime) -> dt.datetime:
    """Parse or validate a timezone-aware timestamp."""

    if isinstance(value, dt.datetime):
        parsed = value
    else:
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
    """Floor datetime to the Chzzk 30-minute KST bucket boundary."""

    kst_value = to_kst_datetime(value)
    minute = 0 if kst_value.minute < 30 else 30
    return kst_value.replace(minute=minute, second=0, microsecond=0)


def format_kst_iso(value: dt.datetime) -> str:
    """Format a timestamp in KST for deterministic test output."""

    return to_kst_datetime(value).isoformat(timespec="seconds")


def _required_string(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")

    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _required_non_negative_int(value: object, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc

    if normalized < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def normalize_category_type(value: object) -> str:
    """Normalize the official Chzzk category type enum."""

    category_type = _required_string(value, "categoryType").upper()
    if category_type not in ALLOWED_CATEGORY_TYPES:
        raise ValueError(f"unsupported Chzzk categoryType: {category_type}")
    return category_type


def extract_live_items(payload: object) -> Sequence[Mapping[str, Any]]:
    """Extract live rows from the official Chzzk common response wrapper."""

    if isinstance(payload, list):
        data = payload
    elif isinstance(payload, dict):
        code = payload.get("code")
        if code is not None and code != 200:
            raise ValueError(f"Chzzk live payload is not successful: code={code}")

        content = payload.get("content")
        if isinstance(content, dict) and "data" in content:
            data = content["data"]
        else:
            data = payload.get("data")
    else:
        raise ValueError("Chzzk live payload must be a JSON object or list")

    if not isinstance(data, list):
        raise ValueError("Chzzk live payload must contain a data list")

    live_items: list[Mapping[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, Mapping):
            raise ValueError(f"Chzzk live item at index {index} must be an object")
        live_items.append(item)
    return live_items


def _replace_top_channel(
    aggregate: _CategoryAggregate,
    *,
    channel_id: str,
    channel_name: str,
    concurrent: int,
) -> bool:
    if concurrent > aggregate.top_channel_concurrent:
        return True
    if concurrent == aggregate.top_channel_concurrent:
        return channel_id < aggregate.top_channel_id
    return False


def aggregate_category_lives(
    payload: object,
    *,
    bucket_time: str | dt.datetime,
    collected_at: str | dt.datetime,
) -> list[ChzzkCategoryFactRow]:
    """Aggregate one Chzzk live-list payload into category bucket rows."""

    normalized_bucket_time = floor_to_kst_half_hour(parse_timestamp(bucket_time))
    normalized_collected_at = parse_timestamp(collected_at)
    aggregates: dict[str, _CategoryAggregate] = {}

    for item in extract_live_items(payload):
        category_id = _required_string(item.get("liveCategory"), "liveCategory")
        category_type = normalize_category_type(item.get("categoryType"))
        category_name = _required_string(item.get("liveCategoryValue"), "liveCategoryValue")
        concurrent = _required_non_negative_int(
            item.get("concurrentUserCount"),
            "concurrentUserCount",
        )
        channel_id = _required_string(item.get("channelId"), "channelId")
        channel_name = _required_string(item.get("channelName"), "channelName")

        aggregate = aggregates.get(category_id)
        if aggregate is None:
            aggregates[category_id] = _CategoryAggregate(
                category_type=category_type,
                category_name=category_name,
                concurrent_sum=concurrent,
                live_count=1,
                top_channel_id=channel_id,
                top_channel_name=channel_name,
                top_channel_concurrent=concurrent,
            )
            continue

        if aggregate.category_type != category_type or aggregate.category_name != category_name:
            raise ValueError(f"inconsistent category metadata for {category_id}")

        aggregate.concurrent_sum += concurrent
        aggregate.live_count += 1
        if _replace_top_channel(
            aggregate,
            channel_id=channel_id,
            channel_name=channel_name,
            concurrent=concurrent,
        ):
            aggregate.top_channel_id = channel_id
            aggregate.top_channel_name = channel_name
            aggregate.top_channel_concurrent = concurrent

    return [
        ChzzkCategoryFactRow(
            chzzk_category_id=category_id,
            bucket_time=normalized_bucket_time,
            category_type=aggregate.category_type,
            category_name=aggregate.category_name,
            concurrent_sum=aggregate.concurrent_sum,
            live_count=aggregate.live_count,
            top_channel_id=aggregate.top_channel_id,
            top_channel_name=aggregate.top_channel_name,
            top_channel_concurrent=aggregate.top_channel_concurrent,
            collected_at=normalized_collected_at,
        )
        for category_id, aggregate in sorted(aggregates.items())
    ]


def build_result_row(row: ChzzkCategoryFactRow) -> dict[str, Any]:
    """Build deterministic result output for one Chzzk category fact row."""

    return {
        "bucket_time": format_kst_iso(row.bucket_time),
        "category_name": row.category_name,
        "category_type": row.category_type,
        "chzzk_category_id": row.chzzk_category_id,
        "collected_at": format_kst_iso(row.collected_at),
        "concurrent_sum": row.concurrent_sum,
        "live_count": row.live_count,
        "top_channel_concurrent": row.top_channel_concurrent,
        "top_channel_id": row.top_channel_id,
        "top_channel_name": row.top_channel_name,
    }


def upsert_fact_chzzk_category_row(
    cursor: Any,
    *,
    row: ChzzkCategoryFactRow,
) -> None:
    """Upsert one Chzzk category fact row using the candidate table grain."""

    cursor.execute(
        UPSERT_SQL,
        (
            row.chzzk_category_id,
            row.bucket_time,
            row.category_type,
            row.category_name,
            row.concurrent_sum,
            row.live_count,
            row.top_channel_id,
            row.top_channel_name,
            row.top_channel_concurrent,
            row.collected_at,
        ),
    )


def process_live_payload(
    payload: object,
    *,
    bucket_time: str | dt.datetime,
    collected_at: str | dt.datetime,
    upsert_row: Callable[[ChzzkCategoryFactRow], None],
) -> list[dict[str, Any]]:
    """Aggregate and upsert one live-list payload with injected storage."""

    rows = aggregate_category_lives(
        payload,
        bucket_time=bucket_time,
        collected_at=collected_at,
    )
    for row in rows:
        upsert_row(row)
    return [build_result_row(row) for row in rows]

