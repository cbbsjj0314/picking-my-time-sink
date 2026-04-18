from __future__ import annotations

from typing import Any

import pytest

from steam.normalize.bronze_to_silver_ccu import format_kst_iso, parse_timestamp
from steam.normalize.silver_to_gold_price import normalize_price_region, process_silver_rows


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str, str], dict[str, Any]] = {}

    def upsert(
        self,
        canonical_game_id: int,
        bucket_time,
        region: str,
        currency_code: str | None,
        initial_price_minor: int | None,
        final_price_minor: int | None,
        discount_percent: int | None,
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
    assert first_results[0]["region"] == "KR"
    assert second_results[0]["region"] == "KR"

    first_key = (1, format_kst_iso(parse_timestamp("2026-03-13T06:00:00+09:00")), "KR")
    assert store.rows[first_key]["final_price_minor"] == 4200000
    assert store.rows[first_key]["is_free"] is None


def test_process_silver_rows_upserts_nullable_free_row_idempotently() -> None:
    store = FakeFactStore()
    rows = [
        {
            "bucket_time": "2026-03-13T06:00:00+09:00",
            "canonical_game_id": 1,
            "collected_at": "2026-03-12T21:41:38+00:00",
            "currency_code": None,
            "discount_percent": None,
            "final_price_minor": None,
            "initial_price_minor": None,
            "is_free": True,
            "region": "kr",
        }
    ]

    first_results = process_silver_rows(rows, upsert_row=store.upsert)
    second_results = process_silver_rows(rows, upsert_row=store.upsert)

    key = (1, format_kst_iso(parse_timestamp("2026-03-13T06:00:00+09:00")), "KR")
    assert len(store.rows) == 1
    assert first_results == second_results
    assert store.rows[key]["is_free"] is True
    assert store.rows[key]["currency_code"] is None
    assert store.rows[key]["final_price_minor"] is None


def test_process_silver_rows_rejects_fake_free_zero_price_row() -> None:
    with pytest.raises(ValueError, match="free price rows"):
        process_silver_rows(
            [
                {
                    "bucket_time": "2026-03-13T06:00:00+09:00",
                    "canonical_game_id": 1,
                    "collected_at": "2026-03-12T21:41:38+00:00",
                    "currency_code": "KRW",
                    "discount_percent": 0,
                    "final_price_minor": 0,
                    "initial_price_minor": 0,
                    "is_free": True,
                    "region": "KR",
                }
            ],
            upsert_row=FakeFactStore().upsert,
        )


def test_process_silver_rows_rejects_paid_partial_row() -> None:
    with pytest.raises(ValueError, match="paid price rows require"):
        process_silver_rows(
            [
                {
                    "bucket_time": "2026-03-13T06:00:00+09:00",
                    "canonical_game_id": 1,
                    "collected_at": "2026-03-12T21:41:38+00:00",
                    "currency_code": None,
                    "discount_percent": 0,
                    "final_price_minor": 4200000,
                    "initial_price_minor": 4200000,
                    "is_free": None,
                    "region": "KR",
                }
            ],
            upsert_row=FakeFactStore().upsert,
        )


def test_normalize_price_region_accepts_legacy_lowercase_kr() -> None:
    assert normalize_price_region("kr") == "KR"
    assert normalize_price_region(" KR ") == "KR"
