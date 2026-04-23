"""Bounded local/private Chzzk live-list temporal probe helper."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from chzzk.normalize.category_lives import (
    aggregate_category_lives,
    build_result_row,
    extract_live_items,
    floor_to_kst_half_hour,
    format_kst_iso,
)
from chzzk.normalize.live_list_to_category_result import write_jsonl

KST = ZoneInfo("Asia/Seoul")
DEFAULT_LIVES_URL = "https://openapi.chzzk.naver.com/open/v1/lives"
EXPECTED_BUCKETS_1D = 48
EXPECTED_BUCKETS_7D = 336
BLANK_CATEGORY_FIELDS = ("categoryType", "liveCategory", "liveCategoryValue")
REQUIRED_FIELDS = (
    "categoryType",
    "liveCategory",
    "liveCategoryValue",
    "concurrentUserCount",
    "channelId",
    "channelName",
)


def utc_now() -> dt.datetime:
    """Return a timezone-aware UTC timestamp."""

    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def parse_timestamp(value: str) -> dt.datetime:
    """Parse a timezone-aware ISO timestamp."""

    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def write_json(path: Path, payload: Any) -> None:
    """Write deterministic JSON for local probe artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    """Read one JSON artifact."""

    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read deterministic JSONL result rows."""

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _page_next(payload: Mapping[str, Any]) -> object:
    content = payload.get("content")
    if not isinstance(content, Mapping):
        return None
    page = content.get("page")
    if not isinstance(page, Mapping):
        return None
    return page.get("next")


def _is_missing_required_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _missing_required_fields(item: Mapping[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_FIELDS
        if _is_missing_required_value(item.get(field))
    ]


def _blank_category_fields(item: Mapping[str, Any]) -> list[str]:
    return [
        field
        for field in BLANK_CATEGORY_FIELDS
        if _is_missing_required_value(item.get(field))
    ]


def _bucket_coverage_status(observed_bucket_count: int) -> str:
    if observed_bucket_count >= EXPECTED_BUCKETS_7D:
        return "full_7d_candidate_available"
    if observed_bucket_count >= EXPECTED_BUCKETS_1D:
        return "full_1d_candidate_available"
    if observed_bucket_count <= 0:
        return "no_observed_bucket"
    if observed_bucket_count == 1:
        return "observed_bucket_only"
    return "partial_window"


def _retryable_http_status(http_status_code: int | None) -> bool:
    if http_status_code is None:
        return False
    return http_status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _fetch_failure(
    *,
    kind: str,
    page_index: int,
    pages_fetched_before_failure: int,
    message: str,
    http_status_code: int | None = None,
) -> dict[str, Any]:
    return {
        "http_status_code": http_status_code,
        "kind": kind,
        "message": message,
        "page_index": page_index,
        "pages_fetched_before_failure": pages_fetched_before_failure,
        "retryable": _retryable_http_status(http_status_code)
        if http_status_code is not None
        else kind == "request_error",
    }


def page_summary(payload: Mapping[str, Any], *, page_index: int) -> dict[str, Any]:
    """Build a sanitized shape summary for one Chzzk live-list page."""

    category_type_counts: Counter[str] = Counter()
    blank_category_missing_counts: Counter[str] = Counter()
    blank_category_live_items = 0
    category_fact_ineligible_live_items = 0
    distinct_key_sets = 0
    missing_required_counts: Counter[str] = Counter()
    malformed_reason: str | None = None
    page_status = "success"
    try:
        live_items = extract_live_items(payload)
        key_sets: Counter[tuple[str, ...]] = Counter()
        for item in live_items:
            key_sets[tuple(sorted(item.keys()))] += 1
            category_type = item.get("categoryType")
            if isinstance(category_type, str):
                category_type_counts[category_type] += 1
            missing_fields = _missing_required_fields(item)
            blank_category_fields = _blank_category_fields(item)
            if missing_fields:
                category_fact_ineligible_live_items += 1
                missing_required_counts.update(missing_fields)
            if blank_category_fields:
                blank_category_live_items += 1
                blank_category_missing_counts.update(blank_category_fields)
        distinct_key_sets = len(key_sets)
    except ValueError as exc:
        live_items = []
        malformed_reason = str(exc)
        page_status = "malformed"

    next_value = _page_next(payload)
    summary = {
        "blank_category_live_items": blank_category_live_items,
        "blank_category_missing_counts": dict(
            sorted(blank_category_missing_counts.items())
        ),
        "category_fact_ineligible_live_items": category_fact_ineligible_live_items,
        "category_type_counts": dict(sorted(category_type_counts.items())),
        "data_count": len(live_items),
        "distinct_key_sets": distinct_key_sets,
        "missing_required_counts": dict(sorted(missing_required_counts.items())),
        "next_present": isinstance(next_value, str) and bool(next_value),
        "next_type": type(next_value).__name__,
        "page_index": page_index,
        "page_status": page_status,
    }
    if malformed_reason is not None:
        summary["malformed_reason"] = malformed_reason
    return summary


def merge_pages(
    pages: Sequence[Mapping[str, Any]],
    *,
    skip_missing_required: bool = False,
) -> dict[str, Any]:
    """Merge fetched Chzzk pages into one parser-compatible wrapper."""

    data: list[Mapping[str, Any]] = []
    for payload in pages:
        for item in extract_live_items(payload):
            if skip_missing_required and _missing_required_fields(item):
                continue
            data.append(item)
    return {
        "code": 200,
        "message": None,
        "content": {
            "data": data,
            "page": {"next": _page_next(pages[-1]) if pages else None},
        },
    }


def build_run_summary(
    *,
    run_dir: Path,
    run_id: str,
    collected_at: dt.datetime,
    pages: Sequence[Mapping[str, Any]],
    result_rows: Sequence[Mapping[str, Any]],
    pages_requested: int,
    size: int,
    failure: Mapping[str, Any] | None = None,
    category_result_written: bool = True,
) -> dict[str, Any]:
    """Build a sanitized summary for one bounded probe run."""

    page_summaries = [
        page_summary(payload, page_index=index + 1)
        for index, payload in enumerate(pages)
    ]
    skipped_required_counts: Counter[str] = Counter()
    blank_category_missing_counts: Counter[str] = Counter()
    skipped_live_items = 0
    blank_category_live_items = 0
    blank_category_page_indexes: list[int] = []
    for page in page_summaries:
        skipped_live_items += int(page["category_fact_ineligible_live_items"])
        blank_category_live_items += int(page["blank_category_live_items"])
        skipped_required_counts.update(page["missing_required_counts"])
        blank_category_missing_counts.update(page["blank_category_missing_counts"])
        if int(page["blank_category_live_items"]) > 0:
            blank_category_page_indexes.append(int(page["page_index"]))

    category_type_counts: Counter[str] = Counter()
    for row in result_rows:
        category_type = row.get("category_type")
        if isinstance(category_type, str):
            category_type_counts[category_type] += 1

    total_live_items = sum(page["data_count"] for page in page_summaries)
    bucket_time = format_kst_iso(floor_to_kst_half_hour(collected_at))
    last_page_next_present = bool(page_summaries and page_summaries[-1]["next_present"])
    observed_bucket_count = 1 if failure is None and total_live_items > 0 else 0
    coverage_status = (
        "incomplete_due_to_fetch_failure"
        if failure is not None
        else (
            "empty_data"
            if total_live_items == 0
            else _bucket_coverage_status(observed_bucket_count)
        )
    )
    if failure is not None:
        result_status = "not_generated_due_to_fetch_failure"
        run_status = "partial_failure" if pages else "failed"
    elif total_live_items == 0:
        result_status = "empty_data"
        run_status = "empty_success"
    elif result_rows:
        result_status = "category_results_available"
        run_status = "success"
    else:
        result_status = "all_rows_skipped"
        run_status = "success"

    category_result_path = (
        str(run_dir / "category-result.jsonl") if category_result_written else None
    )
    return {
        "bucket_time": bucket_time,
        "category_result_path": category_result_path,
        "category_result_rows": len(result_rows),
        "category_type_counts": dict(sorted(category_type_counts.items())),
        "collected_at": format_kst_iso(collected_at),
        "coverage": {
            "full_1d_candidate_available": False,
            "full_7d_candidate_available": False,
            "missing_1d_bucket_count": max(0, EXPECTED_BUCKETS_1D - observed_bucket_count),
            "missing_7d_bucket_count": max(0, EXPECTED_BUCKETS_7D - observed_bucket_count),
            "observed_bucket_candidate_only": observed_bucket_count > 0
            and observed_bucket_count < EXPECTED_BUCKETS_1D,
            "observed_bucket_count": observed_bucket_count,
            "status": coverage_status,
        },
        "fact_ready_live_items": total_live_items - skipped_live_items,
        "failure": failure,
        "page_summaries": page_summaries,
        "pages_fetched": len(pages),
        "pages_requested": pages_requested,
        "pagination_followed": len(pages) > 1,
        "pagination": {
            "bounded_page_cutoff": failure is None
            and len(pages) == pages_requested
            and last_page_next_present,
            "followed": len(pages) > 1,
            "last_page_next_present": last_page_next_present,
            "last_page_next_type": page_summaries[-1]["next_type"] if page_summaries else None,
            "pages_fetched": len(pages),
            "pages_requested": pages_requested,
        },
        "raw_page_dir": str(run_dir / "raw"),
        "result_status": result_status,
        "run_id": run_id,
        "run_status": run_status,
        "size": size,
        "skip_counts": {
            "blank_category_live_items": blank_category_live_items,
            "blank_category_missing_counts": dict(
                sorted(blank_category_missing_counts.items())
            ),
            "category_fact_ineligible_live_items": skipped_live_items,
            "missing_required_counts": dict(sorted(skipped_required_counts.items())),
        },
        "skip_evidence": {
            "blank_category_page_indexes": blank_category_page_indexes,
            "blank_category_skip_present": bool(blank_category_page_indexes),
        },
        "skipped_live_items": skipped_live_items,
        "skipped_required_counts": dict(sorted(skipped_required_counts.items())),
        "total_live_items": total_live_items,
    }


def write_probe_run(
    *,
    output_dir: Path,
    pages: Sequence[Mapping[str, Any]],
    collected_at: dt.datetime,
    pages_requested: int,
    size: int,
    run_id: str | None = None,
    failure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write raw pages, category result JSONL, and a sanitized run summary."""

    resolved_run_id = run_id or collected_at.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / resolved_run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for index, payload in enumerate(pages, start=1):
        write_json(raw_dir / f"page-{index:03d}.json", payload)

    category_result_written = False
    if failure is None:
        merged_payload = merge_pages(pages, skip_missing_required=True)
        rows = aggregate_category_lives(
            merged_payload,
            bucket_time=collected_at,
            collected_at=collected_at,
        )
        result_rows = [build_result_row(row) for row in rows]
        write_jsonl(run_dir / "category-result.jsonl", result_rows)
        category_result_written = True
    else:
        result_rows = []

    summary = build_run_summary(
        run_dir=run_dir,
        run_id=resolved_run_id,
        collected_at=collected_at,
        pages=pages,
        result_rows=result_rows,
        pages_requested=pages_requested,
        size=size,
        failure=failure,
        category_result_written=category_result_written,
    )
    write_json(run_dir / "summary.json", summary)
    return summary


