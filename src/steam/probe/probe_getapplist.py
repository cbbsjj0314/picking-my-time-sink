"""Probe Steam app list endpoint and store a reproducible snapshot."""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from steam.probe.common import (
    RequestResult,
    add_common_probe_arguments,
    build_snapshot,
    configure_logging,
    decode_json_payload,
    request_with_retry,
    runtime_config_from_args,
    save_snapshot,
    text_excerpt,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)
PROBE_NAME = "getapplist"
REQUEST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
REDACTED_VALUE = "***redacted***"
APP_EXCERPT_COUNT = 5
PAGINATION_FIELDS = (
    "cursor",
    "have_more_results",
    "last_appid",
    "limit",
    "max_results",
    "next_cursor",
    "offset",
    "page_count",
    "page_size",
    "page_start",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: IStoreService/GetAppList")
    add_common_probe_arguments(parser)
    return parser


def resolve_steam_api_key() -> str:
    """Return the Steam Web API key required for the official catalog endpoint."""

    api_key = os.getenv("STEAM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("STEAM_API_KEY is required for IStoreService/GetAppList")
    return api_key


def build_request_params(api_key: str) -> dict[str, str]:
    """Build live request params for the catalog probe."""

    return {"key": api_key}


def redact_request_params(params: dict[str, str]) -> dict[str, str]:
    """Return snapshot-safe params without exposing secrets."""

    return {
        key: REDACTED_VALUE if key.lower() == "key" else value
        for key, value in params.items()
    }


def summarize_getapplist_payload(
    payload: Any,
    *,
    excerpt_count: int = APP_EXCERPT_COUNT,
) -> Any:
    """Return a deterministic probe-sized summary for GetAppList payloads."""

    if not isinstance(payload, dict):
        return payload

    response = payload.get("response")
    if not isinstance(response, dict):
        return payload

    summary: dict[str, Any] = {
        "top_level_keys": sorted(response.keys()),
    }

    app_count = response.get("app_count")
    apps = response.get("apps")
    if isinstance(app_count, int):
        summary["app_count"] = app_count
    elif isinstance(apps, list):
        summary["app_count"] = len(apps)

    pagination = {field: response[field] for field in PAGINATION_FIELDS if field in response}
    if pagination:
        summary["pagination"] = pagination

    if isinstance(apps, list):
        summary["apps_excerpt"] = apps[:excerpt_count]

    return summary


def build_probe_snapshot(
    *,
    result: RequestResult,
    timeout_seconds: float,
    request_params: dict[str, str],
) -> dict[str, Any]:
    """Build the persisted snapshot with redacted params and summarized payload."""

    payload = decode_json_payload(result.body)
    if payload is None:
        payload_excerpt_or_json: Any = text_excerpt(result.body)
    else:
        payload_excerpt_or_json = summarize_getapplist_payload(payload)

    return build_snapshot(
        include_collected_at_kst=True,
        probe_name=PROBE_NAME,
        collected_at_utc=utc_now_iso(),
        request_url=REQUEST_URL,
        request_params=redact_request_params(request_params),
        timeout_seconds=timeout_seconds,
        result=result,
        payload_excerpt_or_json=payload_excerpt_or_json,
    )


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    runtime = runtime_config_from_args(args)
    request_params = build_request_params(resolve_steam_api_key())

    result = request_with_retry(
        url=REQUEST_URL,
        params=request_params,
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
        request_params=request_params,
    )
    output_path = save_snapshot(out_dir=runtime.out_dir, probe_name=PROBE_NAME, snapshot=snapshot)
    LOGGER.info("Saved %s snapshot to %s", PROBE_NAME, output_path)


if __name__ == "__main__":
    main()
