from __future__ import annotations

import json

from steam.ingest import fetch_price_1h
from steam.probe.common import RequestResult


def sample_payload() -> dict[str, object]:
    return {
        "252490": {
            "success": True,
            "data": {
                "price_overview": {
                    "currency": "KRW",
                    "discount_percent": 0,
                    "final": 4200000,
                    "initial": 4200000,
                }
            },
        }
    }


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


def test_fetch_price_for_app_uses_repo_grounded_params_and_shared_retry_defaults(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_request_with_retry(**kwargs) -> RequestResult:
        captured.update(kwargs)
        return make_result(sample_payload())

    monkeypatch.setattr(fetch_price_1h, "request_with_retry", fake_request_with_retry)

    result = fetch_price_1h.fetch_price_for_app(
        steam_appid=252490,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )

    assert captured["url"] == fetch_price_1h.REQUEST_URL
    assert captured["params"] == {
        "appids": 252490,
        **fetch_price_1h.REQUEST_PARAMS_BASE,
    }
    assert "retryable_status_codes" not in captured
    assert "response_retry_reason" not in captured
    assert result["payload"] == sample_payload()


def test_load_tracked_steam_games_matches_existing_query_shape_and_skips_invalid_ids() -> None:
    conn = FakeConn(
        [
            (1, "730"),
            (2, "invalid"),
        ]
    )

    rows = fetch_price_1h.load_tracked_steam_games(conn)

    assert rows == [{"canonical_game_id": 1, "steam_appid": 730}]
    assert conn.cursor_instance.executed_query is not None
    normalized_query = conn.cursor_instance.executed_query.lower()
    assert "from tracked_game as tg" in normalized_query
    assert "inner join game_external_id as gei" in normalized_query
    assert "gei.source = 'steam'" in normalized_query
    assert "where tg.is_active = true" in normalized_query


def test_build_bronze_record_keeps_raw_payload_and_minimal_helper_fields() -> None:
    payload = sample_payload()

    record = fetch_price_1h.build_bronze_record(
        canonical_game_id=1,
        steam_appid=252490,
        collected_at="2026-03-12T21:41:38Z",
        fetch_result={
            "attempts": [],
            "error": None,
            "payload": payload,
            "status_code": 200,
        },
    )

    assert record["collected_at"] == "2026-03-12T21:41:38Z"
    assert record["payload"] == payload
    assert "currency_code" not in record
    assert "final_price_minor" not in record
