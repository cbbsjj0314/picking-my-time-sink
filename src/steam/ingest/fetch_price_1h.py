"""Fetch Steam KR price payloads for tracked games and write bronze JSONL."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    sum_attempt_stats,
    summarize_attempts,
    utc_now_iso,
)
from steam.probe.common import (
    RequestResult,
    compute_backoff_seconds,
    decode_json_payload,
    request_with_retry,
)

LOGGER = logging.getLogger(__name__)
REQUEST_URL = "https://store.steampowered.com/api/appdetails"
REQUEST_PARAMS_BASE = {
    "cc": "kr",
    "filters": "price_overview",
    "l": "koreana",
}
FALLBACK_REQUEST_PARAMS_BASE = {
    "cc": "kr",
    "l": "koreana",
}
DEFAULT_BATCH_SIZE = 100
DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 1.5
DEFAULT_MAX_RETRY_AFTER_SECONDS = 60.0
DEFAULT_TIME_BUDGET_SECONDS = 1500.0

FAILURE_RATE_LIMITED = "rate_limited"
FAILURE_SERVER_ERROR = "server_error"
FAILURE_HTTP_ERROR = "http_error"
FAILURE_TIMEOUT = "timeout"
FAILURE_NETWORK_ERROR = "network_error"
FAILURE_INVALID_JSON = "invalid_json"
FAILURE_MISSING_KEY = "missing_key"
FAILURE_TIME_BUDGET_EXCEEDED = "time_budget_exceeded"


def configure_logging() -> None:
    """Use a compact logger format for ingest scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def require_psycopg() -> Any:
    """Import psycopg and fail fast when dependency is missing."""

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for Steam price ingest") from exc
    return psycopg


def get_required_env(name: str) -> str:
    """Read required environment variable or raise clear error."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_pg_conninfo_from_env() -> str:
    """Build Postgres conninfo from environment variables."""

    host = get_required_env("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = get_required_env("POSTGRES_DB")
    user = get_required_env("POSTGRES_USER")
    password = get_required_env("POSTGRES_PASSWORD")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def load_tracked_steam_games(conn: Any) -> list[dict[str, int]]:
    """Load active tracked games and their Steam app ids."""

    query = """
        SELECT
            tg.canonical_game_id,
            gei.external_id AS steam_appid
        FROM tracked_game AS tg
        INNER JOIN game_external_id AS gei
            ON gei.canonical_game_id = tg.canonical_game_id
           AND gei.source = 'steam'
        WHERE tg.is_active = TRUE
        ORDER BY tg.priority, tg.canonical_game_id
    """

    targets: list[dict[str, int]] = []
    with conn.cursor() as cursor:
        cursor.execute(query)
        for canonical_game_id, steam_appid_raw in cursor.fetchall():
            try:
                steam_appid = int(steam_appid_raw)
            except (TypeError, ValueError):
                LOGGER.warning(
                    "Skipping invalid steam_appid for canonical_game_id=%s: %s",
                    canonical_game_id,
                    steam_appid_raw,
                )
                continue

            targets.append(
                {
                    "canonical_game_id": int(canonical_game_id),
                    "steam_appid": steam_appid,
                }
            )

    return targets


def build_appdetails_result(
    *,
    steam_appid: int,
    request_params_base: dict[str, str],
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
) -> dict[str, Any]:
    """Fetch one appdetails payload and preserve request provenance."""

    params: dict[str, str | int] = {
        "appids": steam_appid,
        **request_params_base,
    }
    result = request_with_retry(
        url=REQUEST_URL,
        params=params,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        jitter_max_seconds=jitter_max_seconds,
        max_backoff_seconds=max_backoff_seconds,
        logger=LOGGER,
    )

    return {
        "attempts": result.attempts,
        "attempt_stats": summarize_attempts(result.attempts),
        "error": result.error,
        "payload": decode_json_payload(result.body),
        "request": {
            "params": params,
            "url": REQUEST_URL,
        },
        "status_code": result.status_code,
    }


def has_successful_appdetails_without_price_overview(
    payload: Any,
    *,
    steam_appid: int,
) -> bool:
    """Return true when filtered appdetails succeeded without loadable price_overview."""

    if not isinstance(payload, dict):
        return False

    app_payload = payload.get(str(steam_appid))
    if not isinstance(app_payload, dict):
        return False
    if app_payload.get("success") is not True:
        return False

    data = app_payload.get("data")
    if not isinstance(data, dict):
        return True

    return not isinstance(data.get("price_overview"), dict)


def should_fetch_full_appdetails_fallback(
    primary_result: dict[str, Any],
    *,
    steam_appid: int,
) -> bool:
    """Decide whether a no-filter fallback can add grounded free-title evidence."""

    if primary_result.get("error") is not None:
        return False
    if primary_result.get("status_code") != 200:
        return False

    return has_successful_appdetails_without_price_overview(
        primary_result.get("payload"),
        steam_appid=steam_appid,
    )


def fetch_price_for_app(
    *,
    steam_appid: int,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
) -> dict[str, Any]:
    """Fetch one app's KR price payload using shared retry defaults only."""

    primary_result = build_appdetails_result(
        steam_appid=steam_appid,
        request_params_base=REQUEST_PARAMS_BASE,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        jitter_max_seconds=jitter_max_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )

    fallback_result: dict[str, Any] | None = None
    if should_fetch_full_appdetails_fallback(primary_result, steam_appid=steam_appid):
        fallback_result = build_appdetails_result(
            steam_appid=steam_appid,
            request_params_base=FALLBACK_REQUEST_PARAMS_BASE,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            backoff_base_seconds=backoff_base_seconds,
            jitter_max_seconds=jitter_max_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )

    attempt_stats = [primary_result["attempt_stats"]]
    if fallback_result is not None:
        attempt_stats.append(fallback_result["attempt_stats"])

    return {
        "attempts": primary_result["attempts"],
        "attempt_stats": sum_attempt_stats(attempt_stats),
        "error": primary_result["error"],
        "fallback": fallback_result,
        "payload": primary_result["payload"],
        "primary": primary_result,
        "status_code": primary_result["status_code"],
    }


