from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from chzzk.probe.live_list_temporal_probe import (
    build_temporal_summary,
    fetch_pages,
    merge_pages,
    page_summary,
    parse_timestamp,
    run_exhaustion_probe,
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


def run_exhaustion(tmp_path: Path, handler: Any, **kwargs: Any) -> dict[str, Any]:
    async def collect() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await run_exhaustion_probe(
                client=client,
                headers={},
                base_url="https://example.test/lives",
                size=20,
                output_dir=tmp_path,
                run_id="exhaustion",
                max_pages=kwargs.pop("max_pages", 4),
                time_budget_seconds=kwargs.pop("time_budget_seconds", 5),
                monotonic=kwargs.pop("monotonic", lambda: 0.0),
                **kwargs,
            )

    return asyncio.run(collect())


def synthetic_page(next_value: str | None = None) -> dict[str, Any]:
    return payload(
        [
            live_item(
                category_id="synthetic",
                category_name="Synthetic",
                concurrent=7,
                channel_id="synthetic-channel",
            )
        ],
        next_value=next_value,
    )


def assert_incomplete(summary: dict[str, Any], tmp_path: Path, kind: str) -> None:
    assert summary["pagination"]["termination"] == kind
    assert summary["failure"]["kind"] == kind
    assert summary["run_status"] in {"failed", "partial_failure"}
    assert summary["result_status"] == "not_generated_due_to_fetch_failure"
    for role in ("category", "channel"):
        assert summary[f"{role}_result_rows"] == 0
        assert summary[f"{role}_result_path"] is None
        assert not (tmp_path / "exhaustion" / f"{role}-result.jsonl").exists()
    assert summary["coverage"]["observed_bucket_count"] == 0
    assert summary["pagination"]["bounded_page_cutoff"] == (kind == "safety_cutoff")
    assert json.loads((tmp_path / "exhaustion" / "summary.json").read_text()) == summary


@pytest.fixture
def summary_write_payloads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    original_write_text = Path.write_text

    def observe_write(path: Path, data: str, *args: Any, **kwargs: Any) -> int:
        if path.name == "summary.json":
            writes.append(json.loads(data))
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", observe_write)
    return writes


def test_exhaustion_malformed_summary_is_safe_from_first_write(
    tmp_path: Path,
    summary_write_payloads: list[dict[str, Any]],
) -> None:
    sentinel = "synthetic-provider-code-sentinel"
    malformed = {"code": sentinel, "content": {"data": []}}
    summary = run_exhaustion(tmp_path, lambda request: httpx.Response(200, json=malformed))

    assert all(sentinel not in json.dumps(written) for written in summary_write_payloads)
    assert summary_write_payloads == [summary]
    assert sentinel not in json.dumps(summary)
    assert summary["page_summaries"][0]["malformed_reason"] == "malformed_page"
    assert_incomplete(summary, tmp_path, "malformed_page")
    assert json.loads((tmp_path / "exhaustion" / "raw" / "page-001.json").read_text()) == malformed


def test_exhaustion_cutoff_summary_excludes_unsupported_category_type(
    tmp_path: Path,
    summary_write_payloads: list[dict[str, Any]],
) -> None:
    sentinel = "synthetic-unsupported-category-type-sentinel"
    page = synthetic_page("synthetic-cursor")
    items = page["content"]["data"]
    items.extend(
        [
            {**items[0], "categoryType": value}
            for value in (
                "SPORTS",
                "ENTERTAINMENT",
                "ETC",
                sentinel,
            )
        ]
    )
    summary = run_exhaustion(
        tmp_path,
        lambda request: httpx.Response(200, json=page),
        max_pages=1,
    )

    assert sentinel not in json.dumps(summary)
    assert all(sentinel not in json.dumps(written) for written in summary_write_payloads)
    assert summary_write_payloads == [summary]
    assert summary["page_summaries"][0]["category_type_counts"] == {
        "GAME": 1,
        "SPORTS": 1,
        "ENTERTAINMENT": 1,
        "ETC": 1,
    }
    assert summary["total_live_items"] == 5
    assert_incomplete(summary, tmp_path, "safety_cutoff")
    assert json.loads((tmp_path / "exhaustion" / "raw" / "page-001.json").read_text()) == page


def test_write_probe_run_default_keeps_legacy_summary_write(
    tmp_path: Path,
    summary_write_payloads: list[dict[str, Any]],
) -> None:
    summary = write_probe_run(
        output_dir=tmp_path,
        pages=[synthetic_page("synthetic-cursor")],
        collected_at=parse_timestamp("2026-10-05T10:29:59+09:00"),
        pages_requested=1,
        size=20,
        run_id="legacy",
    )

    assert summary_write_payloads == [summary]
    assert json.loads((tmp_path / "legacy" / "summary.json").read_text()) == summary
    assert summary["failure"] is None
    assert summary["run_status"] == "success"
    assert summary["result_status"] == "category_results_available"
    assert summary["pagination"] == {
        "bounded_page_cutoff": True,
        "followed": False,
        "last_page_next_present": True,
        "last_page_next_type": "str",
        "pages_fetched": 1,
        "pages_requested": 1,
    }
    assert summary["category_type_counts"] == {"GAME": 1}
    assert summary["page_summaries"][0]["category_type_counts"] == {"GAME": 1}
    assert summary["category_result_rows"] == summary["channel_result_rows"] == 1


@pytest.mark.parametrize("max_pages", [2, 4])
def test_exhaustion_success_preserves_anchor_and_row_multiplicity(
    tmp_path: Path,
    max_pages: int,
) -> None:
    events: list[str] = []
    wall_time = parse_timestamp("2026-10-05T10:29:59+09:00")

    def clock() -> Any:
        events.append("anchor")
        return wall_time

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal wall_time
        events.append("request")
        wall_time = parse_timestamp("2026-10-05T10:30:01+09:00")
        return httpx.Response(
            200, json=synthetic_page(None if request.url.params.get("next") else "synthetic-cursor")
        )

    summary = run_exhaustion(tmp_path, handler, max_pages=max_pages, clock=clock)

    assert events == ["anchor", "request", "request"]
    assert summary["failure"] is None
    assert summary["run_status"] == "success"
    assert summary["pages_fetched"] == 2
    assert summary["pages_requested"] == max_pages
    assert summary["pagination"] == {
        "mode": "exhaustion",
        "termination": "pagination_exhausted",
        "requests_performed": 2,
        "time_budget_seconds": 5,
        "bounded_page_cutoff": False,
        "followed": True,
        "last_page_next_present": False,
        "last_page_next_type": "NoneType",
        "pages_fetched": 2,
        "pages_requested": max_pages,
    }
    assert summary["coverage"]["status"] == "observed_bucket_only"
    categories = [
        json.loads(line) for line in Path(summary["category_result_path"]).read_text().splitlines()
    ]
    channels = [
        json.loads(line) for line in Path(summary["channel_result_path"]).read_text().splitlines()
    ]
    assert len(categories) == 1
    assert categories[0]["concurrent_sum"] == 14
    assert categories[0]["live_count"] == 2
    assert len(channels) == 2
    assert channels[0] == channels[1]
    for row in [summary, *categories, *channels]:
        assert row["collected_at"] == "2026-10-05T10:29:59+09:00"
        assert row["bucket_time"] == "2026-10-05T10:00:00+09:00"


def test_exhaustion_ceiling_is_incomplete_with_compatible_cutoff(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=synthetic_page(f"synthetic-cursor-{len(requests)}"))

    summary = run_exhaustion(tmp_path, handler, max_pages=2)

    assert_incomplete(summary, tmp_path, "safety_cutoff")
    assert len(requests) == summary["pagination"]["requests_performed"] == 2
    assert summary["pages_fetched"] == summary["pages_requested"] == 2
    assert summary["failure"]["pages_fetched_before_failure"] == 2
    assert summary["pagination"]["last_page_next_present"] is True


@pytest.mark.parametrize("cursors", [["a", "a"], ["a", "b", "a"]])
def test_exhaustion_cursor_loop_stops_without_another_request(
    tmp_path: Path,
    cursors: list[str],
) -> None:
    requested: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.params.get("next"))
        return httpx.Response(200, json=synthetic_page(cursors[len(requested) - 1]))

    # A loop wins over a simultaneously reached page ceiling.
    summary = run_exhaustion(tmp_path, handler, max_pages=len(cursors))

    assert_incomplete(summary, tmp_path, "pagination_loop_detected")
    assert requested == [None, *cursors[:-1]]
    assert summary["pagination"]["requests_performed"] == len(cursors)
    assert summary["failure"]["pages_fetched_before_failure"] == len(cursors)
    assert summary["pagination"]["last_page_next_present"] is True


