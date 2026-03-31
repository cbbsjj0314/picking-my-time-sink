"""Probe Steam reviews endpoint and store a reproducible snapshot."""

from __future__ import annotations

import argparse
import logging
from typing import Any

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
    text_excerpt,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)
PROBE_NAME = "reviews"
REQUEST_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{app_id}"
REVIEW_EXCERPT_COUNT = 3
REVIEW_EXCERPT_FIELDS = (
    "app_release_date",
    "comment_count",
    "language",
    "primarily_steam_deck",
    "received_for_free",
    "refunded",
    "steam_purchase",
    "timestamp_created",
    "timestamp_updated",
    "voted_up",
    "votes_funny",
    "votes_up",
    "weighted_vote_score",
    "written_during_early_access",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: appreviews")
    add_common_probe_arguments(parser)
    parser.add_argument("--app-id", type=int, default=None)
    return parser


def summarize_review_entry(review: Any) -> Any:
    """Return a public-safe structural summary for one review row."""

    if not isinstance(review, dict):
        return review

    summary = {
        field: review[field]
        for field in REVIEW_EXCERPT_FIELDS
        if field in review
    }

    author = review.get("author")
    if isinstance(author, dict):
        summary["author_fields_present"] = sorted(author.keys())
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
    """Return a bounded public-safe summary for appreviews payloads."""

    if not isinstance(payload, dict):
        return payload

    summary: dict[str, Any] = {
        "top_level_keys": sorted(payload.keys()),
    }

    if "success" in payload:
        summary["success"] = payload["success"]

    query_summary = payload.get("query_summary")
    if isinstance(query_summary, dict):
        summary["query_summary"] = query_summary

    cursor = payload.get("cursor")
    if isinstance(cursor, str):
        summary["cursor_present"] = bool(cursor)

    reviews = payload.get("reviews")
    if isinstance(reviews, list):
        summary["reviews_count"] = len(reviews)
        summary["review_fields_present"] = sorted(
            {
                key
                for review in reviews
                if isinstance(review, dict)
                for key in review.keys()
            }
        )
        author_fields = sorted(
            {
                key
                for review in reviews
                if isinstance(review, dict)
                for author in [review.get("author")]
                if isinstance(author, dict)
                for key in author.keys()
            }
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
    request_params: dict[str, str | int],
) -> dict[str, Any]:
    """Build the persisted probe snapshot with a public-safe payload summary."""

    payload = decode_json_payload(result.body)
    if payload is None:
        payload_excerpt_or_json: Any = text_excerpt(result.body)
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
    request_url = REQUEST_URL_TEMPLATE.format(app_id=app_id)
    params: dict[str, str | int] = {
        "json": 1,
        "filter": "all",
        "language": "all",
        "purchase_type": "all",
        "num_per_page": 20,
    }

    result = request_with_retry(
        url=request_url,
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
        request_url=request_url,
        request_params=params,
    )
    output_path = save_snapshot(out_dir=runtime.out_dir, probe_name=PROBE_NAME, snapshot=snapshot)
    LOGGER.info("Saved %s snapshot to %s", PROBE_NAME, output_path)


if __name__ == "__main__":
    main()
