from __future__ import annotations

import io
import logging
import urllib.error

from steam.probe import common


class DummyResponse:
    def __init__(self, *, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self._status_code = status_code
        self.headers = headers
        self._body = body

    def getcode(self) -> int:
        return self._status_code

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> DummyResponse:
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:
        return False


def test_compute_backoff_seconds_respects_max(monkeypatch) -> None:
    monkeypatch.setattr(common.random, "uniform", lambda _start, _end: 0.2)

    value = common.compute_backoff_seconds(
        attempt=2,
        base_seconds=1.0,
        jitter_max_seconds=0.5,
        max_seconds=2.0,
    )

    assert value == 2.0


def test_selected_headers_returns_expected_keys() -> None:
    headers = {
        "Date": "Sat, 01 Jan 2000 00:00:00 GMT",
        "Content-Type": "application/json",
        "X-Ignored": "value",
    }

    selected = common.selected_headers(headers)

    assert selected["date"] == "Sat, 01 Jan 2000 00:00:00 GMT"
    assert selected["content-type"] == "application/json"
    assert selected["etag"] is None


def test_request_with_retry_retries_429_then_succeeds(monkeypatch, caplog) -> None:
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def fake_urlopen(request, timeout):
        del request, timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url="https://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "1"},
                fp=io.BytesIO(b'{"error":"rate_limited"}'),
            )
        return DummyResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"ok": true}',
        )

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(common.random, "uniform", lambda _start, _end: 0.0)

    caplog.set_level(logging.WARNING)
    result = common.request_with_retry(
        url="https://example.com",
        params=None,
        timeout_seconds=1.0,
        max_attempts=3,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.3,
        max_backoff_seconds=2.0,
    )

    assert result.status_code == 200
    assert result.error is None
    assert len(result.attempts) == 2
    assert result.attempts[0]["status_code"] == 429
    assert result.attempts[0]["sleep_seconds"] == 0.5
    assert sleep_calls == [0.5]
    assert any("HTTP 429" in record.message for record in caplog.records)


def test_request_with_retry_logs_empty_response(monkeypatch, caplog) -> None:
    def fake_urlopen(request, timeout):
        del request, timeout
        return DummyResponse(status_code=200, headers={}, body=b"")

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)

    caplog.set_level(logging.WARNING)
    result = common.request_with_retry(
        url="https://example.com",
        params=None,
        timeout_seconds=1.0,
        max_attempts=1,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )

    assert result.status_code == 200
    assert result.body == b""
    assert any("Empty response body" in record.message for record in caplog.records)
