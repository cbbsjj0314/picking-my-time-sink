from __future__ import annotations

import http.client
import json
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from steam.ingest import fetch_reviews_daily
from steam.normalize import bronze_to_silver_reviews, silver_to_gold_reviews
from steam.probe import common
from steam.probe.common import RequestResult

COLLECTED_AT = "2026-10-27T00:30:00Z"
EXPECTED_INPUT_JSON_730 = (
    '{"appid":730,"cursor":"*","day_range":0,"filter":0,"languages":["all"],'
    '"num_per_page":20,"purchase_type":1,"review_type":0}'
)


def make_result(
    body: dict[str, object],
    *,
    status_code: int = 200,
    error: dict[str, str] | None = None,
) -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=status_code,
        headers={"content-type": "application/json"},
        body=json.dumps(body).encode("utf-8"),
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": status_code}],
        error=error,
    )


def raw_result(body: bytes) -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=200,
        headers={"content-type": "text/html"},
        body=body,
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": 200}],
        error=None,
    )


def http_error(status_code: int, *, headers: dict[str, str] | None = None) -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=status_code,
        headers=headers or {},
        body=b"",
        attempts=[
            {
                "attempt": 1,
                "error": f"HTTP {status_code}",
                "sleep_seconds": 0.0,
                "status_code": status_code,
            }
        ],
        error={"type": "http_error", "message": f"HTTP {status_code}"},
    )


