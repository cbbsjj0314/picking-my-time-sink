from __future__ import annotations

from steam.normalize.bronze_to_silver_ccu import parse_timestamp
from steam.normalize.bronze_to_silver_price import dedupe_silver_records, normalize_bronze_record


def sample_payload() -> dict[str, object]:
    return {
        "252490": {
            "success": True,
            "data": {
                "price_overview": {
                    "currency": "KRW",
                    "discount_percent": 0,
                    "final": 4200000,
                    "initial": 4200000,
                }
            },
        }
    }


def missing_price_payload() -> dict[str, object]:
    return {
        "252490": {
            "success": True,
            "data": {},
        }
    }


def empty_filtered_payload() -> dict[str, object]:
    return {
        "252490": {
            "success": True,
            "data": [],
        }
    }


def fallback_payload(*, is_free: object = True) -> dict[str, object]:
    return {
        "252490": {
            "success": True,
            "data": {
                "is_free": is_free,
            },
        }
    }


def make_bronze_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "canonical_game_id": 1,
        "steam_appid": 252490,
        "collected_at": "2026-03-12T21:41:38Z",
        "payload": sample_payload(),
    }
    row.update(overrides)
    return row


def test_normalize_bronze_record_maps_price_overview_fields() -> None:
    normalized = normalize_bronze_record(make_bronze_row())

    assert normalized == {
        "bucket_time": "2026-03-13T06:00:00+09:00",
        "canonical_game_id": 1,
        "collected_at": "2026-03-12T21:41:38+00:00",
        "currency_code": "KRW",
        "discount_percent": 0,
        "final_price_minor": 4200000,
        "initial_price_minor": 4200000,
        "is_free": None,
        "region": "KR",
        "steam_appid": 252490,
    }


def test_normalize_bronze_record_derives_bucket_time_from_kst_hour_boundary() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(collected_at="2026-03-12T15:00:01Z")
    )

    assert normalized is not None
    assert normalized["bucket_time"] == "2026-03-13T00:00:00+09:00"


def test_normalize_bronze_record_preserves_collected_at_same_instant() -> None:
    bronze = make_bronze_row(collected_at="2026-03-12T21:41:38Z")

    normalized = normalize_bronze_record(bronze)

    assert normalized is not None
    normalized_collected_at = parse_timestamp(str(normalized["collected_at"]))
    bronze_collected_at = parse_timestamp(str(bronze["collected_at"]))

    assert normalized_collected_at == bronze_collected_at


def test_normalize_bronze_record_filters_non_loadable_payloads() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(
            payload={
                "252490": {
                    "success": True,
                    "data": {},
                }
            }
        )
    )

    assert normalized is None


def test_normalize_bronze_record_maps_fallback_true_free_evidence() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(
            fallback={"payload": fallback_payload(is_free=True)},
            payload=missing_price_payload(),
        )
    )

    assert normalized == {
        "bucket_time": "2026-03-13T06:00:00+09:00",
        "canonical_game_id": 1,
        "collected_at": "2026-03-12T21:41:38+00:00",
        "currency_code": None,
        "discount_percent": None,
        "final_price_minor": None,
        "initial_price_minor": None,
        "is_free": True,
        "region": "KR",
        "steam_appid": 252490,
    }


def test_normalize_bronze_record_maps_fallback_true_free_evidence_from_empty_data_list() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(
            fallback={"payload": fallback_payload(is_free=True)},
            payload=empty_filtered_payload(),
        )
    )

    assert normalized is not None
    assert normalized["is_free"] is True
    assert normalized["currency_code"] is None
    assert normalized["initial_price_minor"] is None
    assert normalized["final_price_minor"] is None
    assert normalized["discount_percent"] is None


def test_normalize_bronze_record_drops_fallback_false_or_missing_free_evidence() -> None:
    false_free = normalize_bronze_record(
        make_bronze_row(
            fallback={"payload": fallback_payload(is_free=False)},
            payload=missing_price_payload(),
        )
    )
    missing_free = normalize_bronze_record(
        make_bronze_row(
            fallback={
                "payload": {
                    "252490": {
                        "success": True,
                        "data": {},
                    }
                }
            },
            payload=missing_price_payload(),
        )
    )

    assert false_free is None
    assert missing_free is None


def test_normalize_bronze_record_drops_empty_data_list_when_fallback_is_not_free() -> None:
    false_free = normalize_bronze_record(
        make_bronze_row(
            fallback={"payload": fallback_payload(is_free=False)},
            payload=empty_filtered_payload(),
        )
    )
    malformed_fallback = normalize_bronze_record(
        make_bronze_row(
            fallback={
                "payload": {
                    "252490": {
                        "success": True,
                        "data": [],
                    }
                }
            },
            payload=empty_filtered_payload(),
        )
    )

    assert false_free is None
    assert malformed_fallback is None


def test_normalize_bronze_record_does_not_create_free_row_from_invalid_primary() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(
            fallback={"payload": fallback_payload(is_free=True)},
            payload=None,
        )
    )

    assert normalized is None


def test_normalize_bronze_record_does_not_create_free_row_from_invalid_fallback() -> None:
    normalized = normalize_bronze_record(
        make_bronze_row(
            fallback={"payload": None},
            payload=missing_price_payload(),
        )
    )

    assert normalized is None


def test_dedupe_silver_records_keeps_latest_collected_at_for_same_key() -> None:
    deduped = dedupe_silver_records(
        [
            {
                "bucket_time": "2026-03-13T06:00:00+09:00",
                "canonical_game_id": 1,
                "collected_at": "2026-03-12T21:41:38+00:00",
                "currency_code": "KRW",
                "discount_percent": 0,
                "final_price_minor": 4200000,
                "initial_price_minor": 4200000,
                "is_free": None,
                "region": "KR",
                "steam_appid": 252490,
            },
            {
                "bucket_time": "2026-03-13T06:00:00+09:00",
                "canonical_game_id": 1,
                "collected_at": "2026-03-12T21:45:00+00:00",
                "currency_code": "KRW",
                "discount_percent": 0,
                "final_price_minor": 4100000,
                "initial_price_minor": 4200000,
                "is_free": None,
                "region": "KR",
                "steam_appid": 252490,
            },
        ]
    )

    assert len(deduped) == 1
    assert deduped[0]["final_price_minor"] == 4100000
