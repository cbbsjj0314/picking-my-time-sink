"""Probe Steam reviews endpoint and store a reproducible snapshot."""

from __future__ import annotations

import argparse
import logging

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
PROBE_NAME = "reviews"
REQUEST_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{app_id}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: appreviews")
    add_common_probe_arguments(parser)
    parser.add_argument("--app-id", type=int, default=None)
    return parser


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

    payload = decode_json_payload(result.body)
    if payload is None:
        payload = text_excerpt(result.body)

    collected_at_utc = utc_now_iso()
    snapshot = build_snapshot(
        probe_name=PROBE_NAME,
        collected_at_utc=collected_at_utc,
        request_url=request_url,
        request_params=params,
        timeout_seconds=runtime.timeout_seconds,
        result=result,
        payload_excerpt_or_json=payload,
    )
    output_path = save_snapshot(out_dir=runtime.out_dir, probe_name=PROBE_NAME, snapshot=snapshot)
    LOGGER.info("Saved %s snapshot to %s", PROBE_NAME, output_path)


if __name__ == "__main__":
    main()