@pytest.mark.parametrize(
    ("ticks", "expected_requests"),
    [([0, 5], 0), ([0, 0, 5], 1), ([0, 0, 0, 5], 1)],
)
def test_exhaustion_deadline_blocks_next_request_deterministically(
    tmp_path: Path,
    ticks: list[int],
    expected_requests: int,
) -> None:
    timeline = iter(ticks)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=synthetic_page("synthetic-cursor"))

    summary = run_exhaustion(tmp_path, handler, monotonic=lambda: next(timeline))

    assert_incomplete(summary, tmp_path, "deadline_exceeded")
    assert len(requests) == expected_requests
    assert summary["pagination"]["requests_performed"] == expected_requests
    assert summary["pages_fetched"] == expected_requests
    assert summary["failure"]["pages_fetched_before_failure"] == expected_requests


def test_exhaustion_expired_exhausted_response_is_not_success(tmp_path: Path) -> None:
    timeline = iter([0, 0, 5])
    summary = run_exhaustion(
        tmp_path,
        lambda request: httpx.Response(200, json=synthetic_page()),
        monotonic=lambda: next(timeline),
        max_pages=1,
    )
    assert_incomplete(summary, tmp_path, "deadline_exceeded")
    assert summary["pages_fetched"] == 1
    assert summary["pagination"]["last_page_next_present"] is False


