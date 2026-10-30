from __future__ import annotations

import http.client
import json
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from steam.ingest import fetch_price_1h
from steam.normalize import bronze_to_silver_price
from steam.normalize.silver_to_gold_price import process_silver_rows
from steam.probe import common
from steam.probe.common import RequestResult

REPO_ROOT = Path(__file__).resolve().parents[3]
REPRESENTATIVE_PRICE_PROBE = REPO_ROOT / "docs/probe/steam/price_kr/representative.json"
COLLECTED_AT = "2026-10-15T00:07:00Z"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def request_clock(self) -> fetch_price_1h.RequestClock:
        return fetch_price_1h.RequestClock(monotonic=self.monotonic, sleep=self.sleep)


def paid(final: int, *, initial: int | None = None, discount: int = 0) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "price_overview": {
                "currency": "KRW",
                "discount_percent": discount,
                "final": final,
                "initial": final if initial is None else initial,
            }
        },
    }


def empty_data() -> dict[str, Any]:
    return {"success": True, "data": []}


def not_success() -> dict[str, Any]:
    return {"success": False}


def full_appdetails(*, is_free: bool) -> dict[str, Any]:
    return {"success": True, "data": {"is_free": is_free, "name": "fixture"}}


def ok_result(body: object) -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps(body).encode("utf-8"),
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


def timeout_result() -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=None,
        headers={},
        body=b"",
        attempts=[{"attempt": 1, "error": "timed out", "sleep_seconds": 0.0, "status_code": None}],
        error={"type": "timeout", "message": "timed out"},
    )


Override = Callable[[dict[str, Any], int], RequestResult | None]


