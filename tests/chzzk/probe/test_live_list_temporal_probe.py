from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chzzk.probe.live_list_temporal_probe import (
    build_temporal_summary,
    merge_pages,
    page_summary,
    parse_timestamp,
    write_json,
    write_probe_run,
)


def payload(items: list[dict[str, Any]], *, next_value: str | None = None) -> dict[str, Any]:
    return {
        "code": 200,
        "message": None,
        "content": {
            "data": items,
            "page": {"next": next_value},
        },
    }


def live_item(
    *,
    category_id: str,
    category_name: str,
    concurrent: int,
    channel_id: str,
) -> dict[str, Any]:
    return {
        "categoryType": "GAME",
        "channelId": channel_id,
        "channelName": f"Channel {channel_id}",
        "concurrentUserCount": concurrent,
        "liveCategory": category_id,
        "liveCategoryValue": category_name,
    }


def test_page_summary_records_shape_without_ugc_values() -> None:
    summary = page_summary(
        payload(
            [
                live_item(
                    category_id="game-alpha",
                    category_name="Game Alpha",
                    concurrent=10,
                    channel_id="channel-a",
                )
            ],
            next_value="cursor-1",
        ),
        page_index=1,
    )

    assert summary == {
        "category_type_counts": {"GAME": 1},
        "data_count": 1,
        "distinct_key_sets": 1,
        "missing_required_counts": {},
        "next_present": True,
        "next_type": "str",
        "page_index": 1,
    }


def test_write_probe_run_merges_pages_before_category_aggregation(tmp_path: Path) -> None:
    first_page = payload(
        [
            live_item(
                category_id="game-alpha",
                category_name="Game Alpha",
                concurrent=10,
                channel_id="channel-a",
            )
        ],
        next_value="cursor-1",
    )
    second_page = payload(
        [
            live_item(
                category_id="game-alpha",
                category_name="Game Alpha",
                concurrent=15,
                channel_id="channel-b",
            )
        ]
    )

    summary = write_probe_run(
        output_dir=tmp_path,
        pages=[first_page, second_page],
        collected_at=parse_timestamp("2026-04-23T10:42:00+09:00"),
        pages_requested=3,
        size=20,
        run_id="run-a",
    )

    result_lines = (tmp_path / "run-a" / "category-result.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(result_lines) == 1
    assert json.loads(result_lines[0])["concurrent_sum"] == 25
    assert summary["pages_fetched"] == 2
    assert summary["pagination_followed"] is True


def test_write_probe_run_skips_category_fact_ineligible_live_rows(tmp_path: Path) -> None:
    page = payload(
        [
            live_item(
                category_id="game-alpha",
                category_name="Game Alpha",
                concurrent=10,
                channel_id="channel-a",
            ),
            live_item(
                category_id="",
                category_name="",
                concurrent=15,
                channel_id="channel-b",
            ),
        ]
    )

    summary = write_probe_run(
        output_dir=tmp_path,
        pages=[page],
        collected_at=parse_timestamp("2026-04-23T10:42:00+09:00"),
        pages_requested=1,
        size=20,
        run_id="run-a",
    )

    result_lines = (tmp_path / "run-a" / "category-result.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(result_lines) == 1
    assert summary["total_live_items"] == 2
    assert summary["fact_ready_live_items"] == 1
    assert summary["skipped_live_items"] == 1
    assert summary["skipped_required_counts"] == {
        "liveCategory": 1,
        "liveCategoryValue": 1,
    }


def test_merge_pages_preserves_parser_compatible_wrapper() -> None:
    merged = merge_pages(
        [
            payload(
                [
                    live_item(
                        category_id="game-alpha",
                        category_name="Game Alpha",
                        concurrent=10,
                        channel_id="channel-a",
                    )
                ],
                next_value="cursor-1",
            ),
            payload(
                [
                    live_item(
                        category_id="game-beta",
                        category_name="Game Beta",
                        concurrent=5,
                        channel_id="channel-b",
                    )
                ]
            ),
        ]
    )

    assert merged["code"] == 200
    assert len(merged["content"]["data"]) == 2


def test_build_temporal_summary_marks_1d_7d_candidates_incomplete(tmp_path: Path) -> None:
    result_path = tmp_path / "run-a" / "category-result.jsonl"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "bucket_time": "2026-04-23T10:30:00+09:00",
                "category_name": "Game Alpha",
                "category_type": "GAME",
                "chzzk_category_id": "game-alpha",
                "collected_at": "2026-04-23T10:42:00+09:00",
                "concurrent_sum": 10,
                "live_count": 1,
                "top_channel_concurrent": 10,
                "top_channel_id": "channel-a",
                "top_channel_name": "Channel A",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "run-a" / "summary.json"
    write_json(
        summary_path,
        {
            "bucket_time": "2026-04-23T10:30:00+09:00",
            "category_result_path": str(result_path),
            "collected_at": "2026-04-23T10:42:00+09:00",
            "pages_fetched": 2,
            "total_live_items": 40,
        },
    )

    summary = build_temporal_summary([json.loads(summary_path.read_text(encoding="utf-8"))])

    assert summary["runs"] == 1
    assert summary["total_pages"] == 2
    assert summary["complete_1d_category_count"] == 0
    assert summary["complete_7d_category_count"] == 0
    assert summary["categories"] == [
        {
            "avg_viewers_observed": 10,
            "bucket_count": 1,
            "category_type": "GAME",
            "chzzk_category_id": "game-alpha",
            "full_1d_candidate_available": False,
            "full_7d_candidate_available": False,
            "live_count_observed_total": 1,
            "peak_viewers_observed": 10,
            "viewer_hours_observed": 5.0,
        }
    ]
