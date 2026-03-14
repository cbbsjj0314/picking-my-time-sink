from __future__ import annotations

import io
import logging
import urllib.error

from steam.common.execution_meta import summarize_attempts
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


def test_request_with_retry_default_behavior_does_not_retry_404(monkeypatch) -> None:
    sleep_calls: list[float] = []

    def fake_urlopen(request, timeout):
        del request, timeout
        raise urllib.error.HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b'{"error":"not_found"}'),
        )

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = common.request_with_retry(
        url="https://example.com",
        params=None,
        timeout_seconds=1.0,
        max_attempts=3,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )

    assert result.status_code == 404
    assert len(result.attempts) == 1
    assert result.error == {"type": "http_error", "message": "HTTP 404"}
    assert sleep_calls == []


def test_request_with_retry_retries_opt_in_404(monkeypatch) -> None:
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def fake_urlopen(request, timeout):
        del request, timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url="https://example.com",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=io.BytesIO(b'{"error":"not_found"}'),
            )
        return DummyResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"ok": true}',
        )

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(common.random, "uniform", lambda _start, _end: 0.0)

    result = common.request_with_retry(
        url="https://example.com",
        params=None,
        timeout_seconds=1.0,
        max_attempts=3,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        retryable_status_codes={404, 429, 500, 502, 503, 504},
    )

    assert result.status_code == 200
    assert result.error is None
    assert len(result.attempts) == 2
    assert result.attempts[0]["status_code"] == 404
    assert result.attempts[0]["sleep_seconds"] == 0.5
    assert sleep_calls == [0.5]


def test_request_with_retry_timeout_then_success_updates_attempt_summary(monkeypatch) -> None:
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def fake_urlopen(request, timeout):
        del request, timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return DummyResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"ok": true}',
        )

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(common.random, "uniform", lambda _start, _end: 0.0)

    result = common.request_with_retry(
        url="https://example.com",
        params=None,
        timeout_seconds=1.0,
        max_attempts=3,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
    )
    summary = summarize_attempts(result.attempts)

    assert result.status_code == 200
    assert result.error is None
    assert summary["retry_count"] == 1
    assert summary["timeout_count"] == 1
    assert sleep_calls == [0.5]


def test_request_with_retry_retries_invalid_payload_until_cap(monkeypatch) -> None:
    sleep_calls: list[float] = []

    def fake_urlopen(request, timeout):
        del request, timeout
        return DummyResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b"not-json",
        )

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(common.random, "uniform", lambda _start, _end: 0.0)

    result = common.request_with_retry(
        url="https://example.com",
        params=None,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        response_retry_reason=lambda _status_code, body: (
            "invalid_json" if common.decode_json_payload(body) is None else None
        ),
    )

    assert result.status_code == 200
    assert len(result.attempts) == 2
    assert result.attempts[0]["error"] == "invalid_json"
    assert result.error == {"type": "response_error", "message": "invalid_json"}
    assert sleep_calls == [0.5]


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


def test_build_snapshot_keeps_collected_at_kst_opt_in_only() -> None:
    result = common.RequestResult(
        final_url="https://example.com",
        status_code=200,
        headers={"content-type": "application/json"},
        body=b'{"ok": true}',
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": 200}],
        error=None,
    )

    snapshot = common.build_snapshot(
        probe_name="example",
        collected_at_utc="2026-03-06T21:45:56Z",
        request_url="https://example.com",
        request_params=None,
        timeout_seconds=10.0,
        result=result,
        payload_excerpt_or_json={"ok": True},
    )
    snapshot_with_kst = common.build_snapshot(
        probe_name="example",
        collected_at_utc="2026-03-06T21:45:56Z",
        request_url="https://example.com",
        request_params=None,
        timeout_seconds=10.0,
        result=result,
        payload_excerpt_or_json={"ok": True},
        include_collected_at_kst=True,
    )

    assert "collected_at_kst" not in snapshot
    assert snapshot_with_kst["collected_at_kst"] == "2026-03-07T06:45:56+09:00"


def test_save_snapshot_uses_timestamp_name_by_default(tmp_path) -> None:
    output_path = common.save_snapshot(
        out_dir=tmp_path,
        probe_name="example",
        snapshot={"collected_at_utc": "2026-03-06T21:41:41Z"},
    )

    assert output_path == tmp_path / "example" / "20260306T214141Z.json"
    assert output_path.exists()


def test_save_snapshot_uses_fixed_basename_when_opted_in(tmp_path) -> None:
    output_path = common.save_snapshot(
        out_dir=tmp_path,
        probe_name="example",
        snapshot={"collected_at_utc": "2026-03-06T21:41:41Z"},
        fixed_basename="representative.json",
    )

    assert output_path == tmp_path / "example" / "representative.json"
    assert output_path.exists()
