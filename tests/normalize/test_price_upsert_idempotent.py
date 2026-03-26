from __future__ import annotations

from typing import Any

from steam.normalize.bronze_to_silver_ccu import format_kst_iso, parse_timestamp
from steam.normalize.silver_to_gold_price import process_silver_rows


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str, str], dict[str, Any]] = {}

    def upsert(
        self,
        canonical_game_id: int,
        bucket_time,
        region: str,
        currency_code: str,
        initial_price_minor: int,
        final_price_minor: int,
        discount_percent: int,
        is_free,
        collected_at,
    ) -> None:
        key = (canonical_game_id, format_kst_iso(bucket_time), region)
        self.rows[key] = {
            "collected_at": collected_at.isoformat(),
            "currency_code": currency_code,
            "discount_percent": discount_percent,
            "final_price_minor": final_price_minor,
            "initial_price_minor": initial_price_minor,
            "is_free": is_free,
        }


def sample_silver_rows() -> list[dict[str, object]]:
    return [
        {
            "bucket_time": "2026-03-13T06:00:00+09:00",
            "canonical_game_id": 1,
            "collected_at": "2026-03-12T21:41:38+00:00",
            "currency_code": "KRW",
            "discount_percent": 0,
            "final_price_minor": 4200000,
            "initial_price_minor": 4200000,
            "is_free": None,
            "region": "kr",
        },
        {
            "bucket_time": "2026-03-13T07:00:00+09:00",
            "canonical_game_id": 1,
            "collected_at": "2026-03-12T22:01:10+00:00",
            "currency_code": "KRW",
            "discount_percent": 0,
            "final_price_minor": 4200000,
            "initial_price_minor": 4200000,
            "is_free": None,
            "region": "kr",
        },
    ]


def test_process_silver_rows_is_idempotent_for_same_input() -> None:
    store = FakeFactStore()
    rows = sample_silver_rows()

    first_results = process_silver_rows(rows, upsert_row=store.upsert)
    second_results = process_silver_rows(rows, upsert_row=store.upsert)

    assert len(store.rows) == 2
    assert first_results[0]["region"] == "kr"
    assert second_results[0]["region"] == "kr"

    first_key = (1, format_kst_iso(parse_timestamp("2026-03-13T06:00:00+09:00")), "kr")
    assert store.rows[first_key]["final_price_minor"] == 4200000
    assert store.rows[first_key]["is_free"] is None
