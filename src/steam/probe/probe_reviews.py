"""Probe Steam GetAppReviews endpoint and store a reproducible snapshot."""

from __future__ import annotations

import argparse
import logging
import math
import re
from collections.abc import Iterable
from typing import Any

from steam.ingest.fetch_reviews_daily import REQUEST_URL, build_request_params
from steam.probe.common import (
    RequestResult,
    add_common_probe_arguments,
    build_snapshot,
    configure_logging,
    decode_json_payload,
    request_with_retry,
    resolve_app_id,
    runtime_config_from_args,
    save_snapshot,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)
PROBE_NAME = "reviews"
REVIEW_EXCERPT_COUNT = 3
# Persisted probe summaries keep only allowlisted fields whose values pass a type check,
# so provider-controlled text cannot reach a snapshot through an unexpected value type.
REVIEW_EXCERPT_INT_FIELDS = (
    "app_release_date",
    "comment_count",
    "timestamp_created",
    "timestamp_updated",
    "votes_funny",
    "votes_up",
)
REVIEW_EXCERPT_BOOL_FIELDS = (
    "primarily_steam_deck",
    "received_for_free",
    "refunded",
    "steam_purchase",
    "voted_up",
    "written_during_early_access",
)
REVIEW_EXCERPT_FIELDS = (
    *REVIEW_EXCERPT_INT_FIELDS,
    *REVIEW_EXCERPT_BOOL_FIELDS,
    "language",
    "weighted_vote_score",
)
QUERY_SUMMARY_FIELDS = (
    "num_reviews",
    "review_score",
    "total_negative",
    "total_positive",
    "total_reviews",
)
LANGUAGE_PATTERN = re.compile(r"[a-z][a-z_-]{0,31}")
DECIMAL_PATTERN = re.compile(r"[0-9]{1,8}(\.[0-9]{1,24})?")
KEY_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


