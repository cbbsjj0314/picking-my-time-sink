"""Probe Steam CCU endpoint and store a reproducible snapshot."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    summarize_attempts,
)
from steam.common.execution_meta import (
    utc_now_iso as meta_utc_now_iso,
)
from steam.probe.common import (
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
PROBE_NAME = "ccu"
REQUEST_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
CCU_RETRYABLE_STATUS_CODES = frozenset({404, 429, 500, 502, 503, 504})


def ccu_response_retry_reason(status_code: int | None, body: bytes) -> str | None:
    """Return a retry reason for abnormal CCU payloads."""

    del status_code

    if not body:
        return "empty_body"

    payload = decode_json_payload(body)
    if payload is None:
        return "invalid_json"

    if not isinstance(payload, dict):
        return "missing_player_count"

    response = payload.get("response")
    if not isinstance(response, dict):
        return "missing_player_count"

    try:
        player_count = int(response.get("player_count"))
    except (TypeError, ValueError):
        return "missing_player_count"

    return None if player_count >= 0 else "missing_player_count"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: GetNumberOfCurrentPlayers")
    add_common_probe_arguments(parser)
    parser.add_argument("--app-id", type=int, default=None)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    runtime = runtime_config_from_args(args)
    started_at_utc = meta_utc_now_iso()
    meta_path = args.meta_path or default_meta_path(
        job_name="probe_ccu",
        started_at_utc=started_at_utc,
    )

    success = False
    http_status: int | None = None
    retry_count = 0
    timeout_count = 0
    rate_limit_count = 0
    records_in = 1
    records_out = 0
    error_type: str | None = None
    error_message: str | None = None

    try:
        app_id = resolve_app_id(args.app_id)
        params: dict[str, str | int] = {"appid": app_id}

        steam_api_key = os.getenv("STEAM_API_KEY")
        if steam_api_key:
            params["key"] = steam_api_key

        result = request_with_retry(
            url=REQUEST_URL,
            params=params,
            timeout_seconds=runtime.timeout_seconds,
            max_attempts=runtime.max_attempts,
            backoff_base_seconds=runtime.backoff_base_seconds,
            jitter_max_seconds=runtime.jitter_max_seconds,
            max_backoff_seconds=runtime.max_backoff_seconds,
            logger=LOGGER,
            retryable_status_codes=CCU_RETRYABLE_STATUS_CODES,
            response_retry_reason=ccu_response_retry_reason,
        )

        payload = decode_json_payload(result.body)
        if payload is None:
            payload = text_excerpt(result.body)

        collected_at_utc = utc_now_iso()
        snapshot = build_snapshot(
            probe_name=PROBE_NAME,
            collected_at_utc=collected_at_utc,
            request_url=REQUEST_URL,
            request_params=params,
            timeout_seconds=runtime.timeout_seconds,
            result=result,
            payload_excerpt_or_json=payload,
        )
        output_path = save_snapshot(
            out_dir=runtime.out_dir,
            probe_name=PROBE_NAME,
            snapshot=snapshot,
        )
        LOGGER.info("Saved %s snapshot to %s", PROBE_NAME, output_path)

        attempt_stats = summarize_attempts(result.attempts)
        retry_count = attempt_stats["retry_count"]
        timeout_count = attempt_stats["timeout_count"]
        rate_limit_count = attempt_stats["rate_limit_count"]
        http_status = result.status_code
        records_out = 1 if result.status_code is not None and result.status_code < 400 else 0
        success = result.error is None and records_out == 1
        if result.error is not None:
            error_type = result.error.get("type")
            error_message = result.error.get("message")
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        finished_at_utc = meta_utc_now_iso()
        execution_meta = build_execution_meta(
            job_name="probe_ccu",
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            success=success,
            http_status=http_status,
            retry_count=retry_count,
            timeout_count=timeout_count,
            rate_limit_count=rate_limit_count,
            records_in=records_in,
            records_out=records_out,
            error_type=error_type,
            error_message=error_message,
        )
        saved_meta_path = save_execution_meta(execution_meta, meta_path)
        LOGGER.info("Saved %s execution meta to %s", PROBE_NAME, saved_meta_path)


if __name__ == "__main__":
    main()
