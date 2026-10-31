from __future__ import annotations

import email.message
import http.client
import io
import logging
import urllib.error
from collections.abc import Callable

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


# Synthetic detail that must never reach error messages or logs (R-5).
RAW_DETAIL = "raw-peer-detail"


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        read_error: BaseException | None = None,
    ) -> None:
        self._status_code = status_code
        self.headers = email.message.Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self._body = body
        self._read_error = read_error

    def getcode(self) -> int:
        return self._status_code

    def read(self) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:  # noqa: ANN001
        return False


class FailingBody:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    def read(self, *_: object) -> bytes:
        raise self._error

    def close(self) -> None:
        pass


def http_error(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    read_error: BaseException | None = None,
) -> urllib.error.HTTPError:
    message = email.message.Message()
    for key, value in (headers or {}).items():
        message[key] = value
    fp = FailingBody(read_error) if read_error is not None else io.BytesIO(body)
    return urllib.error.HTTPError("https://example.com/api", status_code, "error", message, fp)


def incomplete_read() -> http.client.IncompleteRead:
    # The partial bytes are a complete JSON document, so using them would look like success.
    return http.client.IncompleteRead(b'{"ok": true}', 1000)


TRANSPORT_ERRORS = [
    pytest.param(incomplete_read, "IncompleteRead", id="incomplete_read"),
    pytest.param(
        lambda: http.client.RemoteDisconnected(RAW_DETAIL),
        "RemoteDisconnected",
        id="remote_disconnected",
    ),
    pytest.param(
        lambda: ConnectionResetError(104, RAW_DETAIL),
        "ConnectionResetError",
        id="connection_reset",
    ),
]


def install_sequence(
    monkeypatch: pytest.MonkeyPatch,
    steps: list[Callable[[], FakeResponse]],
) -> list[float]:
    """Serve one step per urlopen call; a step either returns a response or raises."""

    sleeps: list[float] = []
    remaining = list(steps)

    def fake_urlopen(request, timeout):  # noqa: ANN001
        del request, timeout
        return remaining.pop(0)()

    monkeypatch.setattr(common.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(common.time, "sleep", sleeps.append)
    return sleeps


def raise_(make_error: Callable[[], BaseException]) -> Callable[[], FakeResponse]:
    def step() -> FakeResponse:
        raise make_error()

    return step


def respond(response: FakeResponse) -> Callable[[], FakeResponse]:
    return lambda: response


def call(max_attempts: int, **kwargs: object) -> common.RequestResult:
    return common.request_with_retry(
        url="https://example.com/api",
        params={"appid": 730, "key": "secret-key"},
        timeout_seconds=1.0,
        max_attempts=max_attempts,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.0,
        max_backoff_seconds=8.0,
        **kwargs,
    )


def assert_transport_final(result: common.RequestResult, error: dict[str, str]) -> None:
    assert result.status_code is None
    assert result.headers == {}
    assert result.body == b""
    assert result.error == error


@pytest.mark.parametrize("make_error, error_name", TRANSPORT_ERRORS)
@pytest.mark.parametrize("raised_from", ["urlopen", "read"])
def test_transport_failure_is_retried_and_returned_as_url_error_class_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_error: Callable[[], BaseException],
    error_name: str,
    raised_from: str,
) -> None:
    def step() -> FakeResponse:
        if raised_from == "urlopen":
            raise make_error()
        return FakeResponse(headers={"X-Partial": "1"}, read_error=make_error())

    sleeps = install_sequence(monkeypatch, [step] * 3)
    caplog.set_level(logging.WARNING)

    result = call(3)

    assert_transport_final(result, {"type": "url_error", "message": error_name})
    assert sleeps == [0.5, 1.0]
    assert [attempt["error"] for attempt in result.attempts] == [error_name] * 3
    assert [attempt["status_code"] for attempt in result.attempts] == [None] * 3
    assert [attempt["sleep_seconds"] for attempt in result.attempts] == [0.5, 1.0, 0.0]
    assert error_name in caplog.text
    assert RAW_DETAIL not in caplog.text
    assert "bytes read" not in caplog.text
    assert "secret-key" not in caplog.text


@pytest.mark.parametrize("make_error, error_name", TRANSPORT_ERRORS)
def test_transport_failure_then_success_returns_the_successful_attempt(
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    error_name: str,
) -> None:
    sleeps = install_sequence(
        monkeypatch,
        [
            respond(FakeResponse(read_error=make_error())),
            respond(FakeResponse(headers={"Content-Type": "application/json"}, body=b'{"a": 1}')),
        ],
    )

    result = call(3)

    assert result.status_code == 200
    assert result.headers == {"Content-Type": "application/json"}
    assert result.body == b'{"a": 1}'
    assert result.error is None
    assert [attempt["error"] for attempt in result.attempts] == [error_name, None]
    assert sleeps == [0.5]


