from __future__ import annotations

import email.message
import io
import urllib.error

import pytest

from steam.ingest import fetch_ccu_30m
from steam.probe import common
from steam.probe.common import RequestResult


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


def test_load_tracked_steam_games_matches_existing_query_shape_and_skips_invalid_ids() -> None:
    conn = FakeConn(
        [
            (1, "730"),
            (2, "invalid"),
        ]
    )

    rows = fetch_ccu_30m.load_tracked_steam_games(conn)

    assert rows == [{"canonical_game_id": 1, "steam_appid": 730}]
    assert conn.cursor_instance.executed_query is not None
    normalized_query = conn.cursor_instance.executed_query.lower()
    assert "from tracked_game as tg" in normalized_query
    assert "inner join game_external_id as gei" in normalized_query
    assert "gei.source = 'steam'" in normalized_query
    assert "where tg.is_active = true" in normalized_query


def test_fetch_ccu_for_app_maps_final_404_to_missing_reason(monkeypatch) -> None:
    def fake_request_with_retry(**kwargs) -> RequestResult:
        assert kwargs["retryable_status_codes"] == fetch_ccu_30m.CCU_RETRYABLE_STATUS_CODES
        assert kwargs["response_retry_reason"] is fetch_ccu_30m.ccu_response_retry_reason
        return RequestResult(
            final_url="https://example.com",
            status_code=404,
            headers={},
            body=b"",
            attempts=[
                {
                    "attempt": 1,
                    "error": "HTTP 404",
                    "sleep_seconds": 0.0,
                    "status_code": 404,
                }
            ],
            error={"type": "http_error", "message": "HTTP 404"},
        )

    monkeypatch.setattr(fetch_ccu_30m, "request_with_retry", fake_request_with_retry)

    result = fetch_ccu_30m.fetch_ccu_for_app(
        steam_appid=730,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )

    assert result["ccu"] is None
    assert result["missing_reason"] == "http_404"


@pytest.mark.parametrize("message", ["empty_body", "invalid_json"])
def test_fetch_ccu_for_app_maps_abnormal_payload_to_missing_reason(
    monkeypatch,
    message: str,
) -> None:
    def fake_request_with_retry(**kwargs) -> RequestResult:
        del kwargs
        return RequestResult(
            final_url="https://example.com",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b"" if message == "empty_body" else b"not-json",
            attempts=[
                {
                    "attempt": 1,
                    "error": message,
                    "sleep_seconds": 0.0,
                    "status_code": 200,
                }
            ],
            error={"type": "response_error", "message": message},
        )

    monkeypatch.setattr(fetch_ccu_30m, "request_with_retry", fake_request_with_retry)

    result = fetch_ccu_30m.fetch_ccu_for_app(
        steam_appid=730,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )

    assert result["ccu"] is None
    assert result["missing_reason"] == "missing_player_count"


def test_fetch_ccu_for_app_maps_http_500_then_transport_failure_to_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final transport attempt must not inherit the earlier HTTP 500 status."""

    responses: list[BaseException] = [
        urllib.error.HTTPError(
            "https://example.com", 500, "error", email.message.Message(), io.BytesIO(b"")
        ),
        ConnectionResetError(104, "raw-peer-detail"),
    ]

    def fake_urlopen(request, timeout):  # noqa: ANN001
        del request, timeout
        raise responses.pop(0)

    monkeypatch.delenv("STEAM_API_KEY", raising=False)
    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", lambda _seconds: None)

    result = fetch_ccu_30m.fetch_ccu_for_app(
        steam_appid=730,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.0,
        max_backoff_seconds=2.0,
    )

    assert result["missing_reason"] == "request_error:url_error"
    assert result["status_code"] is None
    assert result["ccu"] is None
    assert [attempt["error"] for attempt in result["attempts"]] == [
        "HTTP 500",
        "ConnectionResetError",
    ]
