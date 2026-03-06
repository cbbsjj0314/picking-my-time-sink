"""Probe Steam app list endpoint and store a reproducible snapshot."""

from __future__ import annotations

import argparse
import logging

from steam.probe.common import (
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
REQUEST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: ISteamApps/GetAppList")
    add_common_probe_arguments(parser)
    return parser


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    runtime = runtime_config_from_args(args)

    result = request_with_retry(
        url=REQUEST_URL,
        params=None,
        timeout_seconds=runtime.timeout_seconds,
        max_attempts=runtime.max_attempts,
        backoff_base_seconds=runtime.backoff_base_seconds,
        jitter_max_seconds=runtime.jitter_max_seconds,
        max_backoff_seconds=runtime.max_backoff_seconds,
        logger=LOGGER,
    )

    payload = decode_json_payload(result.body)
    if payload is None:
        payload = text_excerpt(result.body)

    collected_at_utc = utc_now_iso()
    snapshot = build_snapshot(
        probe_name=PROBE_NAME,
        collected_at_utc=collected_at_utc,
        request_url=REQUEST_URL,
        request_params=None,
        timeout_seconds=runtime.timeout_seconds,
        result=result,
        payload_excerpt_or_json=payload,
    )
    output_path = save_snapshot(out_dir=runtime.out_dir, probe_name=PROBE_NAME, snapshot=snapshot)
    LOGGER.info("Saved %s snapshot to %s", PROBE_NAME, output_path)


if __name__ == "__main__":
    main()
