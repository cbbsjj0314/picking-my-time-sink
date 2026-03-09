from __future__ import annotations

import json

import pytest

from steam.probe.common import RequestResult
from steam.probe.probe_getapplist import (
    APP_EXCERPT_COUNT,
    REDACTED_VALUE,
    REQUEST_URL,
    build_probe_snapshot,
    build_request_params,
    redact_request_params,
    resolve_steam_api_key,
    summarize_getapplist_payload,
)


def test_resolve_steam_api_key_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STEAM_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="STEAM_API_KEY is required"):
        resolve_steam_api_key()


def test_request_params_keep_key_field_but_redact_value() -> None:
    live_params = build_request_params("real-secret-key")

    assert live_params == {"key": "real-secret-key"}
    assert redact_request_params(live_params) == {"key": REDACTED_VALUE}


def test_summarize_getapplist_payload_is_deterministic_and_bounded() -> None:
    apps = [{"appid": index, "name": f"app-{index}"} for index in range(1, 9)]
    payload = {
        "response": {
            "apps": apps,
            "app_count": 999,
            "have_more_results": True,
            "last_appid": 424242,
        }
    }

    summary = summarize_getapplist_payload(payload)

    assert summary == {
        "top_level_keys": ["app_count", "apps", "have_more_results", "last_appid"],
        "app_count": 999,
        "pagination": {
            "have_more_results": True,
            "last_appid": 424242,
        },
        "apps_excerpt": apps[:APP_EXCERPT_COUNT],
    }


def test_build_probe_snapshot_never_serializes_real_api_key() -> None:
    real_api_key = "real-secret-key"
    result = RequestResult(
        final_url=f"{REQUEST_URL}?key={real_api_key}",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(
            {
                "response": {
                    "apps": [
                        {"appid": 10, "name": "App 10"},
                        {"appid": 20, "name": "App 20"},
                    ],
                    "have_more_results": False,
                }
            }
        ).encode("utf-8"),
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": 200}],
        error=None,
    )

    snapshot = build_probe_snapshot(
        result=result,
        timeout_seconds=10.0,
        request_params=build_request_params(real_api_key),
    )
    serialized = json.dumps(snapshot, sort_keys=True)

    assert snapshot["request"]["url"] == REQUEST_URL
    assert snapshot["request"]["params"] == {"key": REDACTED_VALUE}
    assert REDACTED_VALUE in serialized
    assert real_api_key not in serialized
