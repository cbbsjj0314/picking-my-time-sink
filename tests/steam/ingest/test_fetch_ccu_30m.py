from __future__ import annotations

import pytest

from steam.ingest import fetch_ccu_30m
from steam.probe.common import RequestResult


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
