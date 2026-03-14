"""Execution metadata helpers for probe/ingest reliability baselines."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """Return UTC timestamp in a stable ISO format."""

    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> dt.datetime:
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _timestamp_slug(iso_utc: str) -> str:
    return _parse_iso_utc(iso_utc).strftime("%Y%m%dT%H%M%SZ")


def summarize_attempts(attempts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Summarize retry/timeout/429 counts from attempt logs."""

    retry_count = max(len(attempts) - 1, 0)
    timeout_count = 0
    rate_limit_count = 0

    for attempt in attempts:
        status_code = attempt.get("status_code")
        if status_code == 429:
            rate_limit_count += 1

        error_text = str(attempt.get("error") or "").lower()
        if "timeout" in error_text or "timed out" in error_text:
            timeout_count += 1

    return {
        "retry_count": retry_count,
        "timeout_count": timeout_count,
        "rate_limit_count": rate_limit_count,
    }


def sum_attempt_stats(stats: Sequence[Mapping[str, int]]) -> dict[str, int]:
    """Sum attempt summary dictionaries into one aggregate."""

    return {
        "retry_count": sum(int(item.get("retry_count", 0)) for item in stats),
        "timeout_count": sum(int(item.get("timeout_count", 0)) for item in stats),
        "rate_limit_count": sum(int(item.get("rate_limit_count", 0)) for item in stats),
    }


def build_execution_meta(
    *,
    job_name: str,
    started_at_utc: str,
    finished_at_utc: str,
    success: bool,
    http_status: int | None,
    retry_count: int,
    timeout_count: int,
    rate_limit_count: int,
    records_in: int,
    records_out: int,
    error_type: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    """Build one execution metadata payload with fixed baseline fields."""

    started_at = _parse_iso_utc(started_at_utc)
    finished_at = _parse_iso_utc(finished_at_utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    return {
        "job_name": job_name,
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "duration_ms": duration_ms,
        "success": success,
        "http_status": http_status,
        "retry_count": retry_count,
        "timeout_count": timeout_count,
        "rate_limit_count": rate_limit_count,
        "records_in": records_in,
        "records_out": records_out,
        "error_type": error_type,
        "error_message": error_message,
    }


def default_meta_path(*, job_name: str, started_at_utc: str, base_dir: Path | None = None) -> Path:
    """Return default local metadata output path under tmp/..."""

    resolved_base_dir = base_dir or Path("tmp/steam/run-meta")
    return resolved_base_dir / job_name / f"{_timestamp_slug(started_at_utc)}.meta.json"


def save_execution_meta(meta: Mapping[str, Any], path: Path) -> Path:
    """Persist execution metadata JSON to a local path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path