@dataclass(slots=True)
class RequestClock:
    """Injectable clock so pacing and the time budget are testable without sleeping."""

    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


def parse_retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Return a delta-seconds Retry-After value, or None when absent or unusable."""

    for name, value in headers.items():
        if name.lower() != "retry-after":
            continue
        try:
            seconds = float(str(value).strip())
        except ValueError:
            return None
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return seconds
    return None


def is_retryable_result(result: RequestResult) -> bool:
    """Match the shared retry rule: 429, 5xx, timeout, and network errors."""

    if result.error is None:
        return False
    status_code = result.status_code
    if status_code == 429 or (status_code is not None and status_code >= 500):
        return True
    return result.error.get("type") in {"timeout", "url_error"}


def build_time_budget_result(params: Mapping[str, Any]) -> dict[str, Any]:
    """Describe a request that was not sent because the fetch time budget ran out."""

    return {
        "attempts": [],
        "attempt_stats": summarize_attempts([]),
        "error": {
            "type": FAILURE_TIME_BUDGET_EXCEEDED,
            "message": "fetch time budget exceeded before request",
        },
        "payload": None,
        "request": {"params": dict(params), "url": REQUEST_URL},
        "status_code": None,
    }


class PriceRequestSession:
    """Send price-job Steam requests with pacing, Retry-After, and a total time budget.

    The shared request_with_retry helper is called with max_attempts=1 so that every
    attempt, including retries, passes through the same minimum interval and deadline.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_attempts: int,
        backoff_base_seconds: float,
        jitter_max_seconds: float,
        max_backoff_seconds: float,
        min_request_interval_seconds: float,
        max_retry_after_seconds: float,
        time_budget_seconds: float,
        clock: RequestClock | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self.jitter_max_seconds = jitter_max_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.min_request_interval_seconds = max(min_request_interval_seconds, 0.0)
        self.max_retry_after_seconds = max(max_retry_after_seconds, 0.0)
        self.clock = clock or RequestClock()

        started_at = self.clock.monotonic()
        self.deadline = started_at + max(time_budget_seconds, 0.0)
        self.next_request_at = started_at
        self.request_count = 0
        self.attempt_stats: list[dict[str, int]] = []
        self.time_budget_exceeded = False

    def _wait_for_turn(self) -> bool:
        now = self.clock.monotonic()
        start_at = max(now, self.next_request_at)
        if start_at > self.deadline:
            self.time_budget_exceeded = True
            return False
        if start_at > now:
            self.clock.sleep(start_at - now)
        return True

    def _retry_delay_seconds(self, result: RequestResult, *, attempt: int) -> float:
        if result.status_code == 429:
            retry_after = parse_retry_after_seconds(result.headers)
            if retry_after is not None:
                return min(retry_after, self.max_retry_after_seconds)
        return compute_backoff_seconds(
            attempt=attempt,
            base_seconds=self.backoff_base_seconds,
            jitter_max_seconds=self.jitter_max_seconds,
            max_seconds=self.max_backoff_seconds,
        )

    def get(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Fetch one appdetails request and return the bronze request-result shape."""

        attempts: list[dict[str, Any]] = []
        result: RequestResult | None = None

        for attempt in range(1, self.max_attempts + 1):
            if not self._wait_for_turn():
                if attempts:
                    attempts[-1]["sleep_seconds"] = 0.0
                break

            result = request_with_retry(
                url=REQUEST_URL,
                params=params,
                timeout_seconds=self.timeout_seconds,
                max_attempts=1,
                backoff_base_seconds=self.backoff_base_seconds,
                jitter_max_seconds=self.jitter_max_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                logger=LOGGER,
            )
            finished_at = self.clock.monotonic()
            self.request_count += 1
            self.next_request_at = finished_at + self.min_request_interval_seconds

            attempt_log = {
                "error": None,
                **(result.attempts[-1] if result.attempts else {}),
                "attempt": attempt,
                "sleep_seconds": 0.0,
                "status_code": result.status_code,
            }
            attempts.append(attempt_log)

            if not is_retryable_result(result) or attempt >= self.max_attempts:
                break

            retry_at = finished_at + self._retry_delay_seconds(result, attempt=attempt)
            self.next_request_at = max(self.next_request_at, retry_at)
            attempt_log["sleep_seconds"] = round(self.next_request_at - finished_at, 3)

        if result is None:
            budget_result = build_time_budget_result(params)
            self.attempt_stats.append(budget_result["attempt_stats"])
            return budget_result

        attempt_stats = summarize_attempts(attempts)
        self.attempt_stats.append(attempt_stats)
        return {
            "attempts": attempts,
            "attempt_stats": attempt_stats,
            "error": result.error,
            "payload": decode_json_payload(result.body),
            "request": {"params": dict(params), "url": REQUEST_URL},
            "status_code": result.status_code,
        }


def classify_fetch_failure(result: Mapping[str, Any], *, steam_appid: int) -> str | None:
    """Return why a request result holds no app-level Steam answer, or None when it does.

    `success:false`, `is_free=false`, and missing `price_overview` are Steam answers,
    so they are not fetch failures.
    """

    error = result.get("error")
    status_code = result.get("status_code")
    if error is not None:
        error_type = error.get("type") if isinstance(error, Mapping) else None
        if error_type == FAILURE_TIME_BUDGET_EXCEEDED:
            return FAILURE_TIME_BUDGET_EXCEEDED
        if error_type == "timeout":
            return FAILURE_TIMEOUT
        if error_type == "url_error":
            return FAILURE_NETWORK_ERROR
        if status_code == 429:
            return FAILURE_RATE_LIMITED
        if isinstance(status_code, int) and status_code >= 500:
            return FAILURE_SERVER_ERROR
        return FAILURE_HTTP_ERROR
    if status_code != 200:
        return FAILURE_HTTP_ERROR

    payload = result.get("payload")
    if not isinstance(payload, dict):
        return FAILURE_INVALID_JSON
    if not isinstance(payload.get(str(steam_appid)), dict):
        return FAILURE_MISSING_KEY
    return None


def split_batch_result(batch_result: Mapping[str, Any], *, steam_appid: int) -> dict[str, Any]:
    """Keep the batch request provenance but only this app's slice of the payload."""

    payload = batch_result.get("payload")
    app_key = str(steam_appid)
    app_payload = payload.get(app_key) if isinstance(payload, dict) else None
    return {
        **batch_result,
        "payload": {app_key: app_payload} if isinstance(app_payload, dict) else None,
    }


@dataclass(slots=True)
class AppFetchState:
    """Per-app evidence collected across the batch, supplement, and re-collect passes."""

    steam_appid: int
    collected_at: str | None = None
    primary: dict[str, Any] | None = None
    primary_reason: str | None = None
    fallback: dict[str, Any] | None = None
    fallback_reason: str | None = None
    trail: list[dict[str, Any]] = field(default_factory=list)

    def primary_failure(self) -> str | None:
        if self.primary is None:
            return FAILURE_TIME_BUDGET_EXCEEDED
        return self.primary_reason

    def needs_fallback(self) -> bool:
        return (
            self.primary is not None
            and self.primary_reason is None
            and should_fetch_full_appdetails_fallback(self.primary, steam_appid=self.steam_appid)
        )

    def fallback_failure(self) -> str | None:
        if not self.needs_fallback():
            return None
        if self.fallback is None:
            return FAILURE_TIME_BUDGET_EXCEEDED
        return self.fallback_reason

    def fetch_failure(self) -> dict[str, str] | None:
        primary_failure = self.primary_failure()
        if primary_failure is not None:
            return {"reason": primary_failure, "stage": "primary"}
        fallback_failure = self.fallback_failure()
        if fallback_failure is not None:
            return {"reason": fallback_failure, "stage": "fallback"}
        return None

    def apply(
        self,
        *,
        step: str,
        fetch_pass: str,
        result: dict[str, Any],
        collected_at: str | None = None,
    ) -> None:
        """Record one request outcome and keep it unless it was a budget skip over real evidence."""

        reason = classify_fetch_failure(result, steam_appid=self.steam_appid)
        self.trail.append(
            {
                "outcome": reason or "ok",
                "pass": fetch_pass,
                "status_code": result.get("status_code"),
                "step": step,
            }
        )
        # A request skipped by the time budget must not hide an earlier, more specific outcome.
        sent = bool(result["attempts"])
        if step == "fallback":
            if sent or self.fallback is None:
                self.fallback = result
                self.fallback_reason = reason
            return
        if sent or self.primary is None:
            self.primary = (
                split_batch_result(result, steam_appid=self.steam_appid)
                if step == "batch"
                else result
            )
            self.primary_reason = reason
            self.collected_at = collected_at

    def to_fetch_result(self) -> dict[str, Any]:
        primary = self.primary or build_time_budget_result(
            {"appids": self.steam_appid, **REQUEST_PARAMS_BASE}
        )
        attempt_stats = [primary["attempt_stats"]]
        if self.fallback is not None:
            attempt_stats.append(self.fallback["attempt_stats"])
        return {
            "attempts": primary["attempts"],
            "attempt_stats": sum_attempt_stats(attempt_stats),
            "error": primary["error"],
            "fallback": self.fallback,
            "fetch_failure": self.fetch_failure(),
            "fetch_trail": self.trail,
            "payload": primary["payload"],
            "primary": primary,
            "status_code": primary["status_code"],
        }


def _fetch_single_primary(
    state: AppFetchState,
    *,
    session: PriceRequestSession,
    fetch_pass: str,
    now_iso: Callable[[], str],
) -> None:
    collected_at = now_iso()
    result = session.get({"appids": state.steam_appid, **REQUEST_PARAMS_BASE})
    state.apply(step="single", fetch_pass=fetch_pass, result=result, collected_at=collected_at)


def _fetch_fallback(
    state: AppFetchState,
    *,
    session: PriceRequestSession,
    fetch_pass: str,
) -> None:
    result = session.get({"appids": state.steam_appid, **FALLBACK_REQUEST_PARAMS_BASE})
    state.apply(step="fallback", fetch_pass=fetch_pass, result=result)


def fetch_price_states(
    steam_appids: Sequence[int],
    *,
    session: PriceRequestSession,
    batch_size: int,
    now_iso: Callable[[], str] = utc_now_iso,
) -> dict[int, AppFetchState]:
    """Collect price evidence: batch, single supplement, free fallback, then one re-collect."""

    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    states = {steam_appid: AppFetchState(steam_appid) for steam_appid in steam_appids}
    appids = list(states)

    for start in range(0, len(appids), batch_size):
        chunk = appids[start : start + batch_size]
        collected_at = now_iso()
        batch_result = session.get(
            {"appids": ",".join(str(steam_appid) for steam_appid in chunk), **REQUEST_PARAMS_BASE}
        )
        batch_result["request"]["batch_size"] = len(chunk)
        for steam_appid in chunk:
            states[steam_appid].apply(
                step="batch",
                fetch_pass="first",
                result=batch_result,
                collected_at=collected_at,
            )

    for state in states.values():
        if state.primary_failure() is not None:
            _fetch_single_primary(state, session=session, fetch_pass="first", now_iso=now_iso)

    for state in states.values():
        if state.needs_fallback():
            _fetch_fallback(state, session=session, fetch_pass="first")

    for state in states.values():
        if state.primary_failure() is not None:
            _fetch_single_primary(state, session=session, fetch_pass="recollect", now_iso=now_iso)
            if state.needs_fallback():
                _fetch_fallback(state, session=session, fetch_pass="recollect")
        elif state.fallback_failure() is not None:
            _fetch_fallback(state, session=session, fetch_pass="recollect")

    return states


def build_bronze_record(
    *,
    canonical_game_id: int,
    steam_appid: int,
    collected_at: str,
    fetch_result: dict[str, Any],
) -> dict[str, Any]:
    """Build one bronze record while preserving the decoded raw payload."""

    primary = fetch_result.get("primary")
    if primary is None:
        primary = {
            "attempts": fetch_result["attempts"],
            "error": fetch_result["error"],
            "payload": fetch_result["payload"],
            "request": {
                "params": {
                    "appids": steam_appid,
                    **REQUEST_PARAMS_BASE,
                },
                "url": REQUEST_URL,
            },
            "status_code": fetch_result["status_code"],
        }

    return {
        "attempts": fetch_result["attempts"],
        "canonical_game_id": canonical_game_id,
        "collected_at": collected_at,
        "error": fetch_result["error"],
        "fallback": fetch_result.get("fallback"),
        "fetch_failure": fetch_result.get("fetch_failure"),
        "fetch_trail": fetch_result.get("fetch_trail", []),
        "http_status": fetch_result["status_code"],
        "payload": fetch_result["payload"],
        "primary": primary,
        "steam_appid": steam_appid,
    }


def fetch_price_records(
    targets: Sequence[Mapping[str, int]],
    *,
    session: PriceRequestSession,
    batch_size: int,
    now_iso: Callable[[], str] = utc_now_iso,
) -> list[dict[str, Any]]:
    """Fetch every target and return one bronze record per target, in target order."""

    states = fetch_price_states(
        [int(target["steam_appid"]) for target in targets],
        session=session,
        batch_size=batch_size,
        now_iso=now_iso,
    )
    records: list[dict[str, Any]] = []
    for target in targets:
        state = states[int(target["steam_appid"])]
        records.append(
            build_bronze_record(
                canonical_game_id=int(target["canonical_game_id"]),
                steam_appid=state.steam_appid,
                collected_at=state.collected_at or now_iso(),
                fetch_result=state.to_fetch_result(),
            )
        )
    return records


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic JSONL file for bronze handoff."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for Steam price fetch script."""

    parser = argparse.ArgumentParser(description="Fetch Steam KR price payloads into bronze JSONL")
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-base-sec", type=float, default=0.5)
    parser.add_argument("--jitter-max-sec", type=float, default=0.3)
    parser.add_argument("--max-backoff-sec", type=float, default=8.0)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--min-request-interval-sec",
        type=float,
        default=DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--max-retry-after-sec",
        type=float,
        default=DEFAULT_MAX_RETRY_AFTER_SECONDS,
    )
    parser.add_argument("--time-budget-sec", type=float, default=DEFAULT_TIME_BUDGET_SECONDS)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def run(
    *,
    output_path: Path,
    timeout_seconds: float,
    max_attempts: int,
    backoff_base_seconds: float,
    jitter_max_seconds: float,
    max_backoff_seconds: float,
    meta_path: Path | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    max_retry_after_seconds: float = DEFAULT_MAX_RETRY_AFTER_SECONDS,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    clock: RequestClock | None = None,
) -> list[dict[str, Any]]:
    """Fetch KR price payloads for all tracked Steam games and write bronze output."""

    started_at_utc = utc_now_iso()
    # The time budget starts here so target loading also counts toward it.
    session = PriceRequestSession(
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        jitter_max_seconds=jitter_max_seconds,
        max_backoff_seconds=max_backoff_seconds,
        min_request_interval_seconds=min_request_interval_seconds,
        max_retry_after_seconds=max_retry_after_seconds,
        time_budget_seconds=time_budget_seconds,
        clock=clock,
    )
    resolved_meta_path = meta_path or default_meta_path(
        job_name="fetch_price_1h",
        started_at_utc=started_at_utc,
    )

    success = False
    http_status: int | None = None
    records_in = 0
    fetch_failed_records = 0
    records_out = 0
    error_type: str | None = None
    error_message: str | None = None

    try:
        psycopg = require_psycopg()
        conninfo = build_pg_conninfo_from_env()

        with psycopg.connect(conninfo=conninfo) as conn:
            targets = load_tracked_steam_games(conn)

        records_in = len(targets)
        records = fetch_price_records(targets, session=session, batch_size=batch_size)

        write_jsonl(output_path, records)
        LOGGER.info("Wrote %s bronze rows to %s", len(records), output_path)

        fetch_failed_records = sum(1 for record in records if record["fetch_failure"])
        LOGGER.info(
            "Price fetch requests=%s fetch_failed_records=%s time_budget_exceeded=%s",
            session.request_count,
            fetch_failed_records,
            session.time_budget_exceeded,
        )
        records_out = len(records)
        success = True
        return records
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = str(exc)
        raise
    finally:
        finished_at_utc = utc_now_iso()
        aggregated_attempt_stats = sum_attempt_stats(session.attempt_stats)
        execution_meta = build_execution_meta(
            job_name="fetch_price_1h",
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            success=success,
            http_status=http_status,
            retry_count=aggregated_attempt_stats["retry_count"],
            timeout_count=aggregated_attempt_stats["timeout_count"],
            rate_limit_count=aggregated_attempt_stats["rate_limit_count"],
            records_in=records_in,
            records_out=records_out,
            error_type=error_type,
            error_message=error_message,
        )
        execution_meta.update(
            {
                "fetch_failed_records": fetch_failed_records,
                "request_count": session.request_count,
                "time_budget_exceeded": session.time_budget_exceeded,
            }
        )
        saved_meta_path = save_execution_meta(execution_meta, resolved_meta_path)
        LOGGER.info("Saved fetch execution meta to %s", saved_meta_path)


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    run(
        output_path=args.output_path,
        timeout_seconds=args.timeout_sec,
        max_attempts=args.max_attempts,
        backoff_base_seconds=args.backoff_base_sec,
        jitter_max_seconds=args.jitter_max_sec,
        max_backoff_seconds=args.max_backoff_sec,
        meta_path=args.meta_path,
        batch_size=args.batch_size,
        min_request_interval_seconds=args.min_request_interval_sec,
        max_retry_after_seconds=args.max_retry_after_sec,
        time_budget_seconds=args.time_budget_sec,
    )


if __name__ == "__main__":
    main()
