from __future__ import annotations

import json

from steam.ingest import fetch_reviews_daily
from steam.probe.common import RequestResult


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


def test_fetch_reviews_for_app_uses_repo_grounded_params_and_shared_retry_defaults(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_request_with_retry(**kwargs) -> RequestResult:
        captured.update(kwargs)
        return make_result(
            {
                "query_summary": {
                    "total_reviews": 100,
                    "total_positive": 80,
                    "total_negative": 20,
                }
            }
        )

    monkeypatch.setattr(fetch_reviews_daily, "request_with_retry", fake_request_with_retry)

    result = fetch_reviews_daily.fetch_reviews_for_app(
        steam_appid=730,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )

    assert captured["url"] == "https://store.steampowered.com/appreviews/730"
    assert captured["params"] == fetch_reviews_daily.REQUEST_PARAMS
    assert "retryable_status_codes" not in captured
    assert "response_retry_reason" not in captured
    assert result["summary"] == {
        "total_reviews": 100,
        "total_positive": 80,
        "total_negative": 20,
    }


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
