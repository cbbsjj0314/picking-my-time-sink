"""Shared helpers for Steam endpoint probes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "1.0"
SELECTED_RESPONSE_HEADERS = (
    "date",
    "content-type",
    "cache-control",
    "etag",
    "last-modified",
    "retry-after",
    "content-length",
)


@dataclass(slots=True)
class RequestResult:
    """HTTP result that keeps the full retry trail for probe snapshots."""

    final_url: str
    status_code: int | None
    headers: dict[str, str]
    body: bytes
    attempts: list[dict[str, Any]]
    error: dict[str, str] | None


@dataclass(slots=True)
class ProbeRuntimeConfig:
    """Runtime knobs shared by all probe scripts."""

    out_dir: Path
    timeout_seconds: float
    max_attempts: int
    backoff_base_seconds: float
    jitter_max_seconds: float
    max_backoff_seconds: float


def configure_logging(level: int = logging.INFO) -> None:
    """Set a compact log format for probe execution."""

    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def add_common_probe_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared CLI arguments used by every probe."""

    parser.add_argument("--out-dir", type=Path, default=Path("docs/probe/steam"))
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-base-sec", type=float, default=0.5)
    parser.add_argument("--jitter-max-sec", type=float, default=0.3)
    parser.add_argument("--max-backoff-sec", type=float, default=8.0)


def runtime_config_from_args(args: argparse.Namespace) -> ProbeRuntimeConfig:
    """Translate parsed arguments into a validated runtime config."""

    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be >= 1")

    return ProbeRuntimeConfig(
        out_dir=args.out_dir,
        timeout_seconds=args.timeout_sec,
        max_attempts=args.max_attempts,
        backoff_base_seconds=args.backoff_base_sec,
        jitter_max_seconds=args.jitter_max_sec,
        max_backoff_seconds=args.max_backoff_sec,
    )


def resolve_app_id(cli_app_id: int | None) -> int:
    """Resolve target app id from CLI first, then environment fallback."""

    if cli_app_id is not None:
        return cli_app_id

    raw_value = os.getenv("STEAM_PROBE_APP_ID", "730")
    try:
        return int(raw_value)
    except ValueError as exc:
        raise SystemExit("STEAM_PROBE_APP_ID must be an integer") from exc


def utc_now_iso() -> str:
    """Return UTC timestamp in an ISO format safe for snapshots."""

    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_to_file_timestamp(iso_value: str) -> str:
    normalized = iso_value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    return parsed.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def compute_backoff_seconds(
    *,
    attempt: int,
    base_seconds: float,
    jitter_max_seconds: float,
    max_seconds: float,
) -> float:
    """Return exponential backoff with jitter and a hard upper bound."""

    exponential = base_seconds * (2 ** max(attempt - 1, 0))
    jitter = random.uniform(0.0, max(jitter_max_seconds, 0.0))
    return min(exponential + jitter, max_seconds)


def _normalized_params(params: Mapping[str, str | int | float] | None) -> dict[str, str]:
    if params is None:
        return {}
    return {key: str(value) for key, value in params.items()}


