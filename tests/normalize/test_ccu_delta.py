from __future__ import annotations

from steam.normalize.bronze_to_silver_ccu import (
    floor_to_kst_half_hour,
    format_kst_iso,
    parse_timestamp,
)
from steam.normalize.silver_to_gold_ccu import compute_delta_ccu, previous_day_same_bucket


def test_compute_delta_ccu_normal_case() -> None:
    assert compute_delta_ccu(120, 100) == 20


def test_compute_delta_ccu_missing_case() -> None:
    assert compute_delta_ccu(120, None) is None
    assert compute_delta_ccu(None, 100) is None


def test_previous_day_same_bucket_case() -> None:
    current_bucket = parse_timestamp("2026-03-07T12:30:00+09:00")
    prev_bucket = previous_day_same_bucket(current_bucket)

    assert format_kst_iso(prev_bucket) == "2026-03-06T12:30:00+09:00"


def test_floor_to_kst_half_hour_keeps_kst_semantics() -> None:
    kst_source = parse_timestamp("2026-03-07T12:07:45+09:00")
    utc_source = parse_timestamp("2026-03-07T03:44:10+00:00")

    assert format_kst_iso(floor_to_kst_half_hour(kst_source)) == "2026-03-07T12:00:00+09:00"
    assert format_kst_iso(floor_to_kst_half_hour(utc_source)) == "2026-03-07T12:30:00+09:00"
