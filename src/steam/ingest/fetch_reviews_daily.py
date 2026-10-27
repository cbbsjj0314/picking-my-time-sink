"""Fetch Steam reviews snapshots for tracked games and write bronze JSONL."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
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
from steam.ingest.fetch_price_1h import (
    FAILURE_HTTP_ERROR,
    FAILURE_INVALID_JSON,
    FAILURE_NETWORK_ERROR,
    FAILURE_RATE_LIMITED,
    FAILURE_SERVER_ERROR,
    FAILURE_TIME_BUDGET_EXCEEDED,
    FAILURE_TIMEOUT,
    RequestClock,
    is_retryable_result,
    parse_retry_after_seconds,
)
from steam.probe.common import (
    RequestResult,
    compute_backoff_seconds,
    decode_json_payload,
    request_with_retry,
)

LOGGER = logging.getLogger(__name__)
REQUEST_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
# GetAppReviews enum values that preserve the legacy appreviews series (`filter=all`,
# `purchase_type=all`, `language=all`). Evidence: the 2026-10-27 keyless probe summarized
# in docs/metrics-definitions.md §2.4. purchase_type Steam=0 would drop non-Steam purchases.
FILTER_HELPFUL = 0
REVIEW_TYPE_ALL = 0
PURCHASE_TYPE_ALL = 1
LANGUAGES_ALL = ("all",)
# day_range does not scope query_summary totals; 0 is the explicit no-limit choice.
DAY_RANGE_NO_LIMIT = 0
NUM_PER_PAGE = 20
FIRST_PAGE_CURSOR = "*"

DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 2.0
DEFAULT_MAX_RETRY_AFTER_SECONDS = 60.0
DEFAULT_TIME_BUDGET_SECONDS = 2700.0

FAILURE_MISSING_REVIEW_SUMMARY = "missing_review_summary"
REVIEW_TOTAL_KEYS = ("total_reviews", "total_positive", "total_negative")


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
        raise RuntimeError("psycopg is required for Steam reviews ingest") from exc
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


def build_request_input(steam_appid: int) -> dict[str, Any]:
    """Build the fixed first-page GetAppReviews request for one app."""

    return {
        "appid": steam_appid,
        "cursor": FIRST_PAGE_CURSOR,
        "day_range": DAY_RANGE_NO_LIMIT,
        "filter": FILTER_HELPFUL,
        "languages": list(LANGUAGES_ALL),
        "num_per_page": NUM_PER_PAGE,
        "purchase_type": PURCHASE_TYPE_ALL,
        "review_type": REVIEW_TYPE_ALL,
    }


def build_request_params(steam_appid: int) -> dict[str, str]:
    """Encode the request as the single `input_json` query value GetAppReviews expects."""

    input_json = json.dumps(build_request_input(steam_appid), separators=(",", ":"), sort_keys=True)
    return {"input_json": input_json}


def extract_query_summary(payload: Any) -> dict[str, int] | None:
    """Extract review summary totals from a GetAppReviews `response` envelope."""

    if not isinstance(payload, dict):
        return None

    response = payload.get("response")
    if not isinstance(response, dict):
        return None

    query_summary = response.get("query_summary")
    if not isinstance(query_summary, dict):
        return None

    parsed: dict[str, int] = {}
    for key in REVIEW_TOTAL_KEYS:
        value = query_summary.get(key)
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            return None
        if parsed_value < 0:
            return None
        parsed[key] = parsed_value

    return parsed


def build_time_budget_result() -> dict[str, Any]:
    """Describe a request that was not sent because the fetch time budget ran out."""

    return {
        "attempts": [],
        "attempt_stats": summarize_attempts([]),
        "error": {
            "type": FAILURE_TIME_BUDGET_EXCEEDED,
            "message": "fetch time budget exceeded before request",
        },
        "payload": None,
        "status_code": None,
    }


class ReviewsRequestSession:
    """Send reviews-job Steam requests with pacing, Retry-After, and a total time budget.

    Mirrors PriceRequestSession: request_with_retry is called with max_attempts=1 so that
    every attempt, including retries, passes through the same minimum interval and deadline.
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
            # Sleep can return late (scheduling delay, stopped process); recheck before sending.
            if self.clock.monotonic() > self.deadline:
                self.time_budget_exceeded = True
                return False
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
        """Fetch one GetAppReviews request and return the decoded request result."""

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

            if not is_retryable_result(result):
                break
            is_last_attempt = attempt >= self.max_attempts
            if is_last_attempt and result.status_code != 429:
                break

            retry_at = finished_at + self._retry_delay_seconds(result, attempt=attempt)
            self.next_request_at = max(self.next_request_at, retry_at)
            if is_last_attempt:
                # A final 429 still owes its cooldown to the next app's request.
                break
            attempt_log["sleep_seconds"] = round(self.next_request_at - finished_at, 3)

        if result is None:
            budget_result = build_time_budget_result()
            self.attempt_stats.append(budget_result["attempt_stats"])
            return budget_result

        attempt_stats = summarize_attempts(attempts)
        self.attempt_stats.append(attempt_stats)
        return {
            "attempts": attempts,
            "attempt_stats": attempt_stats,
            "error": result.error,
            "payload": decode_json_payload(result.body),
            "status_code": result.status_code,
        }


