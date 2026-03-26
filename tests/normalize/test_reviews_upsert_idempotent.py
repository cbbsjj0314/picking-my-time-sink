from __future__ import annotations

from typing import Any

from steam.normalize.silver_to_gold_reviews import process_silver_rows


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str], dict[str, Any]] = {}

    def upsert(
        self,
        canonical_game_id: int,
        snapshot_date,
        total_reviews: int,
        total_positive: int,
        total_negative: int,
        positive_ratio: float,
        collected_at,
    ) -> None:
        key = (canonical_game_id, snapshot_date.isoformat())
        self.rows[key] = {
            "collected_at": collected_at.isoformat().replace("+00:00", "Z"),
            "positive_ratio": positive_ratio,
            "total_negative": total_negative,
            "total_positive": total_positive,
            "total_reviews": total_reviews,
        }


def sample_silver_rows() -> list[dict[str, object]]:
    return [
        {
            "canonical_game_id": 1,
            "snapshot_date": "2026-03-06",
            "collected_at": "2026-03-05T18:20:00Z",
            "total_reviews": 100,
            "total_positive": 80,
            "total_negative": 20,
            "positive_ratio": 0.8,
            "skipped_reason": None,
        },
        {
            "canonical_game_id": 1,
            "snapshot_date": "2026-03-07",
            "collected_at": "2026-03-06T18:20:00Z",
            "total_reviews": 120,
            "total_positive": 96,
            "total_negative": 24,
            "positive_ratio": 0.8,
            "skipped_reason": None,
        },
    ]


def test_process_silver_rows_is_idempotent_for_same_input() -> None:
    store = FakeFactStore()
    rows = sample_silver_rows()

    first_results = process_silver_rows(rows, upsert_row=store.upsert)
    second_results = process_silver_rows(rows, upsert_row=store.upsert)

    assert len(store.rows) == 2
    assert first_results[1]["skipped"] is False
    assert second_results[1]["skipped"] is False
    assert store.rows[(1, "2026-03-07")]["total_reviews"] == 120
    assert store.rows[(1, "2026-03-07")]["positive_ratio"] == 0.8


def test_process_silver_rows_skips_rows_with_skip_reason() -> None:
    store = FakeFactStore()

    results = process_silver_rows(
        [
            {
                "canonical_game_id": 1,
                "snapshot_date": "2026-03-07",
                "collected_at": "2026-03-06T18:20:00Z",
                "total_reviews": 0,
                "total_positive": 0,
                "total_negative": 0,
                "positive_ratio": None,
                "skipped_reason": "non_positive_total_reviews",
            }
        ],
        upsert_row=store.upsert,
    )

    assert store.rows == {}
    assert results[0]["skipped"] is True
    assert results[0]["skipped_reason"] == "non_positive_total_reviews"
