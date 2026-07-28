from __future__ import annotations

from unittest.mock import Mock

import pytest

from steam.normalize.bronze_to_silver_ccu import (
    dedupe_silver_records,
    normalize_bronze_record,
)
from steam.normalize.silver_to_gold_ccu import process_silver_rows


def make_bronze_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "canonical_game_id": 1,
        "steam_appid": 730,
        "collected_at": "2026-03-07T12:05:00+09:00",
    }
    row.update(overrides)
    return row


def make_silver_row(
    *,
    ccu: object,
    collected_at: str,
    marker: str,
) -> dict[str, object]:
    return {
        "canonical_game_id": 1,
        "bucket_time": "2026-03-07T12:00:00+09:00",
        "collected_at": collected_at,
        "ccu": ccu,
        "missing_reason": None if ccu is not None else "missing_ccu",
        "marker": marker,
    }


@pytest.mark.parametrize(
    "ccu_fields",
    [
        pytest.param({}, id="absent"),
        pytest.param({"ccu": "invalid"}, id="non-numeric"),
        pytest.param({"ccu": -1}, id="negative"),
    ],
)
def test_normalize_bronze_record_marks_missing_or_invalid_ccu(
    ccu_fields: dict[str, object],
) -> None:
    normalized = normalize_bronze_record(make_bronze_row(**ccu_fields))

    assert normalized["ccu"] is None
    assert normalized["missing_reason"] == "missing_ccu"


@pytest.mark.parametrize("reverse_order", [False, True])
def test_dedupe_prefers_valid_ccu_over_missing_evidence(reverse_order: bool) -> None:
    missing = make_silver_row(
        ccu=None,
        collected_at="2026-03-07T12:10:00+09:00",
        marker="missing-later",
    )
    valid = make_silver_row(
        ccu=42,
        collected_at="2026-03-07T12:05:00+09:00",
        marker="valid-earlier",
    )
    records = [missing, valid] if reverse_order else [valid, missing]

    deduped = dedupe_silver_records(records)

    assert len(deduped) == 1
    assert deduped[0]["ccu"] == 42
    assert deduped[0]["marker"] == "valid-earlier"


@pytest.mark.parametrize(
    ("earlier_ccu", "later_ccu"),
    [
        pytest.param(10, 20, id="valid"),
        pytest.param(None, None, id="missing"),
    ],
)
def test_dedupe_same_quality_prefers_later_collected_at(
    earlier_ccu: int | None,
    later_ccu: int | None,
) -> None:
    earlier = make_silver_row(
        ccu=earlier_ccu,
        collected_at="2026-03-07T12:05:00+09:00",
        marker="earlier",
    )
    later = make_silver_row(
        ccu=later_ccu,
        collected_at="2026-03-07T12:10:00+09:00",
        marker="later",
    )

    deduped = dedupe_silver_records([later, earlier])

    assert len(deduped) == 1
    assert deduped[0]["marker"] == "later"
    assert deduped[0]["ccu"] == later_ccu


def test_missing_silver_ccu_is_skipped_without_storage_calls() -> None:
    upsert_row = Mock()
    fetch_prev_day_ccu = Mock()

    results = process_silver_rows(
        [
            {
                "canonical_game_id": 1,
                "bucket_time": "2026-03-07T12:00:00+09:00",
                "collected_at": "2026-03-07T12:05:00+09:00",
                "ccu": None,
                "missing_reason": "missing_ccu",
            }
        ],
        upsert_row=upsert_row,
        fetch_prev_day_ccu=fetch_prev_day_ccu,
    )

    assert len(results) == 1
    assert results[0]["ccu"] is None
    assert results[0]["skipped"] is True
    assert results[0]["prev_day_same_bucket_ccu"] is None
    assert results[0]["delta_ccu_day"] is None
    upsert_row.assert_not_called()
    fetch_prev_day_ccu.assert_not_called()