@pytest.mark.parametrize(
    "make_error, error_name",
    [
        pytest.param(incomplete_read, "IncompleteRead", id="incomplete_read"),
        pytest.param(
            lambda: ConnectionResetError(104, RAW_DETAIL), "ConnectionResetError", id="reset"
        ),
        pytest.param(lambda: TimeoutError(RAW_DETAIL), "TimeoutError", id="timeout"),
    ],
)
def test_http_error_body_read_failure_keeps_status_and_headers_with_empty_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_error: Callable[[], BaseException],
    error_name: str,
) -> None:
    sleeps = install_sequence(
        monkeypatch,
        [raise_(lambda: http_error(503, headers={"Retry-After": "5"}, read_error=make_error()))]
        * 2,
    )
    caplog.set_level(logging.WARNING)

    result = call(2)

    assert result.status_code == 503
    assert result.headers == {"Retry-After": "5"}
    assert result.body == b""
    assert result.error == {"type": "http_error", "message": "HTTP 503"}
    assert [attempt["error"] for attempt in result.attempts] == ["HTTP 503", "HTTP 503"]
    assert sleeps == [0.5]
    assert "Failed to read HTTP error body" in caplog.text
    assert error_name in caplog.text
    assert RAW_DETAIL not in caplog.text
    assert "bytes read" not in caplog.text
    assert "secret-key" not in caplog.text


@pytest.mark.parametrize(
    "status_code, retryable_status_codes, expected_calls",
    [
        pytest.param(429, None, 3, id="429_default"),
        pytest.param(500, None, 3, id="500_default"),
        pytest.param(404, None, 1, id="404_default"),
        pytest.param(404, {404}, 3, id="404_opt_in"),
    ],
)
def test_http_error_body_read_failure_keeps_status_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    retryable_status_codes: set[int] | None,
    expected_calls: int,
) -> None:
    install_sequence(
        monkeypatch,
        [raise_(lambda: http_error(status_code, read_error=ConnectionResetError(104, RAW_DETAIL)))]
        * 3,
    )

    result = call(3, retryable_status_codes=retryable_status_codes)

    assert len(result.attempts) == expected_calls
    assert result.status_code == status_code
    assert result.body == b""
    assert result.error == {"type": "http_error", "message": f"HTTP {status_code}"}


def rejected_payload(_status_code: int | None, body: bytes) -> str | None:
    return "rejected_payload" if body == b'{"rejected": true}' else None


@pytest.mark.parametrize(
    "first_step, kwargs",
    [
        pytest.param(
            raise_(lambda: http_error(500, headers={"X-Prev": "1"}, body=b"previous-500-body")),
            {},
            id="http_500",
        ),
        pytest.param(
            respond(FakeResponse(headers={"X-Prev": "1"}, body=b'{"rejected": true}')),
            {"response_retry_reason": rejected_payload},
            id="response_error",
        ),
    ],
)
@pytest.mark.parametrize(
    "final_step, expected_error",
    [
        pytest.param(
            respond(FakeResponse(read_error=incomplete_read())),
            {"type": "url_error", "message": "IncompleteRead"},
            id="incomplete_read",
        ),
        pytest.param(
            raise_(lambda: ConnectionResetError(104, RAW_DETAIL)),
            {"type": "url_error", "message": "ConnectionResetError"},
            id="connection_reset",
        ),
        pytest.param(
            raise_(lambda: urllib.error.URLError("unreachable")),
            {"type": "url_error", "message": "unreachable"},
            id="existing_url_error",
        ),
        pytest.param(
            raise_(lambda: urllib.error.URLError(TimeoutError("timed out"))),
            {"type": "timeout", "message": "timed out"},
            id="existing_url_error_timeout",
        ),
        pytest.param(
            raise_(lambda: TimeoutError("timed out")),
            {"type": "timeout", "message": "timed out"},
            id="existing_timeout",
        ),
    ],
)
def test_final_transport_failure_drops_previous_attempt_metadata(
    monkeypatch: pytest.MonkeyPatch,
    first_step: Callable[[], FakeResponse],
    kwargs: dict[str, object],
    final_step: Callable[[], FakeResponse],
    expected_error: dict[str, str],
) -> None:
    install_sequence(monkeypatch, [first_step, final_step])

    result = call(2, **kwargs)

    assert_transport_final(result, expected_error)
    assert result.attempts[0]["status_code"] in {200, 500}
    assert result.attempts[1]["status_code"] is None


@pytest.mark.parametrize("make_error, error_name", TRANSPORT_ERRORS)
def test_transport_failure_then_http_error_returns_the_http_error_attempt(
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    error_name: str,
) -> None:
    install_sequence(
        monkeypatch,
        [
            raise_(make_error),
            raise_(lambda: http_error(502, headers={"X-Final": "1"}, body=b"final-502-body")),
        ],
    )

    result = call(2)

    assert result.status_code == 502
    assert result.headers == {"X-Final": "1"}
    assert result.body == b"final-502-body"
    assert result.error == {"type": "http_error", "message": "HTTP 502"}
    assert [attempt["error"] for attempt in result.attempts] == [error_name, "HTTP 502"]


@pytest.mark.parametrize("max_attempts", [1, 3])
def test_truncated_http_200_is_never_a_successful_result(
    monkeypatch: pytest.MonkeyPatch,
    max_attempts: int,
) -> None:
    previous = respond(FakeResponse(body=b'{"rejected": true}'))
    truncated = respond(FakeResponse(read_error=incomplete_read()))
    steps = [truncated] if max_attempts == 1 else [previous, truncated, truncated]
    install_sequence(monkeypatch, steps)

    result = call(max_attempts, response_retry_reason=rejected_payload)

    assert_transport_final(result, {"type": "url_error", "message": "IncompleteRead"})
    assert len(result.attempts) == max_attempts
