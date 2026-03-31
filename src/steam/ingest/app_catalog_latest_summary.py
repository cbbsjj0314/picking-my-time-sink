"""Helpers for the App Catalog runtime latest summary handoff artifact."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from steam.probe.probe_getapplist import summarize_getapplist_payload

DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH = Path("tmp/steam/app_catalog/latest.summary.json")
LATEST_SUMMARY_SCHEMA_VERSION = "1.0"


def build_latest_summary(
    *,
    job_name: str,
    started_at_utc: str,
    finished_at_utc: str,
    snapshot_path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the runtime latest summary contract from completed JSONL rows."""

    payload_excerpt_or_json = summarize_getapplist_payload(
        {
            "response": {
                "apps": rows,
                "have_more_results": False,
            }
        }
    )
    if not isinstance(payload_excerpt_or_json, dict):
        raise ValueError("payload_excerpt_or_json is not an object")

    return {
        "finished_at_utc": finished_at_utc,
        "job_name": job_name,
        "response": {
            "payload_excerpt_or_json": payload_excerpt_or_json,
        },
        "schema_version": LATEST_SUMMARY_SCHEMA_VERSION,
        "snapshot_path": str(snapshot_path),
        "started_at_utc": started_at_utc,
        "status": "completed",
    }


def write_latest_summary(path: Path, summary: Mapping[str, Any]) -> Path:
    """Persist the runtime latest summary with stable JSON formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path


def extract_catalog_metadata(payload: Any) -> dict[str, Any]:
    """Extract optional App Catalog metadata from the handoff artifact shape."""

    if not isinstance(payload, dict):
        raise ValueError("summary payload is not an object")

    response = payload.get("response")
    if not isinstance(response, dict):
        raise ValueError("response is not an object")

    excerpt = response.get("payload_excerpt_or_json")
    if not isinstance(excerpt, dict):
        raise ValueError("payload_excerpt_or_json is not an object")

    top_level_keys = excerpt.get("top_level_keys")
    pagination = excerpt.get("pagination")
    app_count = excerpt.get("app_count")
    snapshot_path = payload.get("snapshot_path")

    if top_level_keys is not None and not isinstance(top_level_keys, list):
        raise ValueError("top_level_keys is not a list")
    if pagination is not None and not isinstance(pagination, dict):
        raise ValueError("pagination is not an object")

    return {
        "app_count": int(app_count) if isinstance(app_count, int) else None,
        "pagination": pagination if isinstance(pagination, dict) else {},
        "snapshot_path": str(snapshot_path) if isinstance(snapshot_path, str) else None,
        "top_level_keys": top_level_keys if isinstance(top_level_keys, list) else [],
    }
