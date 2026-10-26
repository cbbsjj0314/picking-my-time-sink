from __future__ import annotations

import email.message
import io
import urllib.error

import pytest

from steam.probe import common


def rate_limited_error(url: str) -> urllib.error.HTTPError:
    headers = email.message.Message()
    headers["Retry-After"] = "30"
    return urllib.error.HTTPError(url, 429, "Too Many Requests", headers, io.BytesIO(b""))


def test_shared_retry_keeps_exponential_backoff_and_ignores_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CCU, reviews, and other shared callers keep their pre-existing retry behavior."""

    sleeps: list[float] = []
    calls: list[str] = []

    def always_rate_limited(request, timeout):  # noqa: ANN001
        calls.append(request.full_url)
        raise rate_limited_error(request.full_url)

    monkeypatch.setattr(common.urllib.request, "urlopen", always_rate_limited)
    monkeypatch.setattr(common.time, "sleep", sleeps.append)

    result = common.request_with_retry(
        url="https://example.com/api",
        params={"appid": 730},
        timeout_seconds=1.0,
        max_attempts=4,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.0,
        max_backoff_seconds=8.0,
    )

    assert len(calls) == 4
    assert sleeps == [0.5, 1.0, 2.0]
    assert result.status_code == 429
    assert result.headers.get("Retry-After") == "30"
    assert result.error == {"type": "http_error", "message": "HTTP 429"}
    assert [attempt["sleep_seconds"] for attempt in result.attempts] == [0.5, 1.0, 2.0, 0.0]