def test_exhaustion_deadline_cancels_inflight_body_without_sleep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_scopes: list[asyncio.Timeout] = []
    budgets: list[float] = []
    events: list[str] = []
    real_timeout = asyncio.timeout

    def controlled_timeout(delay: float) -> asyncio.Timeout:
        budgets.append(delay)
        scope = real_timeout(delay)
        timeout_scopes.append(scope)
        return scope

    class PendingBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> Any:
            loop = asyncio.get_running_loop()
            loop.call_soon(timeout_scopes[-1].reschedule, loop.time())
            try:
                await loop.create_future()
            finally:
                events.append("cancelled")
            yield b""

        async def aclose(self) -> None:
            events.append("closed")

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.params.get("next"):
            return httpx.Response(200, json=synthetic_page("synthetic-cursor"))
        return httpx.Response(200, stream=PendingBody())

    monkeypatch.setattr(asyncio, "timeout", controlled_timeout)
    timeline = iter([0, 0, 2, 2])
    summary = run_exhaustion(tmp_path, handler, monotonic=lambda: next(timeline))

    assert_incomplete(summary, tmp_path, "deadline_exceeded")
    assert budgets == [5, 3]
    assert events == ["cancelled", "closed"]
    assert summary["pagination"]["requests_performed"] == 2
    assert summary["pages_fetched"] == 1
    assert summary["failure"]["pages_fetched_before_failure"] == 1