class FakeSteam:
    """Serve appdetails from per-app payload maps, like the batch-capable Steam endpoint."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        filtered: dict[int, dict[str, Any]],
        full: dict[int, dict[str, Any]] | None = None,
        latency: float = 0.2,
        override: Override | None = None,
    ) -> None:
        self.clock = clock
        self.filtered = filtered
        self.full = full or {}
        self.latency = latency
        self.override = override
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> RequestResult:
        params = dict(kwargs["params"])
        call = {
            "max_attempts": kwargs["max_attempts"],
            "params": params,
            "started_at": self.clock.now,
        }
        self.calls.append(call)
        self.clock.now += self.latency
        call["finished_at"] = self.clock.now

        if self.override is not None:
            overridden = self.override(params, len(self.calls) - 1)
            if overridden is not None:
                return overridden

        source = self.filtered if "filters" in params else self.full
        appids = [int(value) for value in str(params["appids"]).split(",")]
        return ok_result({str(appid): source[appid] for appid in appids if appid in source})

    def appid_lists(self) -> list[list[int]]:
        return [[int(v) for v in str(c["params"]["appids"]).split(",")] for c in self.calls]


def is_batch(params: dict[str, Any]) -> bool:
    return isinstance(params["appids"], str) and "," in params["appids"]


def make_session(clock: FakeClock, **overrides: Any) -> fetch_price_1h.PriceRequestSession:
    kwargs: dict[str, Any] = {
        "timeout_seconds": 10.0,
        "max_attempts": 4,
        "backoff_base_seconds": 0.5,
        "jitter_max_seconds": 0.0,
        "max_backoff_seconds": 8.0,
        "min_request_interval_seconds": 1.5,
        "max_retry_after_seconds": 60.0,
        "time_budget_seconds": 1500.0,
        "clock": clock.request_clock(),
    }
    kwargs.update(overrides)
    return fetch_price_1h.PriceRequestSession(**kwargs)


def targets_for(appids: list[int]) -> list[dict[str, int]]:
    return [
        {"canonical_game_id": index + 1, "steam_appid": appid} for index, appid in enumerate(appids)
    ]


def fetch_records(
    monkeypatch: pytest.MonkeyPatch,
    steam: FakeSteam,
    appids: list[int],
    *,
    batch_size: int = 100,
    session: fetch_price_1h.PriceRequestSession | None = None,
) -> tuple[list[dict[str, Any]], fetch_price_1h.PriceRequestSession]:
    monkeypatch.setattr(fetch_price_1h, "request_with_retry", steam)
    resolved_session = session or make_session(steam.clock)
    records = fetch_price_1h.fetch_price_records(
        targets_for(appids),
        session=resolved_session,
        batch_size=batch_size,
        now_iso=lambda: COLLECTED_AT,
    )
    return records, resolved_session


def by_appid(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(record["steam_appid"]): record for record in records}


def test_parser_and_run_defaults_enable_batch_pacing_and_time_budget() -> None:
    args = fetch_price_1h.build_parser().parse_args(["--output-path", "out.jsonl"])

    assert args.batch_size == 100
    assert args.min_request_interval_sec == 1.5
    assert args.max_retry_after_sec == 60.0
    assert args.time_budget_sec == 1500.0
    defaults = fetch_price_1h.run.__kwdefaults__
    assert defaults["batch_size"] == args.batch_size
    assert defaults["min_request_interval_seconds"] == args.min_request_interval_sec
    assert defaults["max_retry_after_seconds"] == args.max_retry_after_sec
    assert defaults["time_budget_seconds"] == args.time_budget_sec


def test_batches_split_by_batch_size_and_keep_per_app_payload_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appids = list(range(1000, 1281))
    clock = FakeClock()
    steam = FakeSteam(clock, filtered={appid: paid(appid * 100) for appid in appids})

    records, session = fetch_records(monkeypatch, steam, appids)

    assert [len(ids) for ids in steam.appid_lists()] == [100, 100, 81]
    assert steam.appid_lists()[2] == appids[200:]
    for call in steam.calls:
        assert call["max_attempts"] == 1
        assert {k: v for k, v in call["params"].items() if k != "appids"} == (
            fetch_price_1h.REQUEST_PARAMS_BASE
        )
    assert session.request_count == 3
    assert len(records) == 281

    tail = by_appid(records)[1280]
    assert tail["payload"] == {"1280": paid(128000)}
    assert tail["primary"]["payload"] == {"1280": paid(128000)}
    assert tail["primary"]["request"]["params"]["appids"] == ",".join(map(str, appids[200:]))
    assert tail["primary"]["request"]["batch_size"] == 81
    assert tail["http_status"] == 200
    assert tail["error"] is None
    assert tail["fallback"] is None
    assert tail["fetch_failure"] is None
    assert tail["fetch_trail"] == [
        {"outcome": "ok", "pass": "first", "status_code": 200, "step": "batch"}
    ]
    assert tail["collected_at"] == COLLECTED_AT


def test_duplicate_appids_are_requested_once_and_recorded_per_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    steam = FakeSteam(clock, filtered={730: paid(100), 570: paid(200)})

    records, _ = fetch_records(monkeypatch, steam, [730, 570, 730])

    assert steam.appid_lists() == [[730, 570]]
    assert [(r["canonical_game_id"], r["steam_appid"]) for r in records] == [
        (1, 730),
        (2, 570),
        (3, 730),
    ]
    assert records[2]["payload"] == {"730": paid(100)}


def test_missing_batch_key_is_supplemented_by_filtered_single_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()

    def drop_570_from_batch(params: dict[str, Any], _: int) -> RequestResult | None:
        if is_batch(params):
            return ok_result({"730": paid(100), "10": paid(300)})
        return None

    steam = FakeSteam(
        clock,
        filtered={730: paid(100), 570: paid(200), 10: paid(300)},
        override=drop_570_from_batch,
    )

    records, _ = fetch_records(monkeypatch, steam, [730, 570, 10])

    assert steam.calls[1]["params"] == {"appids": 570, **fetch_price_1h.REQUEST_PARAMS_BASE}
    assert len(steam.calls) == 2
    record = by_appid(records)[570]
    assert record["payload"] == {"570": paid(200)}
    assert record["primary"]["request"]["params"]["appids"] == 570
    assert "batch_size" not in record["primary"]["request"]
    assert record["fetch_failure"] is None
    assert [(t["step"], t["outcome"]) for t in record["fetch_trail"]] == [
        ("batch", "missing_key"),
        ("single", "ok"),
    ]


@pytest.mark.parametrize(
    "batch_failure",
    [
        pytest.param(lambda: http_error(500), id="http-500"),
        pytest.param(lambda: http_error(429), id="http-429"),
        pytest.param(timeout_result, id="timeout"),
        pytest.param(
            lambda: RequestResult("https://example.com", 200, {}, b"not-json", [], None),
            id="invalid-json",
        ),
    ],
)
def test_failed_batch_request_is_supplemented_by_single_requests(
    monkeypatch: pytest.MonkeyPatch,
    batch_failure: Callable[[], RequestResult],
) -> None:
    clock = FakeClock()

    def fail_batches(params: dict[str, Any], _: int) -> RequestResult | None:
        return batch_failure() if is_batch(params) else None

    steam = FakeSteam(clock, filtered={730: paid(100), 570: paid(200)}, override=fail_batches)

    records, _ = fetch_records(monkeypatch, steam, [730, 570])

    single_calls = [c["params"]["appids"] for c in steam.calls if not is_batch(c["params"])]
    assert single_calls == [730, 570]
    assert all(record["fetch_failure"] is None for record in records)
    assert by_appid(records)[570]["payload"] == {"570": paid(200)}


def test_empty_data_uses_unfiltered_fallback_and_steam_answers_are_not_fetch_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    steam = FakeSteam(
        clock,
        filtered={1: empty_data(), 2: empty_data(), 3: not_success(), 4: paid(100)},
        full={1: full_appdetails(is_free=True), 2: full_appdetails(is_free=False)},
    )

    records, _ = fetch_records(monkeypatch, steam, [1, 2, 3, 4])

    fallback_calls = [c["params"] for c in steam.calls[1:]]
    assert fallback_calls == [
        {"appids": 1, **fetch_price_1h.FALLBACK_REQUEST_PARAMS_BASE},
        {"appids": 2, **fetch_price_1h.FALLBACK_REQUEST_PARAMS_BASE},
    ]
    assert [record["fetch_failure"] for record in records] == [None, None, None, None]
    assert by_appid(records)[1]["fallback"]["payload"] == {"1": full_appdetails(is_free=True)}
    assert by_appid(records)[3]["payload"] == {"3": not_success()}

    silver = [bronze_to_silver_price.normalize_bronze_record(record) for record in records]
    assert silver[0] is not None and silver[0]["is_free"] is True
    assert silver[1] is None
    assert silver[2] is None
    assert silver[3] is not None and silver[3]["final_price_minor"] == 100


def test_retry_after_is_honored_capped_and_falls_back_to_backoff() -> None:
    assert fetch_price_1h.parse_retry_after_seconds({"Retry-After": "7"}) == 7.0
    assert fetch_price_1h.parse_retry_after_seconds({"retry-after": " 2.5 "}) == 2.5
    assert fetch_price_1h.parse_retry_after_seconds({}) is None
    for invalid in ("Wed, 21 Oct 2026 07:28:00 GMT", "-1", "nan", "inf", ""):
        assert fetch_price_1h.parse_retry_after_seconds({"Retry-After": invalid}) is None


@pytest.mark.parametrize(
    ("headers", "expected_wait"),
    [
        pytest.param({"Retry-After": "7"}, 7.0, id="retry-after"),
        pytest.param({"Retry-After": "600"}, 60.0, id="retry-after-capped"),
        pytest.param({}, 0.5, id="missing-header-backoff"),
        pytest.param({"Retry-After": "soon"}, 0.5, id="invalid-header-backoff"),
    ],
)
def test_rate_limited_attempt_waits_for_retry_after_or_backoff(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    expected_wait: float,
) -> None:
    clock = FakeClock()

    def first_call_429(_: dict[str, Any], index: int) -> RequestResult | None:
        return http_error(429, headers=headers) if index == 0 else None

    steam = FakeSteam(clock, filtered={730: paid(100), 570: paid(200)}, override=first_call_429)
    session = make_session(clock, min_request_interval_seconds=0.0)

    records, _ = fetch_records(monkeypatch, steam, [730, 570], session=session)

    gap = steam.calls[1]["started_at"] - steam.calls[0]["finished_at"]
    assert gap == pytest.approx(expected_wait)
    assert records[0]["primary"]["attempts"][0]["sleep_seconds"] == pytest.approx(expected_wait)
    assert records[0]["fetch_failure"] is None
    assert sum(stats["rate_limit_count"] for stats in session.attempt_stats) == 1


def test_minimum_interval_applies_to_every_request_including_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()

    def flaky(params: dict[str, Any], index: int) -> RequestResult | None:
        return http_error(503) if index in {0, 3} else None

    steam = FakeSteam(
        clock,
        filtered={1: empty_data(), 2: paid(100), 3: paid(200)},
        full={1: full_appdetails(is_free=True)},
        override=flaky,
    )

    fetch_records(monkeypatch, steam, [1, 2, 3], batch_size=2)

    assert len(steam.calls) >= 5
    for previous, current in zip(steam.calls, steam.calls[1:], strict=False):
        assert current["started_at"] - previous["finished_at"] >= 1.5 - 1e-9


def test_recollect_pass_recovers_apps_that_failed_the_first_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    single_570_calls = 0

    def rate_limit_570_first_pass(params: dict[str, Any], _: int) -> RequestResult | None:
        nonlocal single_570_calls
        if is_batch(params):
            return ok_result({"730": paid(100), "10": empty_data()})
        if params["appids"] == 570:
            single_570_calls += 1
            if single_570_calls <= 4:
                return http_error(429)
        if params["appids"] == 10 and "filters" not in params and single_570_calls < 5:
            return http_error(502)
        return None

    steam = FakeSteam(
        clock,
        filtered={730: paid(100), 570: paid(200), 10: empty_data()},
        full={10: full_appdetails(is_free=True)},
        override=rate_limit_570_first_pass,
    )

    records, _ = fetch_records(monkeypatch, steam, [730, 570, 10])

    assert [record["fetch_failure"] for record in records] == [None, None, None]
    assert by_appid(records)[570]["payload"] == {"570": paid(200)}
    assert by_appid(records)[570]["fetch_trail"][-1] == {
        "outcome": "ok",
        "pass": "recollect",
        "status_code": 200,
        "step": "single",
    }
    assert by_appid(records)[10]["fallback"]["payload"] == {"10": full_appdetails(is_free=True)}
    assert [(t["step"], t["pass"], t["outcome"]) for t in by_appid(records)[10]["fetch_trail"]] == [
        ("batch", "first", "ok"),
        ("fallback", "first", "server_error"),
        ("fallback", "recollect", "ok"),
    ]


def test_apps_that_stay_failed_record_stage_and_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()

    def always_fail(params: dict[str, Any], _: int) -> RequestResult | None:
        if is_batch(params):
            return ok_result({"730": paid(100), "10": empty_data()})
        if params["appids"] == 570:
            return http_error(429)
        if params["appids"] == 10 and "filters" not in params:
            return http_error(503)
        return None

    steam = FakeSteam(
        clock,
        filtered={730: paid(100), 570: paid(200), 10: empty_data()},
        override=always_fail,
    )

    records, session = fetch_records(monkeypatch, steam, [730, 570, 10])

    failures = {r["steam_appid"]: r["fetch_failure"] for r in records}
    assert failures == {
        730: None,
        570: {"reason": "rate_limited", "stage": "primary"},
        10: {"reason": "server_error", "stage": "fallback"},
    }
    single_570 = [c for c in steam.calls if c["params"]["appids"] == 570]
    assert len(single_570) == 8  # 4 attempts in the first pass + 4 in the re-collect pass
    assert by_appid(records)[570]["http_status"] == 429
    assert session.time_budget_exceeded is False


def test_time_budget_stops_new_requests_and_marks_remaining_apps_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    appids = list(range(1, 11))
    steam = FakeSteam(clock, filtered={appid: paid(appid) for appid in appids})
    session = make_session(clock, time_budget_seconds=5.0)

    records, _ = fetch_records(monkeypatch, steam, appids, batch_size=1, session=session)

    assert [c["started_at"] for c in steam.calls] == pytest.approx([0.0, 1.7, 3.4])
    assert all(call["started_at"] <= 5.0 for call in steam.calls)
    assert clock.now <= 5.0
    assert session.time_budget_exceeded is True
    assert len(records) == 10
    failed = [r for r in records if r["fetch_failure"] is not None]
    assert [r["steam_appid"] for r in failed] == appids[3:]
    assert failed[0]["fetch_failure"] == {"reason": "time_budget_exceeded", "stage": "primary"}
    assert failed[0]["payload"] is None
    assert failed[0]["http_status"] is None


def test_retry_wait_never_extends_past_the_time_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()

    def always_429(_: dict[str, Any], __: int) -> RequestResult:
        return http_error(429, headers={"Retry-After": "30"})

    steam = FakeSteam(clock, filtered={730: paid(100)}, override=always_429)
    session = make_session(clock, time_budget_seconds=10.0)

    records, _ = fetch_records(monkeypatch, steam, [730], session=session)

    assert len(steam.calls) == 1
    assert clock.sleeps == []
    assert clock.now <= 10.0
    assert records[0]["fetch_failure"] == {"reason": "rate_limited", "stage": "primary"}
    assert records[0]["primary"]["attempts"][-1]["sleep_seconds"] == 0.0


class OversleepClock(FakeClock):
    """Return from sleep later than asked, like a delayed or stopped process."""

    def __init__(self, oversleep_seconds: float) -> None:
        super().__init__()
        self.oversleep_seconds = oversleep_seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds + self.oversleep_seconds


def test_final_attempt_429_retry_after_delays_the_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()

    def appid_730_always_429(params: dict[str, Any], _: int) -> RequestResult | None:
        return http_error(429, headers={"Retry-After": "30"}) if params["appids"] == 730 else None

    steam = FakeSteam(clock, filtered={570: paid(200)}, latency=0.0, override=appid_730_always_429)
    monkeypatch.setattr(fetch_price_1h, "request_with_retry", steam)
    session = make_session(clock)

    session.get({"appids": 730, **fetch_price_1h.REQUEST_PARAMS_BASE})
    session.get({"appids": 570, **fetch_price_1h.REQUEST_PARAMS_BASE})

    assert [c["started_at"] for c in steam.calls[:4]] == pytest.approx([0.0, 30.0, 60.0, 90.0])
    assert steam.calls[4]["started_at"] >= 120.0 - 1e-9


@pytest.mark.parametrize(
    ("final_error", "expected_gap"),
    [
        # Attempt 4 backoff: 0.5 * 2**3 with no jitter, under the 8.0 cap.
        pytest.param(lambda: http_error(429), 4.0, id="429-without-retry-after-uses-backoff"),
        pytest.param(lambda: http_error(500), 1.5, id="500-keeps-minimum-interval"),
    ],
)
def test_final_attempt_cooldown_depends_on_failure_type(
    monkeypatch: pytest.MonkeyPatch,
    final_error: Callable[[], RequestResult],
    expected_gap: float,
) -> None:
    clock = FakeClock()

    def appid_730_always_fails(params: dict[str, Any], _: int) -> RequestResult | None:
        return final_error() if params["appids"] == 730 else None

    steam = FakeSteam(clock, filtered={570: paid(200)}, override=appid_730_always_fails)
    monkeypatch.setattr(fetch_price_1h, "request_with_retry", steam)
    session = make_session(clock)

    session.get({"appids": 730, **fetch_price_1h.REQUEST_PARAMS_BASE})
    session.get({"appids": 570, **fetch_price_1h.REQUEST_PARAMS_BASE})

    assert len(steam.calls) == 5
    gap = steam.calls[4]["started_at"] - steam.calls[3]["finished_at"]
    assert gap == pytest.approx(expected_gap)


def test_final_429_cooldown_past_deadline_skips_the_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()

    def appid_730_always_429(params: dict[str, Any], _: int) -> RequestResult | None:
        is_730 = str(params["appids"]) == "730"
        return http_error(429, headers={"Retry-After": "30"}) if is_730 else None

    steam = FakeSteam(clock, filtered={570: paid(200)}, latency=0.0, override=appid_730_always_429)
    session = make_session(clock, time_budget_seconds=100.0)

    records, _ = fetch_records(monkeypatch, steam, [730, 570], batch_size=1, session=session)

    assert [c["params"]["appids"] for c in steam.calls] == ["730"] * 4
    assert session.time_budget_exceeded is True
    assert by_appid(records)[730]["fetch_failure"] == {"reason": "rate_limited", "stage": "primary"}
    assert by_appid(records)[570]["fetch_failure"] == {
        "reason": "time_budget_exceeded",
        "stage": "primary",
    }


def test_oversleep_past_deadline_does_not_send_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = OversleepClock(oversleep_seconds=0.2)
    steam = FakeSteam(clock, filtered={730: paid(100), 570: paid(200)})
    session = make_session(clock)
    # First request at 1498.2 finishes at 1498.4; the 1.5s interval wakes at 1500.1, not 1499.9.
    clock.now = 1498.2

    records, _ = fetch_records(monkeypatch, steam, [730, 570], batch_size=1, session=session)

    assert len(steam.calls) == 1
    assert all(call["started_at"] <= 1500.0 for call in steam.calls)
    assert session.time_budget_exceeded is True
    assert by_appid(records)[730]["fetch_failure"] is None
    assert by_appid(records)[570]["fetch_failure"] == {
        "reason": "time_budget_exceeded",
        "stage": "primary",
    }


def load_representative_price_payload() -> dict[str, Any]:
    snapshot = json.loads(REPRESENTATIVE_PRICE_PROBE.read_text(encoding="utf-8"))
    return snapshot["response"]["payload_excerpt_or_json"]


def test_batch_bronze_matches_legacy_single_bronze_through_silver_and_gold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    representative = load_representative_price_payload()
    filtered = {
        252490: representative["252490"],
        730: empty_data(),
        440: empty_data(),
        570: not_success(),
        1091500: paid(3600000, initial=6000000, discount=40),
    }
    full = {730: full_appdetails(is_free=True), 440: full_appdetails(is_free=False)}
    appids = list(filtered)
    targets = targets_for(appids)

    def legacy_request(**kwargs: Any) -> RequestResult:
        params = kwargs["params"]
        source = filtered if "filters" in params else full
        appid = int(params["appids"])
        return ok_result({str(appid): source[appid]})

    monkeypatch.setattr(fetch_price_1h, "request_with_retry", legacy_request)
    legacy_bronze = []
    for target in targets:
        legacy_bronze.append(
            fetch_price_1h.build_bronze_record(
                canonical_game_id=target["canonical_game_id"],
                steam_appid=target["steam_appid"],
                collected_at=COLLECTED_AT,
                fetch_result=fetch_price_1h.fetch_price_for_app(
                    steam_appid=target["steam_appid"],
                    timeout_seconds=10.0,
                    max_attempts=4,
                    backoff_base_seconds=0.5,
                    jitter_max_seconds=0.0,
                    max_backoff_seconds=8.0,
                ),
            )
        )

    steam = FakeSteam(FakeClock(), filtered=filtered, full=full)
    batch_bronze, _ = fetch_records(monkeypatch, steam, appids)

    assert [r["payload"] for r in batch_bronze] == [r["payload"] for r in legacy_bronze]
    assert [r["fallback"] and r["fallback"]["payload"] for r in batch_bronze] == [
        r["fallback"] and r["fallback"]["payload"] for r in legacy_bronze
    ]

    def to_silver(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = [bronze_to_silver_price.normalize_bronze_record(row) for row in rows]
        return bronze_to_silver_price.dedupe_silver_records([r for r in normalized if r])

    legacy_silver = to_silver(legacy_bronze)
    batch_silver = to_silver(batch_bronze)
    assert batch_silver == legacy_silver
    assert [row["steam_appid"] for row in batch_silver] == [252490, 730, 1091500]

    def to_gold(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple]]:
        upserts: list[tuple] = []
        results = process_silver_rows(rows, upsert_row=lambda *args: upserts.append(args))
        return results, upserts

    assert to_gold(batch_silver) == to_gold(legacy_silver)


class FakePsycopg:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows

    def connect(self, *, conninfo: str) -> Any:
        rows = self.rows

        class Conn:
            def __enter__(self) -> Conn:
                return self

            def __exit__(self, *exc: object) -> bool:
                return False

            def cursor(self) -> Any:
                class Cursor:
                    def __enter__(self) -> Cursor:
                        return self

                    def __exit__(self, *exc: object) -> bool:
                        return False

                    def execute(self, query: str) -> None:
                        pass

                    def fetchall(self) -> list[tuple[object, object]]:
                        return rows

                return Cursor()

        return Conn()


def test_run_writes_bronze_and_counts_rate_limits_per_request_not_per_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    appids = list(range(1, 151))
    clock = FakeClock()

    def batch_429_once(_: dict[str, Any], index: int) -> RequestResult | None:
        return http_error(429, headers={"Retry-After": "3"}) if index == 0 else None

    steam = FakeSteam(
        clock,
        filtered={appid: paid(appid) for appid in appids if appid != 150},
        override=batch_429_once,
    )
    monkeypatch.setattr(fetch_price_1h, "request_with_retry", steam)
    monkeypatch.setattr(
        fetch_price_1h,
        "require_psycopg",
        lambda: FakePsycopg([(appid, str(appid)) for appid in appids]),
    )
    monkeypatch.setattr(fetch_price_1h, "build_pg_conninfo_from_env", lambda: "fake")

    output_path = tmp_path / "price.bronze.jsonl"
    meta_path = tmp_path / "fetch.meta.json"
    rows = fetch_price_1h.run(
        output_path=output_path,
        timeout_seconds=10.0,
        max_attempts=4,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.0,
        max_backoff_seconds=8.0,
        meta_path=meta_path,
        clock=clock.request_clock(),
    )

    assert len(rows) == 150
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 150
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    # Batch 1 (429 then 200), batch 2 (200 but 150 missing), single 150 x2 passes.
    assert meta["request_count"] == 5
    assert meta["rate_limit_count"] == 1
    assert meta["retry_count"] == 1
    assert meta["fetch_failed_records"] == 1
    assert meta["time_budget_exceeded"] is False
    assert meta["records_out"] == 150
    assert by_appid(rows)[150]["fetch_failure"] == {"reason": "missing_key", "stage": "primary"}


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
    calls: list[tuple[str, float]] = []

    def fake_urlopen(request, timeout):  # noqa: ANN001
        del timeout
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        appids = query["appids"][0]
        calls.append((appids, clock.now))
        clock.now += 0.2
        if "570" in appids.split(","):
            # Truncated JSON-looking bytes must not become an app-level answer.
            return FakeTransportResponse(
                read_error=http.client.IncompleteRead(b'{"570": {"success": true}}', 1000)
            )
        return FakeTransportResponse(body=json.dumps({"730": paid(100)}).encode("utf-8"))

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    session = make_session(clock)

    records = fetch_price_1h.fetch_price_records(
        targets_for([730, 570]),
        session=session,
        batch_size=100,
        now_iso=lambda: COLLECTED_AT,
    )

    failures = {record["steam_appid"]: record["fetch_failure"] for record in records}
    assert failures == {730: None, 570: {"reason": "network_error", "stage": "primary"}}
    assert by_appid(records)[570]["http_status"] is None
    single_570 = [appids for appids, _ in calls if appids == "570"]
    assert len(single_570) == 8  # 4 attempts in the first pass + 4 in the re-collect pass
    for (_, previous_start), (_, current_start) in zip(calls, calls[1:], strict=False):
        assert current_start - (previous_start + 0.2) >= 1.5 - 1e-9
    assert session.time_budget_exceeded is False