def classify_fetch_failure(result: Mapping[str, Any], summary: dict[str, int] | None) -> str | None:
    """Return why a request result holds no usable review totals, or None when it does.

    GetAppReviews has no `success` field, so an HTTP 200 without valid totals is a failure.
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
    if result.get("payload") is None:
        return FAILURE_INVALID_JSON
    if summary is None:
        return FAILURE_MISSING_REVIEW_SUMMARY
    return None


def fetch_reviews_for_app(
    *,
    steam_appid: int,
    session: ReviewsRequestSession,
) -> dict[str, Any]:
    """Fetch one app's first-page review summary through the paced session."""

    result = session.get(build_request_params(steam_appid))
    summary = extract_query_summary(result["payload"])
    reason = classify_fetch_failure(result, summary)

    return {
        "status_code": result["status_code"],
        "summary": summary if reason is None else None,
        "error": result["error"],
        "attempts": result["attempts"],
        "attempt_stats": result["attempt_stats"],
        "fetch_failure": None if reason is None else {"reason": reason},
    }


def build_bronze_record(
    *,
    canonical_game_id: int,
    steam_appid: int,
    collected_at: str,
    fetch_result: dict[str, Any],
) -> dict[str, Any]:
    """Build one bronze record with explicit UTC collected_at semantics."""

    summary = fetch_result["summary"]

    return {
        "attempts": fetch_result["attempts"],
        "canonical_game_id": canonical_game_id,
        "collected_at": collected_at,
        "error": fetch_result["error"],
        "fetch_failure": fetch_result.get("fetch_failure"),
        "http_status": fetch_result["status_code"],
        "steam_appid": steam_appid,
        "total_negative": None if summary is None else summary["total_negative"],
        "total_positive": None if summary is None else summary["total_positive"],
        "total_reviews": None if summary is None else summary["total_reviews"],
    }


def fetch_reviews_records(
    targets: Sequence[Mapping[str, int]],
    *,
    session: ReviewsRequestSession,
    now_iso: Callable[[], str] = utc_now_iso,
) -> list[dict[str, Any]]:
    """Fetch every target and return one bronze record per target, in target order."""

    records: list[dict[str, Any]] = []
    for target in targets:
        steam_appid = int(target["steam_appid"])
        collected_at = now_iso()
        result = fetch_reviews_for_app(steam_appid=steam_appid, session=session)
        records.append(
            build_bronze_record(
                canonical_game_id=int(target["canonical_game_id"]),
                steam_appid=steam_appid,
                collected_at=collected_at,
                fetch_result=result,
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
    """Build CLI parser for Steam reviews fetch script."""

    parser = argparse.ArgumentParser(description="Fetch Steam reviews snapshots into bronze JSONL")
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-base-sec", type=float, default=2.0)
    parser.add_argument("--jitter-max-sec", type=float, default=0.3)
    parser.add_argument("--max-backoff-sec", type=float, default=30.0)
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
    min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    max_retry_after_seconds: float = DEFAULT_MAX_RETRY_AFTER_SECONDS,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    clock: RequestClock | None = None,
) -> list[dict[str, Any]]:
    """Fetch reviews for all tracked Steam games and write bronze output."""

    started_at_utc = utc_now_iso()
    # The time budget starts here so target loading also counts toward it.
    session = ReviewsRequestSession(
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
        job_name="fetch_reviews_daily",
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
        records = fetch_reviews_records(targets, session=session)

        write_jsonl(output_path, records)
        LOGGER.info("Wrote %s bronze rows to %s", len(records), output_path)

        fetch_failed_records = sum(1 for record in records if record["fetch_failure"])
        LOGGER.info(
            "Reviews fetch requests=%s fetch_failed_records=%s time_budget_exceeded=%s",
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
            job_name="fetch_reviews_daily",
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
        min_request_interval_seconds=args.min_request_interval_sec,
        max_retry_after_seconds=args.max_retry_after_sec,
        time_budget_seconds=args.time_budget_sec,
    )


if __name__ == "__main__":
    main()
