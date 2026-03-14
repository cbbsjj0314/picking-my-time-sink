"""Fetch the Steam app catalog with pagination, resume, and deterministic JSONL output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    summarize_attempts,
    utc_now_iso,
)
from steam.probe.common import (
    configure_logging,
    decode_json_payload,
    request_with_retry,
)
from steam.probe.probe_getapplist import (
    REQUEST_URL,
    build_request_params,
    parse_getapplist_page,
    resolve_steam_api_key,
)

LOGGER = logging.getLogger(__name__)
JOB_NAME = "fetch_app_catalog_weekly"
DEFAULT_CHECKPOINT_PATH = Path(
    "tmp/steam/app_catalog/checkpoints/fetch_app_catalog_weekly.state.json"
)
DEFAULT_SNAPSHOT_DIR = Path("tmp/steam/app_catalog/snapshots")


def _timestamp_slug(iso_utc: str) -> str:
    normalized = iso_utc.replace("Z", "+00:00") if iso_utc.endswith("Z") else iso_utc
    return dt.datetime.fromisoformat(normalized).strftime("%Y%m%dT%H%M%SZ")


def default_snapshot_path(started_at_utc: str) -> Path:
    """Return the default temporary JSONL snapshot path for one run."""

    return DEFAULT_SNAPSHOT_DIR / f"{_timestamp_slug(started_at_utc)}.jsonl"


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    """Load checkpoint JSON when present."""

    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid checkpoint file: {path}") from exc


def save_checkpoint(path: Path, state: Mapping[str, Any]) -> Path:
    """Persist checkpoint JSON with stable formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load deterministic JSONL rows from disk."""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                rows.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number} in {path}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write deterministic JSONL rows to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return path


def build_checkpoint(
    *,
    status: str,
    started_at_utc: str,
    snapshot_path: Path,
    last_appid: int | None,
) -> dict[str, Any]:
    """Build the minimal checkpoint payload for app catalog runs."""

    return {
        "job_name": JOB_NAME,
        "last_appid": last_appid,
        "snapshot_path": str(snapshot_path),
        "started_at_utc": started_at_utc,
        "status": status,
    }


def get_resume_state(
    *,
    checkpoint_path: Path,
    output_path: Path | None,
) -> tuple[str, Path, int | None, list[dict[str, Any]]]:
    """Return the run start state, resuming only from explicit in-progress checkpoints."""

    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint is not None and checkpoint.get("status") == "in_progress":
        snapshot_path = Path(str(checkpoint.get("snapshot_path", "")))
        if not snapshot_path.exists():
            raise ValueError(f"Checkpoint snapshot missing: {snapshot_path}")
        rows = load_jsonl(snapshot_path)
        last_appid = checkpoint.get("last_appid")
        return (
            str(checkpoint["started_at_utc"]),
            snapshot_path,
            int(last_appid) if last_appid is not None else None,
            rows,
        )

    started_at_utc = utc_now_iso()
    snapshot_path = output_path or default_snapshot_path(started_at_utc)
    write_jsonl(snapshot_path, [])
    save_checkpoint(
        checkpoint_path,
        build_checkpoint(
            status="in_progress",
            started_at_utc=started_at_utc,
            snapshot_path=snapshot_path,
            last_appid=None,
        ),
    )
    return started_at_utc, snapshot_path, None, []


def getapplist_response_retry_reason(status_code: int | None, body: bytes) -> str | None:
    """Return retry reasons for invalid paginated GetAppList responses."""

    del status_code

    if not body:
        return "empty_body"

    payload = decode_json_payload(body)
    if payload is None:
        return "invalid_json"

    try:
        parse_getapplist_page(payload)
    except ValueError as exc:
        return str(exc)

    return None


def normalize_app_catalog_rows(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize one GetAppList page to the temporary JSONL row shape."""

    rows: list[dict[str, Any]] = []
    for app in apps:
        rows.append(
            {
                "appid": int(app["appid"]),
                "last_modified": app.get("last_modified"),
                "name": app.get("name"),
                "price_change_number": app.get("price_change_number"),
            }
        )
    return rows