def _build_final_url(url: str, params: Mapping[str, str]) -> str:
    if not params:
        return url

    query = urllib.parse.urlencode(params)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def request_with_retry(
    *,
    url: str,
    params: Mapping[str, str | int | float] | None,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
    logger: logging.Logger | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> RequestResult:
    """Send a GET request and capture retries, failures, and response metadata."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    log = logger or LOGGER
    normalized_params = _normalized_params(params)
    final_url = _build_final_url(url, normalized_params)

    headers = {
        "Accept": "*/*",
        "User-Agent": "steam-probe-mvp/0.1",
    }
    if extra_headers:
        headers.update(extra_headers)

    attempts: list[dict[str, Any]] = []
    last_status_code: int | None = None
    last_headers: dict[str, str] = {}
    last_body = b""
    last_error: dict[str, str] | None = None

    for attempt in range(1, max_attempts + 1):
        attempt_log: dict[str, Any] = {
            "attempt": attempt,
            "error": None,
            "sleep_seconds": 0.0,
            "status_code": None,
        }
        retryable = False

        request = urllib.request.Request(final_url, method="GET", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read()
                status_code = response.getcode()
                response_headers = dict(response.headers.items())

            attempt_log["status_code"] = status_code
            attempts.append(attempt_log)

            if not body:
                log.warning("Empty response body from %s (status=%s)", final_url, status_code)

            return RequestResult(
                final_url=final_url,
                status_code=status_code,
                headers=response_headers,
                body=body,
                attempts=attempts,
                error=None,
            )

        except urllib.error.HTTPError as exc:
            status_code = exc.code
            response_headers = dict(exc.headers.items()) if exc.headers is not None else {}
            body = exc.read()

            attempt_log["status_code"] = status_code
            attempt_log["error"] = f"HTTP {status_code}"
            retryable = status_code == 429 or status_code >= 500

            if status_code == 429:
                log.warning("Received HTTP 429 from %s (attempt=%s)", final_url, attempt)
            if not body:
                log.warning("Empty response body from %s (status=%s)", final_url, status_code)

            last_status_code = status_code
            last_headers = response_headers
            last_body = body
            last_error = {
                "type": "http_error",
                "message": f"HTTP {status_code}",
            }

        except urllib.error.URLError as exc:
            reason = exc.reason
            message = str(reason)

            attempt_log["error"] = message or "url_error"
            retryable = True

            reason_text = message.lower()
            if isinstance(reason, TimeoutError) or "timed out" in reason_text:
                log.warning("Request timeout for %s (attempt=%s)", final_url, attempt)
                error_type = "timeout"
            else:
                error_type = "url_error"

            last_error = {
                "type": error_type,
                "message": message or "URL error",
            }

        except TimeoutError as exc:
            message = str(exc) or "timeout"
            attempt_log["error"] = message
            retryable = True
            log.warning("Request timeout for %s (attempt=%s)", final_url, attempt)

            last_error = {
                "type": "timeout",
                "message": message,
            }

        if retryable and attempt < max_attempts:
            sleep_seconds = compute_backoff_seconds(
                attempt=attempt,
                base_seconds=backoff_base_seconds,
                jitter_max_seconds=jitter_max_seconds,
                max_seconds=max_backoff_seconds,
            )
            attempt_log["sleep_seconds"] = round(sleep_seconds, 3)
            attempts.append(attempt_log)
            time.sleep(sleep_seconds)
            continue

        attempts.append(attempt_log)
        return RequestResult(
            final_url=final_url,
            status_code=last_status_code,
            headers=last_headers,
            body=last_body,
            attempts=attempts,
            error=last_error,
        )

    return RequestResult(
        final_url=final_url,
        status_code=last_status_code,
        headers=last_headers,
        body=last_body,
        attempts=attempts,
        error=last_error,
    )


def selected_headers(headers: Mapping[str, str]) -> dict[str, str | None]:
    """Return only the response headers we want to persist for probes."""

    by_lower = {key.lower(): value for key, value in headers.items()}
    return {name: by_lower.get(name) for name in SELECTED_RESPONSE_HEADERS}


def decode_json_payload(body: bytes) -> Any | None:
    """Decode UTF-8 JSON body when possible."""

    if not body:
        return None

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def text_excerpt(body: bytes, max_chars: int = 4000) -> str | None:
    """Decode body as text and return a bounded excerpt."""

    if not body:
        return None

    text = body.decode("utf-8", errors="replace")
    return text[:max_chars]


def build_snapshot(
    *,
    probe_name: str,
    collected_at_utc: str,
    request_url: str,
    request_params: Mapping[str, str | int | float] | None,
    timeout_seconds: float,
    result: RequestResult,
    payload_excerpt_or_json: Any,
) -> dict[str, Any]:
    """Create deterministic snapshot payload shared by all probes."""

    normalized_params = _normalized_params(request_params)

    return {
        "schema_version": SCHEMA_VERSION,
        "probe_name": probe_name,
        "collected_at_utc": collected_at_utc,
        "request": {
            "method": "GET",
            "params": normalized_params,
            "timeout_seconds": timeout_seconds,
            "url": request_url,
        },
        "response": {
            "body_sha256": hashlib.sha256(result.body).hexdigest(),
            "body_size": len(result.body),
            "is_empty": len(result.body) == 0,
            "payload_excerpt_or_json": payload_excerpt_or_json,
            "selected_headers": selected_headers(result.headers),
            "status_code": result.status_code,
        },
        "attempts": result.attempts,
        "error": result.error,
    }


def save_snapshot(*, out_dir: Path, probe_name: str, snapshot: Mapping[str, Any]) -> Path:
    """Save snapshot JSON under docs/probe/steam/<probe_name>/ with stable formatting."""

    probe_dir = out_dir / probe_name
    probe_dir.mkdir(parents=True, exist_ok=True)

    collected_at_utc = str(snapshot.get("collected_at_utc", utc_now_iso()))
    timestamp = _iso_to_file_timestamp(collected_at_utc)
    output_path = probe_dir / f"{timestamp}.json"

    suffix = 1
    while output_path.exists():
        output_path = probe_dir / f"{timestamp}_{suffix:02d}.json"
        suffix += 1

    snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    output_path.write_text(f"{snapshot_text}\n", encoding="utf-8")
    return output_path
