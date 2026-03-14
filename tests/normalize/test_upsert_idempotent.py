from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from steam.normalize.bronze_to_silver_ccu import format_kst_iso, parse_timestamp
from steam.normalize.silver_to_gold_ccu import previous_day_same_bucket, process_silver_rows


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str], dict[str, Any]] = {}

    def upsert(
        self,
        canonical_game_id: int,
        bucket_time: dt.datetime,
        ccu: int,
        collected_at: dt.datetime,
    ) -> None:
        key = (canonical_game_id, format_kst_iso(bucket_time))
        self.rows[key] = {
            "ccu": ccu,
            "collected_at": format_kst_iso(collected_at),
        }

    def fetch_prev_day_ccu(self, canonical_game_id: int, bucket_time: dt.datetime) -> int | None:
        prev_bucket = previous_day_same_bucket(bucket_time)
        prev_key = (canonical_game_id, format_kst_iso(prev_bucket))
        row = self.rows.get(prev_key)
        if row is None:
            return None
        return int(row["ccu"])


def sample_silver_rows() -> list[Mapping[str, Any]]:
    return [
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-06T12:30:00+09:00",
            "collected_at": "2026-03-06T12:30:20+09:00",
            "ccu": 100,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T12:30:00+09:00",
            "collected_at": "2026-03-07T12:30:25+09:00",
            "ccu": 120,
        },
    ]


def test_process_silver_rows_is_idempotent_for_same_input() -> None:
    store = FakeFactStore()
    rows = sample_silver_rows()

    first_results = process_silver_rows(
        rows,
        upsert_row=store.upsert,
        fetch_prev_day_ccu=store.fetch_prev_day_ccu,
    )
    second_results = process_silver_rows(
        rows,
        upsert_row=store.upsert,
        fetch_prev_day_ccu=store.fetch_prev_day_ccu,
    )

    assert len(store.rows) == 2
    assert first_results[1]["delta_ccu_day"] == 20
    assert second_results[1]["delta_ccu_day"] == 20

    today_key = (1, format_kst_iso(parse_timestamp("2026-03-07T12:30:00+09:00")))
    assert today_key in store.rows
    assert store.rows[today_key]["ccu"] == 120