def merge_normalized_catalog_rows(
    existing_rows: list[dict[str, Any]],
    page_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge App Catalog rows by appid.

    Pages are expected to be non-overlapping by appid. If duplicates appear,
    later rows replace earlier rows, and the final output is sorted by appid.
    """

    merged = {int(row["appid"]): row for row in existing_rows}
    for row in page_rows:
        merged[int(row["appid"])] = row
    return [merged[appid] for appid in sorted(merged)]


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the weekly app catalog fetch runner."""

    parser = argparse.ArgumentParser(description="Fetch Steam App Catalog into temporary JSONL")
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-base-sec", type=float, default=0.5)
    parser.add_argument("--jitter-max-sec", type=float, default=0.3)
    parser.add_argument("--max-backoff-sec", type=float, default=8.0)
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def run(
    *,
    output_path: Path | None = None,
    checkpoint_path: Path | None = None,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
    max_results: int | None = None,
    meta_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Fetch the full Steam App Catalog into a resumable temporary JSONL snapshot."""

    resolved_checkpoint_path = checkpoint_path or DEFAULT_CHECKPOINT_PATH
    started_at_utc, resolved_snapshot_path, last_appid, rows = get_resume_state(
        checkpoint_path=resolved_checkpoint_path,
        output_path=output_path,
    )
    resolved_meta_path = meta_path or default_meta_path(
        job_name=JOB_NAME,
        started_at_utc=started_at_utc,
    )

    success = False
    http_status: int | None = None
    retry_count = 0
    timeout_count = 0
    rate_limit_count = 0
    records_in = len(rows)
    records_out = len(rows)
    error_type: str | None = None
    error_message: str | None = None
    attempt_summaries: list[dict[str, int]] = []

    try:
        api_key = resolve_steam_api_key()

        while True:
            request_params = build_request_params(
                api_key,
                last_appid=last_appid,
                max_results=max_results,
            )
            result = request_with_retry(
                url=REQUEST_URL,
                params=request_params,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                backoff_base_seconds=backoff_base_seconds,
                jitter_max_seconds=jitter_max_seconds,
                max_backoff_seconds=max_backoff_seconds,
                logger=LOGGER,
                response_retry_reason=getapplist_response_retry_reason,
            )
            http_status = result.status_code
            attempt_summaries.append(summarize_attempts(result.attempts))

            payload = decode_json_payload(result.body)
            if payload is None:
                raise RuntimeError("GetAppList returned non-JSON payload after retry exhaustion")

            page = parse_getapplist_page(payload)
            page_rows = normalize_app_catalog_rows(page["apps"])
            rows = merge_normalized_catalog_rows(rows, page_rows)
            write_jsonl(resolved_snapshot_path, rows)
            records_out = len(rows)

            if not page["have_more_results"]:
                save_checkpoint(
                    resolved_checkpoint_path,
                    build_checkpoint(
                        status="completed",
                        started_at_utc=started_at_utc,
                        snapshot_path=resolved_snapshot_path,
                        last_appid=None,
                    ),
                )
                break

            last_appid = page["last_appid"]
            save_checkpoint(
                resolved_checkpoint_path,
                build_checkpoint(
                    status="in_progress",
                    started_at_utc=started_at_utc,
                    snapshot_path=resolved_snapshot_path,
                    last_appid=last_appid,
                ),
            )

        aggregated = {
            "retry_count": sum(item["retry_count"] for item in attempt_summaries),
            "timeout_count": sum(item["timeout_count"] for item in attempt_summaries),
            "rate_limit_count": sum(item["rate_limit_count"] for item in attempt_summaries),
        }
        retry_count = aggregated["retry_count"]
        timeout_count = aggregated["timeout_count"]
        rate_limit_count = aggregated["rate_limit_count"]
        success = True
        return rows
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        finished_at_utc = utc_now_iso()
        execution_meta = build_execution_meta(
            job_name=JOB_NAME,
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
        save_execution_meta(execution_meta, resolved_meta_path)


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    run(
        output_path=args.output_path,
        checkpoint_path=args.checkpoint_path,
        timeout_seconds=args.timeout_sec,
        max_attempts=args.max_attempts,
        backoff_base_seconds=args.backoff_base_sec,
        jitter_max_seconds=args.jitter_max_sec,
        max_backoff_seconds=args.max_backoff_sec,
        max_results=args.max_results,
        meta_path=args.meta_path,
    )


if __name__ == "__main__":
    main()