def json_type_name(value: Any) -> str:
    """Return the JSON type of a value without echoing the value itself."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def safe_key_names(keys: Iterable[Any]) -> list[str]:
    """Keep identifier-like key names only, so odd provider keys cannot carry free text."""

    return sorted(
        {key for key in keys if isinstance(key, str) and KEY_NAME_PATTERN.fullmatch(key)}
    )


def is_safe_excerpt_value(field: str, value: Any) -> bool:
    if field in REVIEW_EXCERPT_INT_FIELDS:
        return type(value) is int
    if field in REVIEW_EXCERPT_BOOL_FIELDS:
        return type(value) is bool
    if field == "language":
        return isinstance(value, str) and LANGUAGE_PATTERN.fullmatch(value) is not None
    if field == "weighted_vote_score":
        if type(value) in (int, float):
            return math.isfinite(value)
        return isinstance(value, str) and DECIMAL_PATTERN.fullmatch(value) is not None
    return False


def summarize_query_summary(query_summary: dict[str, Any]) -> dict[str, int]:
    """Keep allowlisted integer counts; drop `review_score_desc` and anything unrecognized."""

    return {
        field: query_summary[field]
        for field in QUERY_SUMMARY_FIELDS
        if type(query_summary.get(field)) is int
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: GetAppReviews")
    add_common_probe_arguments(parser)
    parser.add_argument("--app-id", type=int, default=None)
    return parser


def summarize_review_entry(review: Any) -> dict[str, Any]:
    """Return a public-safe structural summary for one review row."""

    if not isinstance(review, dict):
        return {"entry_type": json_type_name(review)}

    summary: dict[str, Any] = {}
    dropped_fields: list[str] = []
    for field in REVIEW_EXCERPT_FIELDS:
        if field not in review:
            continue
        if is_safe_excerpt_value(field, review[field]):
            summary[field] = review[field]
        else:
            dropped_fields.append(field)
    if dropped_fields:
        summary["excerpt_fields_dropped"] = sorted(dropped_fields)

    author = review.get("author")
    if isinstance(author, dict):
        summary["author_fields_present"] = safe_key_names(author.keys())
        summary["author_summary_redacted"] = True

    reactions = review.get("reactions")
    if isinstance(reactions, list):
        summary["reaction_count"] = len(reactions)

    review_text = review.get("review")
    if isinstance(review_text, str):
        summary["review_text_length"] = len(review_text)
        summary["review_text_redacted"] = True

    if "recommendationid" in review:
        summary["recommendationid_redacted"] = True

    return summary


def summarize_reviews_payload(
    payload: Any,
    *,
    excerpt_count: int = REVIEW_EXCERPT_COUNT,
) -> Any:
    """Return a bounded public-safe summary for a GetAppReviews `response` envelope."""

    if not isinstance(payload, dict):
        return {"payload_type": json_type_name(payload)}

    summary: dict[str, Any] = {
        "top_level_keys": safe_key_names(payload.keys()),
    }

    response = payload.get("response")
    if not isinstance(response, dict):
        return summary

    summary["response_keys"] = safe_key_names(response.keys())

    query_summary = response.get("query_summary")
    if isinstance(query_summary, dict):
        summary["query_summary"] = summarize_query_summary(query_summary)

    for key in ("day_range_used", "total_matching"):
        value = response.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            summary[key] = value

    cursor = response.get("cursor")
    if isinstance(cursor, str):
        summary["cursor_present"] = bool(cursor)

    reviews = response.get("reviews")
    if isinstance(reviews, list):
        summary["reviews_count"] = len(reviews)
        summary["review_fields_present"] = safe_key_names(
            key
            for review in reviews
            if isinstance(review, dict)
            for key in review.keys()
        )
        author_fields = safe_key_names(
            key
            for review in reviews
            if isinstance(review, dict)
            for author in [review.get("author")]
            if isinstance(author, dict)
            for key in author.keys()
        )
        if author_fields:
            summary["author_fields_present"] = author_fields
        summary["reviews_excerpt"] = [
            summarize_review_entry(review)
            for review in reviews[:excerpt_count]
        ]

    return summary


def build_probe_snapshot(
    *,
    result: RequestResult,
    timeout_seconds: float,
    request_url: str,
    request_params: dict[str, str],
) -> dict[str, Any]:
    """Build the persisted probe snapshot with a public-safe payload summary."""

    payload = decode_json_payload(result.body)
    if payload is None:
        # Never persist a raw body excerpt; body_size and body_sha256 stay in the snapshot.
        payload_excerpt_or_json: Any = {"non_json": True} if result.body else None
    else:
        payload_excerpt_or_json = summarize_reviews_payload(payload)

    return build_snapshot(
        probe_name=PROBE_NAME,
        collected_at_utc=utc_now_iso(),
        request_url=request_url,
        request_params=request_params,
        timeout_seconds=timeout_seconds,
        result=result,
        payload_excerpt_or_json=payload_excerpt_or_json,
    )


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    runtime = runtime_config_from_args(args)

    app_id = resolve_app_id(args.app_id)
    params = build_request_params(app_id)

    result = request_with_retry(
        url=REQUEST_URL,
        params=params,
        timeout_seconds=runtime.timeout_seconds,
        max_attempts=runtime.max_attempts,
        backoff_base_seconds=runtime.backoff_base_seconds,
        jitter_max_seconds=runtime.jitter_max_seconds,
        max_backoff_seconds=runtime.max_backoff_seconds,
        logger=LOGGER,
    )

    snapshot = build_probe_snapshot(
        result=result,
        timeout_seconds=runtime.timeout_seconds,
        request_url=REQUEST_URL,
        request_params=params,
    )
    output_path = save_snapshot(out_dir=runtime.out_dir, probe_name=PROBE_NAME, snapshot=snapshot)
    LOGGER.info("Saved %s snapshot to %s", PROBE_NAME, output_path)


if __name__ == "__main__":
    main()