def fetch_pages(
    *,
    client: httpx.Client,
    headers: Mapping[str, str],
    base_url: str,
    size: int,
    pages: int,
) -> dict[str, Any]:
    """Fetch a bounded number of Chzzk live-list pages."""

    if not 1 <= size <= 20:
        raise ValueError("size must be between 1 and 20")
    if pages < 1:
        raise ValueError("pages must be at least 1")

    fetched: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for page_index in range(1, pages + 1):
        params = {"size": str(size)}
        if next_cursor:
            params["next"] = next_cursor
        try:
            response = client.get(base_url, headers=headers, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return {
                "failure": _fetch_failure(
                    kind="quota_http_error"
                    if exc.response.status_code == 429
                    else "http_error",
                    page_index=page_index,
                    pages_fetched_before_failure=len(fetched),
                    message=str(exc),
                    http_status_code=exc.response.status_code,
                ),
                "pages": fetched,
            }
        except httpx.RequestError as exc:
            return {
                "failure": _fetch_failure(
                    kind="request_error",
                    page_index=page_index,
                    pages_fetched_before_failure=len(fetched),
                    message=str(exc),
                ),
                "pages": fetched,
            }
        try:
            payload = response.json()
        except ValueError as exc:
            return {
                "failure": _fetch_failure(
                    kind="invalid_json",
                    page_index=page_index,
                    pages_fetched_before_failure=len(fetched),
                    message=str(exc),
                ),
                "pages": fetched,
            }
        if not isinstance(payload, dict):
            return {
                "failure": _fetch_failure(
                    kind="malformed_page",
                    page_index=page_index,
                    pages_fetched_before_failure=len(fetched),
                    message="Chzzk live-list response must be a JSON object",
                ),
                "pages": fetched,
            }
        fetched.append(payload)
        try:
            extract_live_items(payload)
        except ValueError as exc:
            return {
                "failure": _fetch_failure(
                    kind="malformed_page",
                    page_index=page_index,
                    pages_fetched_before_failure=max(0, len(fetched) - 1),
                    message=str(exc),
                ),
                "pages": fetched,
            }

        next_value = _page_next(payload)
        if not isinstance(next_value, str) or not next_value:
            break
        next_cursor = next_value
    return {"failure": None, "pages": fetched}


def _dedupe_rows_by_category_bucket(
    run_rows: Iterable[tuple[str, Mapping[str, Any]]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for collected_at, row in sorted(run_rows, key=lambda item: item[0]):
        category_id = str(row["chzzk_category_id"])
        bucket_time = str(row["bucket_time"])
        rows_by_key[(category_id, bucket_time)] = {**row, "_run_collected_at": collected_at}
    return rows_by_key


def build_temporal_summary(run_summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize multiple local Chzzk probe runs into observed candidate metrics."""

    run_rows: list[tuple[str, Mapping[str, Any]]] = []
    category_ids_by_run: list[set[str]] = []
    run_category_counts: list[dict[str, Any]] = []
    run_status_counts: Counter[str] = Counter()
    result_status_counts: Counter[str] = Counter()
    runs_with_results = 0
    runs_excluded_from_comparison = 0
    bounded_page_cutoff_runs = 0
    last_page_next_present_runs = 0
    skipped_live_items_total = 0
    blank_category_skipped_live_items_total = 0
    total_pages = 0
    total_live_items = 0
    for summary in run_summaries:
        run_status_counts[str(summary.get("run_status", "unknown"))] += 1
        result_status_counts[str(summary.get("result_status", "unknown"))] += 1
        total_pages += int(summary.get("pages_fetched", 0))
        total_live_items += int(summary.get("total_live_items", 0))
        pagination = summary.get("pagination")
        if isinstance(pagination, Mapping):
            if bool(pagination.get("bounded_page_cutoff")):
                bounded_page_cutoff_runs += 1
            if bool(pagination.get("last_page_next_present")):
                last_page_next_present_runs += 1
        skip_counts = summary.get("skip_counts")
        if isinstance(skip_counts, Mapping):
            skipped_live_items_total += int(
                skip_counts.get(
                    "category_fact_ineligible_live_items",
                    summary.get("skipped_live_items", 0),
                )
            )
            blank_category_skipped_live_items_total += int(
                skip_counts.get("blank_category_live_items", 0)
            )
        result_path = summary.get("category_result_path")
        if not isinstance(result_path, str):
            runs_excluded_from_comparison += 1
            continue
        runs_with_results += 1
        rows = read_jsonl(Path(result_path))
        category_ids = {str(row["chzzk_category_id"]) for row in rows}
        category_ids_by_run.append(category_ids)
        run_category_counts.append(
            {
                "category_count": len(category_ids),
                "collected_at": summary.get("collected_at"),
                "coverage_status": summary.get("coverage", {}).get("status"),
                "run_id": summary.get("run_id"),
            }
        )
        for row in rows:
            collected_at = str(summary["collected_at"])
            run_rows.append((collected_at, row))

    rows_by_key = _dedupe_rows_by_category_bucket(run_rows)
    rows_by_category: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for (category_id, _bucket_time), row in sorted(rows_by_key.items()):
        rows_by_category[category_id].append(row)

    categories: list[dict[str, Any]] = []
    for category_id, rows in sorted(rows_by_category.items()):
        concurrent_values = [int(row["concurrent_sum"]) for row in rows]
        live_count_values = [int(row["live_count"]) for row in rows]
        observed_bucket_count = len(rows)
        category_type = str(rows[-1]["category_type"])
        categories.append(
            {
                "avg_viewers_observed": sum(concurrent_values) / len(concurrent_values),
                "bucket_count": observed_bucket_count,
                "category_type": category_type,
                "chzzk_category_id": category_id,
                "coverage_status": _bucket_coverage_status(observed_bucket_count),
                "full_1d_candidate_available": observed_bucket_count
                >= EXPECTED_BUCKETS_1D,
                "full_7d_candidate_available": observed_bucket_count
                >= EXPECTED_BUCKETS_7D,
                "live_count_observed_total": sum(live_count_values),
                "missing_1d_bucket_count": max(
                    0, EXPECTED_BUCKETS_1D - observed_bucket_count
                ),
                "missing_7d_bucket_count": max(
                    0, EXPECTED_BUCKETS_7D - observed_bucket_count
                ),
                "observed_bucket_count": observed_bucket_count,
                "peak_viewers_observed": max(concurrent_values),
                "viewer_hours_observed": sum(value * 0.5 for value in concurrent_values),
            }
        )

    collected_times = sorted(str(summary["collected_at"]) for summary in run_summaries)
    bucket_times = sorted({str(summary["bucket_time"]) for summary in run_summaries})
    complete_1d_categories = sum(
        1 for category in categories if category["full_1d_candidate_available"]
    )
    complete_7d_categories = sum(
        1 for category in categories if category["full_7d_candidate_available"]
    )
    category_ids_seen_all_runs = (
        sorted(set.intersection(*category_ids_by_run)) if category_ids_by_run else []
    )
    category_ids_seen_any_run = (
        sorted(set.union(*category_ids_by_run)) if category_ids_by_run else []
    )
    observed_window_bucket_count = len(bucket_times)
    return {
        "bucket_times": bucket_times,
        "categories": categories,
        "categories_seen_all_runs": len(category_ids_seen_all_runs),
        "categories_seen_any_run": len(category_ids_seen_any_run),
        "categories_seen": len(categories),
        "collected_at_first": collected_times[0] if collected_times else None,
        "collected_at_last": collected_times[-1] if collected_times else None,
        "complete_1d_category_count": complete_1d_categories,
        "complete_7d_category_count": complete_7d_categories,
        "coverage_note": (
            "1d/7d metrics remain observed local candidates unless each category has "
            f"{EXPECTED_BUCKETS_1D}/{EXPECTED_BUCKETS_7D} distinct KST half-hour "
            "buckets respectively."
        ),
        "coverage": {
            "full_1d_bucket_requirement": EXPECTED_BUCKETS_1D,
            "full_7d_bucket_requirement": EXPECTED_BUCKETS_7D,
            "missing_1d_bucket_count": max(
                0, EXPECTED_BUCKETS_1D - observed_window_bucket_count
            ),
            "missing_7d_bucket_count": max(
                0, EXPECTED_BUCKETS_7D - observed_window_bucket_count
            ),
            "observed_bucket_candidate_only": observed_window_bucket_count > 0
            and observed_window_bucket_count < EXPECTED_BUCKETS_1D,
            "observed_bucket_count": observed_window_bucket_count,
            "status": _bucket_coverage_status(observed_window_bucket_count),
        },
        "last_page_next_present_run_count": last_page_next_present_runs,
        "blank_category_skipped_live_items_total": blank_category_skipped_live_items_total,
        "bounded_page_cutoff_run_count": bounded_page_cutoff_runs,
        "result_status_counts": dict(sorted(result_status_counts.items())),
        "runs": len(run_summaries),
        "runs_excluded_from_comparison": runs_excluded_from_comparison,
        "run_category_counts": run_category_counts,
        "run_status_counts": dict(sorted(run_status_counts.items())),
        "runs_with_results": runs_with_results,
        "skipped_live_items_total": skipped_live_items_total,
        "total_live_items": total_live_items,
        "total_pages": total_pages,
    }


def run_fetch(args: argparse.Namespace) -> None:
    client_id = os.environ.get("CHZZK_CLIENT_ID")
    client_secret = os.environ.get("CHZZK_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("CHZZK_CLIENT_ID and CHZZK_CLIENT_SECRET are required")

    collected_at = utc_now()
    with httpx.Client(timeout=args.timeout) as client:
        fetch_result = fetch_pages(
            client=client,
            headers={"Client-Id": client_id, "Client-Secret": client_secret},
            base_url=args.base_url,
            size=args.size,
            pages=args.pages,
        )

    summary = write_probe_run(
        output_dir=args.output_dir,
        pages=fetch_result["pages"],
        collected_at=collected_at,
        pages_requested=args.pages,
        size=args.size,
        run_id=args.run_id,
        failure=fetch_result["failure"],
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if fetch_result["failure"] is not None:
        raise SystemExit(1)


def run_summarize(args: argparse.Namespace) -> None:
    run_summaries = [read_json(path) for path in args.summary]
    summary = build_temporal_summary(run_summaries)
    write_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for local/private Chzzk temporal probes."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch a bounded live-list run")
    fetch_parser.add_argument("--output-dir", type=Path, required=True)
    fetch_parser.add_argument("--pages", type=int, default=3)
    fetch_parser.add_argument("--size", type=int, default=20)
    fetch_parser.add_argument("--run-id")
    fetch_parser.add_argument("--base-url", default=DEFAULT_LIVES_URL)
    fetch_parser.add_argument("--timeout", type=float, default=20.0)
    fetch_parser.set_defaults(func=run_fetch)

    summarize_parser = subparsers.add_parser("summarize", help="Summarize probe runs")
    summarize_parser.add_argument("--summary", type=Path, nargs="+", required=True)
    summarize_parser.add_argument("--output", type=Path, required=True)
    summarize_parser.set_defaults(func=run_summarize)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
