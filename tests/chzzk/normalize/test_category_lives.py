from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from chzzk.normalize.category_lives import (
    ChzzkCategoryFactRow,
    aggregate_category_lives,
    format_kst_iso,
    process_live_payload,
)
from chzzk.normalize.live_list_to_category_result import main as category_result_main

FIXTURE_PATH = Path("tests/fixtures/chzzk/lives/representative.json")


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert(self, row: ChzzkCategoryFactRow) -> None:
        key = (row.chzzk_category_id, format_kst_iso(row.bucket_time))
        self.rows[key] = {
            "category_name": row.category_name,
            "category_type": row.category_type,
            "collected_at": format_kst_iso(row.collected_at),
            "concurrent_sum": row.concurrent_sum,
            "live_count": row.live_count,
            "top_channel_concurrent": row.top_channel_concurrent,
            "top_channel_id": row.top_channel_id,
            "top_channel_name": row.top_channel_name,
        }


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_aggregate_category_lives_builds_category_bucket_rows() -> None:
    rows = aggregate_category_lives(
        load_fixture(),
        bucket_time="2026-04-20T12:42:10+09:00",
        collected_at="2026-04-20T03:42:10Z",
    )

    assert [row.chzzk_category_id for row in rows] == [
        "etc-category-delta",
        "game-category-alpha",
        "game-category-gamma",
    ]

    delta = rows[0]
    assert delta.category_type == "ETC"
    assert delta.category_name == "Representative Etc Category Delta"
    assert delta.concurrent_sum == 100
    assert delta.live_count == 1

    alpha = rows[1]
    assert format_kst_iso(alpha.bucket_time) == "2026-04-20T12:30:00+09:00"
    assert alpha.category_type == "GAME"
    assert alpha.category_name == "Representative Game Alpha"
    assert alpha.concurrent_sum == 2000
    assert alpha.live_count == 2
    assert alpha.top_channel_id == "channel-alpha"
    assert alpha.top_channel_name == "Streamer Alpha"
    assert alpha.top_channel_concurrent == 1200

    gamma = rows[2]
    assert gamma.concurrent_sum == 300
    assert gamma.live_count == 1


def test_process_live_payload_is_idempotent_for_same_payload() -> None:
    payload = load_fixture()
    store = FakeFactStore()

    first_results = process_live_payload(
        payload,
        bucket_time="2026-04-20T12:42:10+09:00",
        collected_at="2026-04-20T03:42:10Z",
        upsert_row=store.upsert,
    )
    second_results = process_live_payload(
        payload,
        bucket_time="2026-04-20T12:42:10+09:00",
        collected_at="2026-04-20T03:42:10Z",
        upsert_row=store.upsert,
    )

    assert len(store.rows) == 3
    assert first_results == second_results
    assert store.rows[("game-category-alpha", "2026-04-20T12:30:00+09:00")][
        "concurrent_sum"
    ] == 2000


def test_category_result_cli_writes_deterministic_jsonl(tmp_path: Path) -> None:
    output_path = tmp_path / "category-result.jsonl"
    second_output_path = tmp_path / "category-result-second.jsonl"
    args = [
        "--input",
        str(FIXTURE_PATH),
        "--output",
        str(output_path),
        "--bucket-time",
        "2026-04-20T12:42:10+09:00",
        "--collected-at",
        "2026-04-20T03:42:10Z",
    ]

    category_result_main(args)
    category_result_main([*args[:3], str(second_output_path), *args[4:]])

    assert output_path.read_text(encoding="utf-8") == second_output_path.read_text(
        encoding="utf-8"
    )
    assert output_path.read_text(encoding="utf-8").splitlines() == [
        json.dumps(
            {
                "bucket_time": "2026-04-20T12:30:00+09:00",
                "category_name": "Representative Etc Category Delta",
                "category_type": "ETC",
                "chzzk_category_id": "etc-category-delta",
                "collected_at": "2026-04-20T12:42:10+09:00",
                "concurrent_sum": 100,
                "live_count": 1,
                "top_channel_concurrent": 100,
                "top_channel_id": "channel-delta",
                "top_channel_name": "Streamer Delta",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        json.dumps(
            {
                "bucket_time": "2026-04-20T12:30:00+09:00",
                "category_name": "Representative Game Alpha",
                "category_type": "GAME",
                "chzzk_category_id": "game-category-alpha",
                "collected_at": "2026-04-20T12:42:10+09:00",
                "concurrent_sum": 2000,
                "live_count": 2,
                "top_channel_concurrent": 1200,
                "top_channel_id": "channel-alpha",
                "top_channel_name": "Streamer Alpha",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        json.dumps(
            {
                "bucket_time": "2026-04-20T12:30:00+09:00",
                "category_name": "Representative Game Gamma",
                "category_type": "GAME",
                "chzzk_category_id": "game-category-gamma",
                "collected_at": "2026-04-20T12:42:10+09:00",
                "concurrent_sum": 300,
                "live_count": 1,
                "top_channel_concurrent": 300,
                "top_channel_id": "channel-gamma",
                "top_channel_name": "Streamer Gamma",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    ]


def test_aggregate_category_lives_rejects_failed_common_response() -> None:
    with pytest.raises(ValueError, match="not successful"):
        aggregate_category_lives(
            {"code": 401, "message": "client auth required"},
            bucket_time="2026-04-20T12:42:10+09:00",
            collected_at="2026-04-20T03:42:10Z",
        )


def test_aggregate_category_lives_accepts_observed_entertainment_type() -> None:
    payload = load_fixture()
    mutated = copy.deepcopy(payload)
    item = mutated["content"]["data"][0]
    item["categoryType"] = "ENTERTAINMENT"
    item["liveCategory"] = "entertainment-category-alpha"
    item["liveCategoryValue"] = "Representative Entertainment Alpha"

    rows = aggregate_category_lives(
        mutated,
        bucket_time="2026-04-20T12:42:10+09:00",
        collected_at="2026-04-20T03:42:10Z",
    )

    entertainment_rows = [
        row for row in rows if row.chzzk_category_id == "entertainment-category-alpha"
    ]
    assert len(entertainment_rows) == 1
    assert entertainment_rows[0].category_type == "ENTERTAINMENT"
    assert entertainment_rows[0].category_name == "Representative Entertainment Alpha"


def test_aggregate_category_lives_rejects_missing_category_id() -> None:
    payload = load_fixture()
    mutated = copy.deepcopy(payload)
    del mutated["content"]["data"][0]["liveCategory"]

    with pytest.raises(ValueError, match="liveCategory is required"):
        aggregate_category_lives(
            mutated,
            bucket_time="2026-04-20T12:42:10+09:00",
            collected_at="2026-04-20T03:42:10Z",
        )


def test_aggregate_category_lives_rejects_negative_concurrent() -> None:
    payload = load_fixture()
    mutated = copy.deepcopy(payload)
    mutated["content"]["data"][0]["concurrentUserCount"] = -1

    with pytest.raises(ValueError, match="concurrentUserCount must be non-negative"):
        aggregate_category_lives(
            mutated,
            bucket_time="2026-04-20T12:42:10+09:00",
            collected_at="2026-04-20T03:42:10Z",
        )