@pytest.mark.parametrize("prior_pages", [0, 1])
@pytest.mark.parametrize(
    ("failure_kind", "response_kind", "retained"),
    [
        ("quota_http_error", "429", False),
        ("http_error", "503", False),
        ("http_error", "302", False),
        ("request_error", "request", False),
        ("invalid_json", "json", False),
        ("malformed_page", "nonobject", False),
        ("malformed_page", "data", True),
        ("malformed_page", "code", True),
    ],
)
def test_exhaustion_failures_preserve_distinct_page_counts_and_no_derived_result(
    tmp_path: Path,
    prior_pages: int,
    failure_kind: str,
    response_kind: str,
    retained: bool,
) -> None:
    requests: list[httpx.Request] = []
    sentinel = "synthetic-private-response-sentinel"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) <= prior_pages:
            return httpx.Response(200, json=synthetic_page(sentinel))
        if response_kind.isdigit():
            return httpx.Response(
                int(response_kind),
                text=sentinel,
                headers={"Location": f"https://example.test/{sentinel}"},
            )
        if response_kind == "request":
            raise httpx.ReadTimeout(sentinel, request=request)
        if response_kind == "json":
            return httpx.Response(200, text=sentinel)
        if response_kind == "nonobject":
            return httpx.Response(200, json=[sentinel])
        malformed: dict[str, Any] = {"content": {"data": {}, "page": {"next": sentinel}}}
        if response_kind == "code":
            malformed["code"] = sentinel
        return httpx.Response(200, json=malformed)

    summary = run_exhaustion(tmp_path, handler, max_pages=prior_pages + 1)

    assert_incomplete(summary, tmp_path, failure_kind)
    assert len(requests) == summary["pagination"]["requests_performed"] == prior_pages + 1
    assert summary["pages_fetched"] == prior_pages + int(retained)
    assert summary["pages_requested"] == prior_pages + 1
    assert summary["pagination"]["pages_fetched"] == summary["pages_fetched"]
    assert summary["pagination"]["pages_requested"] == prior_pages + 1
    assert summary["pagination"]["last_page_next_present"] == bool(prior_pages or retained)
    assert summary["failure"]["pages_fetched_before_failure"] == prior_pages
    assert summary["failure"]["page_index"] == prior_pages + 1
    assert summary["failure"]["http_status_code"] == (
        int(response_kind) if response_kind.isdigit() else None
    )
    assert sentinel not in json.dumps(summary)
    assert len(list((tmp_path / "exhaustion" / "raw").glob("page-*.json"))) == (
        prior_pages + int(retained)
    )


@pytest.mark.parametrize(
    "budget",
    [0, -1, float("inf"), float("-inf"), float("nan")],
)
def test_exhaustion_rejects_nonfinite_or_nonpositive_budget(tmp_path: Path, budget: float) -> None:
    with pytest.raises(ValueError, match="time_budget_seconds"):
        run_exhaustion(
            tmp_path, lambda request: pytest.fail("unexpected request"), time_budget_seconds=budget
        )
    assert not (tmp_path / "exhaustion").exists()


@pytest.mark.parametrize("ceiling", [0, -1, 1.5, True, float("inf")])
def test_exhaustion_requires_positive_integer_ceiling(tmp_path: Path, ceiling: Any) -> None:
    with pytest.raises(ValueError, match="max_pages"):
        run_exhaustion(
            tmp_path, lambda request: pytest.fail("unexpected request"), max_pages=ceiling
        )
    assert not (tmp_path / "exhaustion").exists()


