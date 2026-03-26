from __future__ import annotations

from steam.normalize.bronze_to_silver_ccu import parse_timestamp
from steam.normalize.bronze_to_silver_reviews import normalize_bronze_record


def make_bronze_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "canonical_game_id": 1,
        "steam_appid": 730,
        "collected_at": "2026-03-06T21:46:06Z",
        "total_reviews": 100,
        "total_positive": 80,
        "total_negative": 20,
    }
    row.update(overrides)
    return row


def test_normalize_bronze_record_maps_query_summary_fields() -> None:
    normalized = normalize_bronze_record(make_bronze_row())

    assert normalized["snapshot_date"] == "2026-03-07"
    assert normalized["total_reviews"] == 100
    assert normalized["total_positive"] == 80
    assert normalized["total_negative"] == 20
    assert normalized["positive_ratio"] == 0.8
    assert normalized["skipped_reason"] is None


def test_normalize_bronze_record_derives_snapshot_date_from_kst_boundary() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(collected_at="2026-03-06T15:30:00Z")
    )

    assert normalized["snapshot_date"] == "2026-03-07"


def test_normalize_bronze_record_preserves_collected_at_same_instant() -> None:
    bronze = make_bronze_row(collected_at="2026-03-06T21:46:06Z")

    normalized = normalize_bronze_record(bronze)

    normalized_collected_at = parse_timestamp(str(normalized["collected_at"]))
    bronze_collected_at = parse_timestamp(str(bronze["collected_at"]))

    assert normalized_collected_at == bronze_collected_at


def test_normalize_bronze_record_zero_total_marks_row_skipped() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(
            total_reviews=0,
            total_positive=0,
            total_negative=0,
        )
    )

    assert normalized["positive_ratio"] is None
    assert normalized["skipped_reason"] == "non_positive_total_reviews"