def envelope(total_reviews: int, total_positive: int, total_negative: int) -> dict[str, Any]:
    """Sanitized shape of the verified GetAppReviews first-page envelope."""

    return {
        "response": {
            "cursor": "SYNTHETIC-CURSOR",
            "day_range_used": 0,
            "query_summary": {
                "total_negative": total_negative,
                "total_positive": total_positive,
                "total_reviews": total_reviews,
            },
            "reviews": [{"review": "SYNTHETIC-REVIEW-TEXT", "voted_up": True}],
            "total_matching": total_reviews,
        }
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def request_clock(self) -> fetch_reviews_daily.RequestClock:
        return fetch_reviews_daily.RequestClock(monotonic=self.monotonic, sleep=self.sleep)


class FakeSteam:
    """Serve GetAppReviews per appid, optionally overriding the n-th call."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        responses: dict[int, RequestResult] | None = None,
        latency: float = 1.0,
        override: Any = None,
    ) -> None:
        self.clock = clock
        self.responses = responses or {}
        self.latency = latency
        self.override = override
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> RequestResult:
        params = dict(kwargs["params"])
        appid = json.loads(params["input_json"])["appid"]
        call = {
            "appid": appid,
            "kwargs": kwargs,
            "max_attempts": kwargs["max_attempts"],
            "started_at": self.clock.now,
        }
        self.calls.append(call)
        self.clock.now += self.latency
        call["finished_at"] = self.clock.now

        if self.override is not None:
            overridden = self.override(appid, len(self.calls) - 1)
            if overridden is not None:
                return overridden
        return self.responses.get(appid, make_result(envelope(100, 80, 20)))


def make_session(clock: FakeClock, **overrides: Any) -> fetch_reviews_daily.ReviewsRequestSession:
    kwargs: dict[str, Any] = {
        "timeout_seconds": 10.0,
        "max_attempts": 4,
        "backoff_base_seconds": 2.0,
        "jitter_max_seconds": 0.0,
        "max_backoff_seconds": 30.0,
        "min_request_interval_seconds": 2.0,
        "max_retry_after_seconds": 60.0,
        "time_budget_seconds": 2700.0,
        "clock": clock.request_clock(),
    }
    kwargs.update(overrides)
    return fetch_reviews_daily.ReviewsRequestSession(**kwargs)


def targets_for(appids: list[int]) -> list[dict[str, int]]:
    return [
        {"canonical_game_id": index + 1, "steam_appid": appid} for index, appid in enumerate(appids)
    ]


def fetch_records(
    monkeypatch: pytest.MonkeyPatch,
    steam: FakeSteam,
    appids: list[int],
    *,
    session: fetch_reviews_daily.ReviewsRequestSession | None = None,
) -> tuple[list[dict[str, Any]], fetch_reviews_daily.ReviewsRequestSession]:
    monkeypatch.setattr(fetch_reviews_daily, "request_with_retry", steam)
    resolved_session = session or make_session(steam.clock)
    records = fetch_reviews_daily.fetch_reviews_records(
        targets_for(appids),
        session=resolved_session,
        now_iso=lambda: COLLECTED_AT,
    )
    return records, resolved_session


class FakeCursor:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows
        self.executed_query: str | None = None

    def execute(self, query: str) -> None:
        self.executed_query = query

    def fetchall(self) -> list[tuple[object, object]]:
        return self.rows

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:
        return False


class FakeConn:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.cursor_instance = FakeCursor(rows)

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_request_uses_getappreviews_url_and_single_fixed_input_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam = FakeSteam(FakeClock())

    records, _ = fetch_records(monkeypatch, steam, [730])

    kwargs = steam.calls[0]["kwargs"]
    assert kwargs["url"] == "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
    assert kwargs["params"] == {"input_json": EXPECTED_INPUT_JSON_730}
    assert fetch_reviews_daily.build_request_params(730) == {"input_json": EXPECTED_INPUT_JSON_730}
    assert kwargs["max_attempts"] == 1
    assert "retryable_status_codes" not in kwargs
    assert "response_retry_reason" not in kwargs

    request = json.loads(kwargs["params"]["input_json"])
    for legacy_or_secret in ("key", "json", "language", "filter_offtopic_activity"):
        assert legacy_or_secret not in request
    for enum_key in ("filter", "purchase_type", "review_type", "day_range"):
        assert isinstance(request[enum_key], int)
    assert request["languages"] == ["all"]

    query = urllib.parse.urlencode(kwargs["params"])
    assert "key=" not in query
    assert records[0]["total_reviews"] == 100
    assert records[0]["fetch_failure"] is None


def test_extract_query_summary_reads_only_the_response_envelope() -> None:
    assert fetch_reviews_daily.extract_query_summary(envelope(100, 80, 20)) == {
        "total_reviews": 100,
        "total_positive": 80,
        "total_negative": 20,
    }


def _missing_totals() -> dict[str, Any]:
    payload = envelope(100, 80, 20)
    del payload["response"]["query_summary"]["total_negative"]
    return payload


def _with_total(key: str, value: object) -> dict[str, Any]:
    payload = envelope(100, 80, 20)
    payload["response"]["query_summary"][key] = value
    return payload


def _raw_envelope(total_reviews_literal: str) -> bytes:
    # Python's json module decodes the non-standard NaN / Infinity literals to floats.
    return (
        '{"response":{"query_summary":{"total_negative":20,"total_positive":80,'
        '"total_reviews":' + total_reviews_literal + "}}}"
    ).encode("utf-8")


INT_MAX = fetch_reviews_daily.POSTGRES_INTEGER_MAX


def test_review_total_limit_matches_postgres_integer_max() -> None:
    assert INT_MAX == 2**31 - 1 == 2_147_483_647

INVALID_SUMMARY_RESULTS = [
    pytest.param(
        make_result(
            {"query_summary": {"total_reviews": 100, "total_positive": 80, "total_negative": 20}}
        ),
        id="top-level-query-summary-without-response",
    ),
    pytest.param(make_result({"response": {}}), id="empty-response"),
    pytest.param(make_result(_missing_totals()), id="missing-total"),
    pytest.param(make_result(_with_total("total_reviews", "many")), id="non-numeric-string"),
    pytest.param(make_result(_with_total("total_reviews", "100")), id="numeric-string"),
    pytest.param(make_result(_with_total("total_reviews", 100.0)), id="integral-float"),
    pytest.param(make_result(_with_total("total_reviews", 100.5)), id="fractional-float"),
    pytest.param(make_result(_with_total("total_negative", True)), id="boolean-count"),
    pytest.param(make_result(_with_total("total_reviews", None)), id="null-count"),
    pytest.param(raw_result(_raw_envelope("NaN")), id="nan"),
    pytest.param(raw_result(_raw_envelope("Infinity")), id="infinity"),
    pytest.param(raw_result(_raw_envelope("1e400")), id="overflow-to-infinity"),
    pytest.param(make_result(envelope(100, 80, -1)), id="negative-total"),
    pytest.param(make_result(envelope(100, 80, 80)), id="inconsistent-sum-over"),
    pytest.param(
        make_result(envelope(INT_MAX + 1, INT_MAX + 1, 0)),
        id="postgres-integer-max-plus-one",
    ),
    pytest.param(make_result(envelope(10**30, 10**30, 0)), id="huge-int-consistent"),
    pytest.param(make_result(envelope(100, 70, 20)), id="inconsistent-sum-under"),
]


@pytest.mark.parametrize("result", INVALID_SUMMARY_RESULTS)
def test_http_200_without_valid_totals_is_missing_review_summary(
    monkeypatch: pytest.MonkeyPatch,
    result: RequestResult,
) -> None:
    steam = FakeSteam(FakeClock(), responses={730: result})

    records, _ = fetch_records(monkeypatch, steam, [730])

    assert records[0]["fetch_failure"] == {"reason": "missing_review_summary"}
    assert records[0]["http_status"] == 200
    assert records[0]["total_reviews"] is None
    assert records[0]["total_positive"] is None
    assert records[0]["total_negative"] is None


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(_with_total("total_negative", False), id="boolean-zero"),
        pytest.param(_with_total("total_reviews", float("nan")), id="nan"),
        pytest.param(_with_total("total_reviews", float("inf")), id="infinity"),
        pytest.param(_with_total("total_reviews", 10**400), id="huge-int-inconsistent"),
        pytest.param(envelope(INT_MAX + 1, INT_MAX, 1), id="postgres-integer-max-plus-one"),
        pytest.param(envelope(10**30, 10**30 - 1, 1), id="huge-int-consistent"),
    ],
)
def test_extract_query_summary_rejects_without_raising(body: dict[str, Any]) -> None:
    assert fetch_reviews_daily.extract_query_summary(body) is None


@pytest.mark.parametrize(
    ("totals", "expected_silver_skip"),
    [
        pytest.param((100, 80, 20), None, id="valid"),
        pytest.param((20, 0, 20), None, id="zero-positive"),
        pytest.param((0, 0, 0), "non_positive_total_reviews", id="zero-reviews"),
        pytest.param((INT_MAX, INT_MAX, 0), None, id="postgres-integer-max"),
        pytest.param((INT_MAX, 0, INT_MAX), None, id="postgres-integer-max-negative"),
    ],
)
def test_valid_integer_totals_are_kept_including_zero_counts(
    monkeypatch: pytest.MonkeyPatch,
    totals: tuple[int, int, int],
    expected_silver_skip: str | None,
) -> None:
    steam = FakeSteam(FakeClock(), responses={730: make_result(envelope(*totals))})

    records, _ = fetch_records(monkeypatch, steam, [730])
    silver = bronze_to_silver_reviews.normalize_bronze_record(records[0])

    assert records[0]["fetch_failure"] is None
    assert (
        records[0]["total_reviews"],
        records[0]["total_positive"],
        records[0]["total_negative"],
    ) == totals
    assert silver["skipped_reason"] == expected_silver_skip


def test_invalid_totals_never_reach_the_gold_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_results = [param.values[0] for param in INVALID_SUMMARY_RESULTS]
    valid_appid = 9999
    responses = {index + 1: result for index, result in enumerate(invalid_results)}
    responses[valid_appid] = make_result(envelope(100, 80, 20))
    steam = FakeSteam(FakeClock(), responses=responses, latency=0.0)
    session = make_session(steam.clock, min_request_interval_seconds=0.0)

    records, _ = fetch_records(monkeypatch, steam, list(responses), session=session)
    silver_rows = [bronze_to_silver_reviews.normalize_bronze_record(row) for row in records]
    upserted: list[tuple[object, ...]] = []
    gold_rows = silver_to_gold_reviews.process_silver_rows(
        silver_rows,
        upsert_row=lambda *args: upserted.append(args),
    )

    valid_game_id = next(
        row["canonical_game_id"] for row in records if row["steam_appid"] == valid_appid
    )
    assert [args[0] for args in upserted] == [valid_game_id]
    assert upserted[0][2:5] == (100, 80, 20)
    invalid_silver = [row for row in silver_rows if row["canonical_game_id"] != valid_game_id]
    assert len(invalid_silver) == len(invalid_results)
    assert {row["skipped_reason"] for row in invalid_silver} == {"missing_review_counts"}
    assert sum(1 for row in gold_rows if row["skipped"] is False) == 1


def test_non_json_body_is_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    steam = FakeSteam(FakeClock(), responses={730: raw_result(b"<html>not json</html>")})

    records, _ = fetch_records(monkeypatch, steam, [730])

    assert records[0]["fetch_failure"] == {"reason": "invalid_json"}
    assert records[0]["total_reviews"] is None


def test_missing_review_summary_flows_to_silver_missing_review_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam = FakeSteam(FakeClock(), responses={730: make_result({"response": {}})})

    records, _ = fetch_records(monkeypatch, steam, [730])
    silver = bronze_to_silver_reviews.normalize_bronze_record(records[0])

    assert records[0]["fetch_failure"]["reason"] == "missing_review_summary"
    assert silver["skipped_reason"] == "missing_review_counts"


def test_bronze_record_keeps_no_review_text_or_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    steam = FakeSteam(FakeClock())

    records, _ = fetch_records(monkeypatch, steam, [730])
    serialized = json.dumps(records[0], sort_keys=True)

    assert set(records[0]) == {
        "attempts",
        "canonical_game_id",
        "collected_at",
        "error",
        "fetch_failure",
        "http_status",
        "steam_appid",
        "total_negative",
        "total_positive",
        "total_reviews",
    }
    assert "SYNTHETIC-REVIEW-TEXT" not in serialized
    assert "SYNTHETIC-CURSOR" not in serialized


@pytest.mark.parametrize(
    ("headers", "expected_wait"),
    [
        pytest.param({"Retry-After": "5"}, 5.0, id="retry-after"),
        pytest.param({"Retry-After": "600"}, 60.0, id="retry-after-capped"),
        pytest.param({}, 2.0, id="missing-header-backoff"),
    ],
)
def test_rate_limited_attempt_waits_for_retry_after_or_backoff(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    expected_wait: float,
) -> None:
    clock = FakeClock()

    def first_call_429(_: int, index: int) -> RequestResult | None:
        return http_error(429, headers=headers) if index == 0 else None

    steam = FakeSteam(clock, override=first_call_429)
    session = make_session(clock, min_request_interval_seconds=0.0)

    records, _ = fetch_records(monkeypatch, steam, [730], session=session)

    gap = steam.calls[1]["started_at"] - steam.calls[0]["finished_at"]
    assert gap == pytest.approx(expected_wait)
    assert records[0]["attempts"][0]["sleep_seconds"] == pytest.approx(expected_wait)
    assert records[0]["fetch_failure"] is None
    assert sum(stats["rate_limit_count"] for stats in session.attempt_stats) == 1


def test_final_429_is_rate_limited_and_delays_the_next_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()

    def always_429_for_first_app(appid: int, _: int) -> RequestResult | None:
        return http_error(429, headers={"Retry-After": "45"}) if appid == 1 else None

    steam = FakeSteam(clock, override=always_429_for_first_app)

    records, session = fetch_records(monkeypatch, steam, [1, 2])

    first_app_calls = [call for call in steam.calls if call["appid"] == 1]
    second_app_call = next(call for call in steam.calls if call["appid"] == 2)
    assert len(first_app_calls) == 4
    assert records[0]["fetch_failure"] == {"reason": "rate_limited"}
    assert records[0]["http_status"] == 429
    assert second_app_call["started_at"] - first_app_calls[-1]["finished_at"] == pytest.approx(45.0)
    assert records[1]["fetch_failure"] is None
    assert session.request_count == 5


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        pytest.param(http_error(503), "server_error", id="5xx"),
        pytest.param(http_error(404), "http_error", id="4xx"),
        pytest.param(
            RequestResult(
                final_url="https://example.com",
                status_code=None,
                headers={},
                body=b"",
                attempts=[{"attempt": 1, "error": "timed out", "status_code": None}],
                error={"type": "timeout", "message": "timed out"},
            ),
            "timeout",
            id="timeout",
        ),
        pytest.param(
            RequestResult(
                final_url="https://example.com",
                status_code=None,
                headers={},
                body=b"",
                attempts=[{"attempt": 1, "error": "refused", "status_code": None}],
                error={"type": "url_error", "message": "refused"},
            ),
            "network_error",
            id="network",
        ),
    ],
)
def test_final_request_failures_are_classified(
    monkeypatch: pytest.MonkeyPatch,
    result: RequestResult,
    reason: str,
) -> None:
    steam = FakeSteam(FakeClock(), responses={730: result})

    records, _ = fetch_records(monkeypatch, steam, [730])

    assert records[0]["fetch_failure"] == {"reason": reason}
    assert records[0]["total_reviews"] is None


def test_minimum_interval_applies_between_apps_and_between_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()

    def flaky(_: int, index: int) -> RequestResult | None:
        # Retry-After 0 would otherwise allow an immediate retry.
        if index == 0:
            return http_error(429, headers={"Retry-After": "0"})
        return http_error(503) if index == 2 else None

    steam = FakeSteam(clock, override=flaky)
    session = make_session(clock, backoff_base_seconds=0.0)

    fetch_records(monkeypatch, steam, [1, 2, 3], session=session)

    assert len(steam.calls) == 5
    for previous, current in zip(steam.calls, steam.calls[1:], strict=False):
        assert current["started_at"] - previous["finished_at"] >= 2.0 - 1e-9


def test_time_budget_skips_remaining_apps_without_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    steam = FakeSteam(clock, latency=1.0)
    # Requests start at 0 and 3; the third app would start at 6 > budget 5.
    session = make_session(clock, time_budget_seconds=5.0)

    records, _ = fetch_records(monkeypatch, steam, [1, 2, 3, 4], session=session)

    assert [call["appid"] for call in steam.calls] == [1, 2]
    assert len(records) == 4
    assert [record["steam_appid"] for record in records] == [1, 2, 3, 4]
    assert [record["fetch_failure"] for record in records] == [
        None,
        None,
        {"reason": "time_budget_exceeded"},
        {"reason": "time_budget_exceeded"},
    ]
    assert records[2]["attempts"] == []
    assert records[2]["http_status"] is None
    assert records[2]["total_reviews"] is None
    assert session.time_budget_exceeded is True
    assert session.request_count == 2


def test_scheduled_path_defaults_match_pacing_policy() -> None:
    from steam.ingest import run_steam_cadence_job

    kwargs = run_steam_cadence_job._fetch_run_kwargs(
        fetch_reviews_daily,
        output_path=Path("out.jsonl"),
        meta_path=Path("meta.json"),
    )
    defaults = fetch_reviews_daily.run.__kwdefaults__

    assert kwargs["timeout_seconds"] == 10.0
    assert kwargs["max_attempts"] == 4
    assert kwargs["backoff_base_seconds"] == 2.0
    assert kwargs["max_backoff_seconds"] == 30.0
    assert kwargs["jitter_max_seconds"] == 0.3
    assert "min_request_interval_seconds" not in kwargs
    assert defaults["min_request_interval_seconds"] == 2.0
    assert defaults["max_retry_after_seconds"] == 60.0
    assert defaults["time_budget_seconds"] == 2700.0

    args = fetch_reviews_daily.build_parser().parse_args(["--output-path", "out.jsonl"])
    assert args.min_request_interval_sec == defaults["min_request_interval_seconds"]
    assert args.max_retry_after_sec == defaults["max_retry_after_seconds"]
    assert args.time_budget_sec == defaults["time_budget_seconds"]


class FakePsycopg:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows

    def connect(self, *, conninfo: str) -> Any:
        rows = self.rows

        class _Conn(FakeConn):
            def __enter__(self) -> _Conn:
                return self

            def __exit__(self, exc_type, exc, exc_tb) -> bool:
                return False

        return _Conn(rows)


def test_run_writes_one_row_per_target_and_records_fetch_meta(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clock = FakeClock()

    def flaky(appid: int, index: int) -> RequestResult | None:
        if index == 0:
            return http_error(429, headers={"Retry-After": "3"})
        return make_result({"response": {}}) if appid == 3 else None

    steam = FakeSteam(clock, override=flaky)
    monkeypatch.setattr(fetch_reviews_daily, "request_with_retry", steam)
    monkeypatch.setattr(
        fetch_reviews_daily,
        "require_psycopg",
        lambda: FakePsycopg([(1, "1"), (2, "2"), (3, "3")]),
    )
    monkeypatch.setattr(fetch_reviews_daily, "build_pg_conninfo_from_env", lambda: "fake")

    output_path = tmp_path / "reviews.bronze.jsonl"
    meta_path = tmp_path / "fetch.meta.json"
    rows = fetch_reviews_daily.run(
        output_path=output_path,
        timeout_seconds=10.0,
        max_attempts=4,
        backoff_base_seconds=2.0,
        jitter_max_seconds=0.0,
        max_backoff_seconds=30.0,
        meta_path=meta_path,
        clock=clock.request_clock(),
    )

    assert len(rows) == 3
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 3
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["request_count"] == 4
    assert meta["rate_limit_count"] == 1
    assert meta["retry_count"] == 1
    assert meta["fetch_failed_records"] == 1
    assert meta["time_budget_exceeded"] is False
    assert meta["records_out"] == 3
    assert rows[2]["fetch_failure"] == {"reason": "missing_review_summary"}


def test_load_tracked_steam_games_matches_existing_query_shape_and_skips_invalid_ids() -> None:
    conn = FakeConn(
        [
            (1, "730"),
            (2, "invalid"),
        ]
    )

    rows = fetch_reviews_daily.load_tracked_steam_games(conn)

    assert rows == [{"canonical_game_id": 1, "steam_appid": 730}]
    assert conn.cursor_instance.executed_query is not None
    normalized_query = conn.cursor_instance.executed_query.lower()
    assert "from tracked_game as tg" in normalized_query
    assert "inner join game_external_id as gei" in normalized_query
    assert "gei.source = 'steam'" in normalized_query
    assert "where tg.is_active = true" in normalized_query


def test_build_bronze_record_uses_collected_at_field_with_same_value() -> None:
    record = fetch_reviews_daily.build_bronze_record(
        canonical_game_id=1,
        steam_appid=730,
        collected_at="2026-03-06T21:46:06Z",
        fetch_result={
            "status_code": 200,
            "summary": {
                "total_reviews": 100,
                "total_positive": 80,
                "total_negative": 20,
            },
            "error": None,
            "attempts": [],
        },
    )

    assert record["collected_at"] == "2026-03-06T21:46:06Z"
    assert "collected_at_utc" not in record
    assert record["total_reviews"] == 100


class FakeTransportResponse:
    """Minimal urlopen response for driving the real shared request helper."""

    def __init__(self, *, body: bytes = b"", read_error: BaseException | None = None) -> None:
        self.headers = {"Content-Type": "application/json"}
        self._body = body
        self._read_error = read_error

    def getcode(self) -> int:
        return 200

    def read(self) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._body

    def __enter__(self) -> FakeTransportResponse:
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:  # noqa: ANN001
        return False


def test_transport_failures_are_retried_in_session_and_isolated_to_one_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    calls: list[tuple[int, float]] = []

    def fake_urlopen(request, timeout):  # noqa: ANN001
        del timeout
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        appid = json.loads(query["input_json"][0])["appid"]
        calls.append((appid, clock.now))
        clock.now += 1.0
        if appid == 570:
            raise ConnectionResetError(104, "raw-peer-detail")
        if len(calls) == 1:
            return FakeTransportResponse(
                read_error=http.client.IncompleteRead(b'{"response": {}}', 1000)
            )
        return FakeTransportResponse(body=json.dumps(envelope(100, 80, 20)).encode("utf-8"))

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    session = make_session(clock)

    records = fetch_reviews_daily.fetch_reviews_records(
        targets_for([730, 570, 440]),
        session=session,
        now_iso=lambda: COLLECTED_AT,
    )

    assert [call[0] for call in calls] == [730, 730, 570, 570, 570, 570, 440]
    for (_, previous_start), (_, current_start) in zip(calls, calls[1:], strict=False):
        assert current_start - (previous_start + 1.0) >= 2.0 - 1e-9
    assert [record["fetch_failure"] for record in records] == [
        None,
        {"reason": "network_error"},
        None,
    ]
    assert records[0]["total_reviews"] == 100
    assert [attempt["error"] for attempt in records[0]["attempts"]] == ["IncompleteRead", None]
    assert records[1]["http_status"] is None
    assert records[1]["total_reviews"] is None
    assert [attempt["error"] for attempt in records[1]["attempts"]] == ["ConnectionResetError"] * 4
