from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from chzzk.probe.live_list_temporal_probe import (
    build_temporal_summary,
    fetch_pages,
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
        "blank_category_live_items": 0,
        "blank_category_missing_counts": {},
        "category_fact_ineligible_live_items": 0,
        "category_type_counts": {"GAME": 1},
        "data_count": 1,
        "distinct_key_sets": 1,
        "missing_required_counts": {},
        "next_present": True,
        "next_type": "str",
        "page_index": 1,
        "page_status": "success",
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
    assert summary["run_status"] == "success"
    assert summary["result_status"] == "category_results_available"
    assert summary["pagination"] == {
        "bounded_page_cutoff": False,
        "followed": True,
        "last_page_next_present": False,
        "last_page_next_type": "NoneType",
        "pages_fetched": 2,
        "pages_requested": 3,
    }
    assert summary["coverage"] == {
        "full_1d_candidate_available": False,
        "full_7d_candidate_available": False,
        "missing_1d_bucket_count": 47,
        "missing_7d_bucket_count": 335,
        "observed_bucket_candidate_only": True,
        "observed_bucket_count": 1,
        "status": "observed_bucket_only",
    }


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
    assert summary["skip_counts"] == {
        "blank_category_live_items": 1,
        "blank_category_missing_counts": {
            "liveCategory": 1,
            "liveCategoryValue": 1,
        },
        "category_fact_ineligible_live_items": 1,
        "missing_required_counts": {
            "liveCategory": 1,
            "liveCategoryValue": 1,
        },
    }
    assert summary["skip_evidence"] == {
        "blank_category_page_indexes": [1],
        "blank_category_skip_present": True,
    }


def test_write_probe_run_marks_empty_success_without_category_rows(tmp_path: Path) -> None:
    summary = write_probe_run(
        output_dir=tmp_path,
        pages=[payload([], next_value=None)],
        collected_at=parse_timestamp("2026-04-23T10:42:00+09:00"),
        pages_requested=1,
        size=20,
        run_id="run-empty",
    )

    assert summary["run_status"] == "empty_success"
    assert summary["result_status"] == "empty_data"
    assert summary["category_result_rows"] == 0
    assert summary["coverage"] == {
        "full_1d_candidate_available": False,
        "full_7d_candidate_available": False,
        "missing_1d_bucket_count": 48,
        "missing_7d_bucket_count": 336,
        "observed_bucket_candidate_only": False,
        "observed_bucket_count": 0,
        "status": "empty_data",
    }


def test_write_probe_run_records_partial_quota_failure_without_result_rows(
    tmp_path: Path,
) -> None:
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

    summary = write_probe_run(
        output_dir=tmp_path,
        pages=[first_page],
        collected_at=parse_timestamp("2026-04-23T10:42:00+09:00"),
        pages_requested=3,
        size=20,
        run_id="run-partial",
        failure={
            "http_status_code": 429,
            "kind": "quota_http_error",
            "message": "quota exceeded",
            "page_index": 2,
            "pages_fetched_before_failure": 1,
            "retryable": True,
        },
    )

    assert summary["run_status"] == "partial_failure"
    assert summary["result_status"] == "not_generated_due_to_fetch_failure"
    assert summary["category_result_path"] is None
    assert summary["category_result_rows"] == 0
    assert summary["failure"] == {
        "http_status_code": 429,
        "kind": "quota_http_error",
        "message": "quota exceeded",
        "page_index": 2,
        "pages_fetched_before_failure": 1,
        "retryable": True,
    }
    assert summary["pagination"] == {
        "bounded_page_cutoff": False,
        "followed": False,
        "last_page_next_present": True,
        "last_page_next_type": "str",
        "pages_fetched": 1,
        "pages_requested": 3,
    }


def test_fetch_pages_reports_quota_http_failure_after_first_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("next") == "cursor-1":
            return httpx.Response(429, json={"code": 429, "message": "too many requests"})
        return httpx.Response(
            200,
            json=payload(
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
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_pages(
            client=client,
            headers={},
            base_url="https://example.test/lives",
            size=20,
            pages=3,
        )

    assert len(result["pages"]) == 1
    assert result["failure"]["http_status_code"] == 429
    assert result["failure"]["kind"] == "quota_http_error"
    assert result["failure"]["page_index"] == 2
    assert result["failure"]["pages_fetched_before_failure"] == 1
    assert result["failure"]["retryable"] is True
    assert "429 Too Many Requests" in result["failure"]["message"]


def test_fetch_pages_keeps_malformed_page_as_local_failure_evidence(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("next") == "cursor-1":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "content": {"data": {"not": "a-list"}, "page": {"next": None}},
                },
            )
        return httpx.Response(
            200,
            json=payload(
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
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_pages(
            client=client,
            headers={},
            base_url="https://example.test/lives",
            size=20,
            pages=3,
        )

    assert len(result["pages"]) == 2
    assert result["failure"] == {
        "http_status_code": None,
        "kind": "malformed_page",
        "message": "Chzzk live payload must contain a data list",
        "page_index": 2,
        "pages_fetched_before_failure": 1,
        "retryable": False,
    }

    summary = write_probe_run(
        output_dir=tmp_path,
        pages=result["pages"],
        collected_at=parse_timestamp("2026-04-23T10:42:00+09:00"),
        pages_requested=3,
        size=20,
        run_id="run-malformed",
        failure=result["failure"],
    )

    assert summary["page_summaries"][1]["page_status"] == "malformed"
    assert summary["page_summaries"][1]["malformed_reason"] == (
        "Chzzk live payload must contain a data list"
    )


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
            "coverage": {"status": "observed_bucket_only"},
            "pages_fetched": 2,
            "pagination": {
                "bounded_page_cutoff": True,
                "last_page_next_present": True,
            },
            "result_status": "category_results_available",
            "run_status": "success",
            "skip_counts": {
                "blank_category_live_items": 1,
                "category_fact_ineligible_live_items": 1,
            },
            "total_live_items": 40,
        },
    )

    summary = build_temporal_summary([json.loads(summary_path.read_text(encoding="utf-8"))])

    assert summary["runs"] == 1
    assert summary["runs_with_results"] == 1
    assert summary["runs_excluded_from_comparison"] == 0
    assert summary["total_pages"] == 2
    assert summary["complete_1d_category_count"] == 0
    assert summary["complete_7d_category_count"] == 0
    assert summary["bounded_page_cutoff_run_count"] == 1
    assert summary["last_page_next_present_run_count"] == 1
    assert summary["blank_category_skipped_live_items_total"] == 1
    assert summary["skipped_live_items_total"] == 1
    assert summary["coverage"] == {
        "full_1d_bucket_requirement": 48,
        "full_7d_bucket_requirement": 336,
        "missing_1d_bucket_count": 47,
        "missing_7d_bucket_count": 335,
        "observed_bucket_candidate_only": True,
        "observed_bucket_count": 1,
        "status": "observed_bucket_only",
    }
    assert summary["categories"] == [
        {
            "avg_viewers_observed": 10,
            "bucket_count": 1,
            "category_type": "GAME",
            "chzzk_category_id": "game-alpha",
            "coverage_status": "observed_bucket_only",
            "full_1d_candidate_available": False,
            "full_7d_candidate_available": False,
            "live_count_observed_total": 1,
            "missing_1d_bucket_count": 47,
            "missing_7d_bucket_count": 335,
            "observed_bucket_count": 1,
            "peak_viewers_observed": 10,
            "viewer_hours_observed": 5.0,
        }
    ]