def test_exhaustion_refuses_reusing_artifacts_before_request(tmp_path: Path) -> None:
    run_exhaustion(tmp_path, lambda request: httpx.Response(200, json=synthetic_page()))
    with pytest.raises(FileExistsError):
        run_exhaustion(tmp_path, lambda request: pytest.fail("unexpected request"))


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
    channel_lines = (tmp_path / "run-a" / "channel-result.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(result_lines) == 1
    assert json.loads(result_lines[0])["concurrent_sum"] == 25
    assert [json.loads(line) for line in channel_lines] == [
        {
            "bucket_time": "2026-04-23T10:30:00+09:00",
            "category_name": "Game Alpha",
            "category_type": "GAME",
            "channel_id": "channel-a",
            "channel_name": "Channel channel-a",
            "chzzk_category_id": "game-alpha",
            "collected_at": "2026-04-23T10:42:00+09:00",
            "concurrent_user_count": 10,
        },
        {
            "bucket_time": "2026-04-23T10:30:00+09:00",
            "category_name": "Game Alpha",
            "category_type": "GAME",
            "channel_id": "channel-b",
            "channel_name": "Channel channel-b",
            "chzzk_category_id": "game-alpha",
            "collected_at": "2026-04-23T10:42:00+09:00",
            "concurrent_user_count": 15,
        },
    ]
    assert summary["channel_result_path"] == str(tmp_path / "run-a" / "channel-result.jsonl")
    assert summary["channel_result_rows"] == 2
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
    channel_lines = (tmp_path / "run-a" / "channel-result.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(result_lines) == 1
    assert len(channel_lines) == 1
    assert json.loads(channel_lines[0])["channel_id"] == "channel-a"
    assert summary["total_live_items"] == 2
    assert summary["channel_result_rows"] == 1
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
    assert summary["channel_result_rows"] == 0
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
    assert summary["channel_result_path"] is None
    assert summary["channel_result_rows"] == 0
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
    result_path_b = tmp_path / "run-b" / "category-result.jsonl"
    result_path_b.parent.mkdir(parents=True)
    result_path_b.write_text(
        json.dumps(
            {
                "bucket_time": "2026-04-23T11:00:00+09:00",
                "category_name": "Game Alpha",
                "category_type": "GAME",
                "chzzk_category_id": "game-alpha",
                "collected_at": "2026-04-23T11:12:00+09:00",
                "concurrent_sum": 24,
                "live_count": 3,
                "top_channel_concurrent": 12,
                "top_channel_id": "channel-b",
                "top_channel_name": "Channel B",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path_b = tmp_path / "run-b" / "summary.json"
    write_json(
        summary_path_b,
        {
            "bucket_time": "2026-04-23T11:00:00+09:00",
            "category_result_path": str(result_path_b),
            "collected_at": "2026-04-23T11:12:00+09:00",
            "coverage": {"status": "observed_bucket_only"},
            "pages_fetched": 2,
            "pagination": {
                "bounded_page_cutoff": True,
                "last_page_next_present": True,
            },
            "result_status": "category_results_available",
            "run_status": "success",
            "skip_counts": {
                "blank_category_live_items": 0,
                "category_fact_ineligible_live_items": 0,
            },
            "total_live_items": 40,
        },
    )

    summary = build_temporal_summary(
        [
            json.loads(summary_path.read_text(encoding="utf-8")),
            json.loads(summary_path_b.read_text(encoding="utf-8")),
        ]
    )

    assert summary["runs"] == 2
    assert summary["runs_with_results"] == 2
    assert summary["runs_excluded_from_comparison"] == 0
    assert summary["runs_with_channel_results"] == 0
    assert summary["runs_missing_channel_results"] == 2
    assert summary["total_pages"] == 4
    assert summary["complete_1d_category_count"] == 0
    assert summary["complete_7d_category_count"] == 0
    assert summary["bounded_page_cutoff_run_count"] == 2
    assert summary["last_page_next_present_run_count"] == 2
    assert summary["blank_category_skipped_live_items_total"] == 1
    assert summary["skipped_live_items_total"] == 1
    assert summary["coverage"] == {
        "full_1d_bucket_requirement": 48,
        "full_7d_bucket_requirement": 336,
        "missing_1d_bucket_count": 46,
        "missing_7d_bucket_count": 334,
        "observed_bucket_candidate_only": True,
        "observed_bucket_count": 2,
        "status": "partial_window",
    }
    assert summary["categories"] == [
        {
            "avg_channels_observed": 2,
            "avg_viewers_observed": 17,
            "bucket_count": 2,
            "category_type": "GAME",
            "chzzk_category_id": "game-alpha",
            "coverage_status": "partial_window",
            "full_1d_candidate_available": False,
            "full_7d_candidate_available": False,
            "live_count_observed_total": 4,
            "missing_1d_bucket_count": 46,
            "missing_7d_bucket_count": 334,
            "observed_bucket_count": 2,
            "peak_channels_observed": 3,
            "peak_viewers_observed": 24,
            "viewer_per_channel_observed": 8.5,
            "viewer_hours_observed": 17.0,
        }
    ]


def test_build_temporal_summary_excludes_failed_runs_from_bucket_coverage(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "run-success" / "category-result.jsonl"
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

    summary = build_temporal_summary(
        [
            {
                "bucket_time": "2026-04-23T10:30:00+09:00",
                "category_result_path": str(result_path),
                "collected_at": "2026-04-23T10:42:00+09:00",
                "coverage": {"status": "observed_bucket_only"},
                "pages_fetched": 1,
                "pagination": {
                    "bounded_page_cutoff": False,
                    "last_page_next_present": False,
                },
                "result_status": "category_results_available",
                "run_id": "run-success",
                "run_status": "success",
                "skip_counts": {
                    "blank_category_live_items": 0,
                    "category_fact_ineligible_live_items": 0,
                },
                "total_live_items": 1,
            },
            {
                "bucket_time": "2026-04-23T11:00:00+09:00",
                "category_result_path": None,
                "collected_at": "2026-04-23T11:03:00+09:00",
                "coverage": {"status": "incomplete_due_to_fetch_failure"},
                "pages_fetched": 1,
                "pagination": {
                    "bounded_page_cutoff": False,
                    "last_page_next_present": True,
                },
                "result_status": "not_generated_due_to_fetch_failure",
                "run_id": "run-partial",
                "run_status": "partial_failure",
                "skip_counts": {
                    "blank_category_live_items": 0,
                    "category_fact_ineligible_live_items": 0,
                },
                "total_live_items": 20,
            },
            {
                "bucket_time": "2026-04-23T11:30:00+09:00",
                "category_result_path": str(tmp_path / "missing" / "category-result.jsonl"),
                "collected_at": "2026-04-23T11:31:00+09:00",
                "coverage": {"status": "observed_bucket_only"},
                "pages_fetched": 1,
                "pagination": {
                    "bounded_page_cutoff": False,
                    "last_page_next_present": False,
                },
                "result_status": "category_results_available",
                "run_id": "run-missing-artifact",
                "run_status": "success",
                "skip_counts": {
                    "blank_category_live_items": 0,
                    "category_fact_ineligible_live_items": 0,
                },
                "total_live_items": 20,
            },
        ]
    )

    assert summary["bucket_times"] == ["2026-04-23T10:30:00+09:00"]
    assert summary["coverage"]["observed_bucket_count"] == 1
    assert summary["coverage"]["missing_1d_bucket_count"] == 47
    assert summary["coverage"]["status"] == "observed_bucket_only"
    assert summary["runs_with_results"] == 1
    assert summary["runs_excluded_from_comparison"] == 2
    assert summary["run_status_counts"] == {
        "partial_failure": 1,
        "success": 2,
    }


def test_build_temporal_summary_computes_unique_channels_from_channel_results(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "run-a" / "category-result.jsonl"
    channel_path = tmp_path / "run-a" / "channel-result.jsonl"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "bucket_time": "2026-04-23T10:30:00+09:00",
                "category_name": "Game Alpha",
                "category_type": "GAME",
                "chzzk_category_id": "game-alpha",
                "collected_at": "2026-04-23T10:42:00+09:00",
                "concurrent_sum": 30,
                "live_count": 2,
                "top_channel_concurrent": 20,
                "top_channel_id": "channel-a",
                "top_channel_name": "Channel A",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    channel_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "bucket_time": "2026-04-23T10:30:00+09:00",
                        "category_name": "Game Alpha",
                        "category_type": "GAME",
                        "channel_id": "channel-a",
                        "channel_name": "Channel A",
                        "chzzk_category_id": "game-alpha",
                        "collected_at": "2026-04-23T10:42:00+09:00",
                        "concurrent_user_count": 20,
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "bucket_time": "2026-04-23T10:30:00+09:00",
                        "category_name": "Game Alpha",
                        "category_type": "GAME",
                        "channel_id": "channel-b",
                        "channel_name": "Channel B",
                        "chzzk_category_id": "game-alpha",
                        "collected_at": "2026-04-23T10:42:00+09:00",
                        "concurrent_user_count": 10,
                    },
                    sort_keys=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_temporal_summary(
        [
            {
                "bucket_time": "2026-04-23T10:30:00+09:00",
                "category_result_path": str(result_path),
                "channel_result_path": str(channel_path),
                "collected_at": "2026-04-23T10:42:00+09:00",
                "coverage": {"status": "observed_bucket_only"},
                "pages_fetched": 1,
                "pagination": {
                    "bounded_page_cutoff": False,
                    "last_page_next_present": False,
                },
                "result_status": "category_results_available",
                "run_status": "success",
                "skip_counts": {
                    "blank_category_live_items": 0,
                    "category_fact_ineligible_live_items": 0,
                },
                "total_live_items": 2,
            }
        ]
    )

    assert summary["runs_with_channel_results"] == 1
    assert summary["runs_missing_channel_results"] == 0
    assert summary["categories"][0]["unique_channels_observed"] == 2
