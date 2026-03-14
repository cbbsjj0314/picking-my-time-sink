from __future__ import annotations

import json
from pathlib import Path

import pytest

from steam.ingest import fetch_app_catalog_weekly
from steam.probe.common import RequestResult


def make_result(body: dict[str, object]) -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(body).encode("utf-8"),
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": 200}],
        error=None,
    )


def test_build_parser_uses_app_catalog_only_defaults() -> None:
    parser = fetch_app_catalog_weekly.build_parser()
    args = parser.parse_args([])

    assert args.checkpoint_path == fetch_app_catalog_weekly.DEFAULT_CHECKPOINT_PATH
    assert args.output_path is None
    assert args.max_results is None
    assert args.meta_path is None


def test_merge_normalized_catalog_rows_last_seen_wins_and_sorts() -> None:
    merged = fetch_app_catalog_weekly.merge_normalized_catalog_rows(
        [
            {"appid": 20, "name": "older-20", "last_modified": 1, "price_change_number": 1},
            {"appid": 10, "name": "ten", "last_modified": 1, "price_change_number": 1},
        ],
        [
            {"appid": 20, "name": "newer-20", "last_modified": 2, "price_change_number": 2},
            {"appid": 30, "name": "thirty", "last_modified": 3, "price_change_number": 3},
        ],
    )

    assert merged == [
        {"appid": 10, "name": "ten", "last_modified": 1, "price_change_number": 1},
        {"appid": 20, "name": "newer-20", "last_modified": 2, "price_change_number": 2},
        {"appid": 30, "name": "thirty", "last_modified": 3, "price_change_number": 3},
    ]


@pytest.mark.parametrize(
    ("payload", "expected_reason"),
    [
        ({}, "invalid_response_container"),
        ({"response": {"apps": {}, "have_more_results": False}}, "invalid_apps"),
        ({"response": {"apps": [], "have_more_results": "yes"}}, "invalid_pagination_flag"),
        ({"response": {"apps": [], "have_more_results": True}}, "invalid_pagination_cursor"),
    ],
)
def test_getapplist_response_retry_reason_covers_pagination_anomalies(
    payload: dict[str, object],
    expected_reason: str,
) -> None:
    reason = fetch_app_catalog_weekly.getapplist_response_retry_reason(
        200,
        json.dumps(payload).encode("utf-8"),
    )
    assert reason == expected_reason


def test_run_fetches_paginated_catalog_and_writes_completed_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "snapshot.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    meta_path = tmp_path / "meta.json"
    responses = iter(
        [
            make_result(
                {
                    "response": {
                        "apps": [
                            {"appid": 20, "name": "Twenty", "last_modified": 2},
                            {"appid": 10, "name": "Ten", "last_modified": 1},
                        ],
                        "have_more_results": True,
                        "last_appid": 20,
                    }
                }
            ),
            make_result(
                {
                    "response": {
                        "apps": [
                            {"appid": 30, "name": "Thirty", "last_modified": 3},
                        ],
                        "have_more_results": False,
                    }
                }
            ),
        ]
    )

    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        fetch_app_catalog_weekly,
        "request_with_retry",
        lambda **kwargs: next(responses),
    )

    rows = fetch_app_catalog_weekly.run(
        output_path=snapshot_path,
        checkpoint_path=checkpoint_path,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        max_results=1000,
        meta_path=meta_path,
    )

    assert rows == [
        {"appid": 10, "name": "Ten", "last_modified": 1, "price_change_number": None},
        {"appid": 20, "name": "Twenty", "last_modified": 2, "price_change_number": None},
        {"appid": 30, "name": "Thirty", "last_modified": 3, "price_change_number": None},
    ]

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["status"] == "completed"
    assert checkpoint["last_appid"] is None
    assert checkpoint["snapshot_path"] == str(snapshot_path)
    assert snapshot_path.exists()
    assert meta_path.exists()


def test_run_single_page_terminal_page_writes_completed_not_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "snapshot.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    recorded_states: list[dict[str, object]] = []
    real_save_checkpoint = fetch_app_catalog_weekly.save_checkpoint

    def recording_save_checkpoint(path: Path, state: dict[str, object]) -> Path:
        recorded_states.append(dict(state))
        return real_save_checkpoint(path, state)

    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        fetch_app_catalog_weekly,
        "request_with_retry",
        lambda **kwargs: make_result(
            {
                "response": {
                    "apps": [{"appid": 2, "name": "Two", "last_modified": 2}],
                    "have_more_results": False,
                }
            }
        ),
    )
    monkeypatch.setattr(fetch_app_catalog_weekly, "save_checkpoint", recording_save_checkpoint)

    rows = fetch_app_catalog_weekly.run(
        output_path=snapshot_path,
        checkpoint_path=checkpoint_path,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        max_results=None,
        meta_path=tmp_path / "meta.json",
    )

    assert rows == [{"appid": 2, "name": "Two", "last_modified": 2, "price_change_number": None}]
    assert [(state["status"], state["last_appid"]) for state in recorded_states] == [
        ("in_progress", None),
        ("completed", None),
    ]


def test_run_multi_page_terminal_page_writes_completed_not_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "snapshot.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    recorded_states: list[dict[str, object]] = []
    real_save_checkpoint = fetch_app_catalog_weekly.save_checkpoint
    responses = iter(
        [
            make_result(
                {
                    "response": {
                        "apps": [{"appid": 10, "name": "Ten", "last_modified": 1}],
                        "have_more_results": True,
                        "last_appid": 10,
                    }
                }
            ),
            make_result(
                {
                    "response": {
                        "apps": [{"appid": 20, "name": "Twenty", "last_modified": 2}],
                        "have_more_results": False,
                    }
                }
            ),
        ]
    )

    def recording_save_checkpoint(path: Path, state: dict[str, object]) -> Path:
        recorded_states.append(dict(state))
        return real_save_checkpoint(path, state)

    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        fetch_app_catalog_weekly,
        "request_with_retry",
        lambda **kwargs: next(responses),
    )
    monkeypatch.setattr(fetch_app_catalog_weekly, "save_checkpoint", recording_save_checkpoint)

    fetch_app_catalog_weekly.run(
        output_path=snapshot_path,
        checkpoint_path=checkpoint_path,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        max_results=None,
        meta_path=tmp_path / "meta.json",
    )

    assert [(state["status"], state["last_appid"]) for state in recorded_states] == [
        ("in_progress", None),
        ("in_progress", 10),
        ("completed", None),
    ]


def test_run_resumes_from_in_progress_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "snapshot.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    meta_path = tmp_path / "meta.json"
    fetch_app_catalog_weekly.write_jsonl(
        snapshot_path,
        [{"appid": 10, "name": "Ten", "last_modified": 1, "price_change_number": None}],
    )
    fetch_app_catalog_weekly.save_checkpoint(
        checkpoint_path,
        fetch_app_catalog_weekly.build_checkpoint(
            status="in_progress",
            started_at_utc="2026-03-15T00:00:00Z",
            snapshot_path=snapshot_path,
            last_appid=10,
        ),
    )
    captured_params: list[dict[str, str | int]] = []

    def fake_request_with_retry(**kwargs) -> RequestResult:
        captured_params.append(dict(kwargs["params"]))
        return make_result(
            {
                "response": {
                    "apps": [{"appid": 20, "name": "Twenty", "last_modified": 2}],
                    "have_more_results": False,
                }
            }
        )

    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")
    monkeypatch.setattr(fetch_app_catalog_weekly, "request_with_retry", fake_request_with_retry)

    rows = fetch_app_catalog_weekly.run(
        output_path=None,
        checkpoint_path=checkpoint_path,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        max_results=1000,
        meta_path=meta_path,
    )

    assert captured_params == [{"key": "fake-test-key", "last_appid": 10, "max_results": 1000}]
    assert rows == [
        {"appid": 10, "name": "Ten", "last_modified": 1, "price_change_number": None},
        {"appid": 20, "name": "Twenty", "last_modified": 2, "price_change_number": None},
    ]


def test_run_fails_for_corrupt_resume_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    missing_snapshot = tmp_path / "missing.jsonl"
    fetch_app_catalog_weekly.save_checkpoint(
        checkpoint_path,
        fetch_app_catalog_weekly.build_checkpoint(
            status="in_progress",
            started_at_utc="2026-03-15T00:00:00Z",
            snapshot_path=missing_snapshot,
            last_appid=20,
        ),
    )
    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")

    with pytest.raises(ValueError, match="Checkpoint snapshot missing"):
        fetch_app_catalog_weekly.run(
            output_path=None,
            checkpoint_path=checkpoint_path,
            timeout_seconds=1.0,
            max_attempts=2,
            backoff_base_seconds=0.5,
            jitter_max_seconds=0.1,
            max_backoff_seconds=2.0,
            max_results=1000,
            meta_path=tmp_path / "meta.json",
        )


def test_run_completed_checkpoint_starts_fresh_and_keeps_previous_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_snapshot = tmp_path / "old.jsonl"
    old_snapshot.write_text('{"appid":1}\n', encoding="utf-8")
    checkpoint_path = tmp_path / "checkpoint.json"
    fetch_app_catalog_weekly.save_checkpoint(
        checkpoint_path,
        fetch_app_catalog_weekly.build_checkpoint(
            status="completed",
            started_at_utc="2026-03-15T00:00:00Z",
            snapshot_path=old_snapshot,
            last_appid=None,
        ),
    )
    new_snapshot = tmp_path / "new.jsonl"
    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        fetch_app_catalog_weekly,
        "request_with_retry",
        lambda **kwargs: make_result(
            {
                "response": {
                    "apps": [{"appid": 2, "name": "Two", "last_modified": 2}],
                    "have_more_results": False,
                }
            }
        ),
    )

    rows = fetch_app_catalog_weekly.run(
        output_path=new_snapshot,
        checkpoint_path=checkpoint_path,
        timeout_seconds=1.0,
        max_attempts=2,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.1,
        max_backoff_seconds=2.0,
        max_results=None,
        meta_path=tmp_path / "meta.json",
    )

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert rows == [{"appid": 2, "name": "Two", "last_modified": 2, "price_change_number": None}]
    assert checkpoint["status"] == "completed"
    assert checkpoint["started_at_utc"] != "2026-03-15T00:00:00Z"
    assert checkpoint["snapshot_path"] == str(new_snapshot)
    assert old_snapshot.read_text(encoding="utf-8") == '{"appid":1}\n'


def test_run_is_rerun_safe_for_same_paginated_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def run_once(
        snapshot_path: Path,
        checkpoint_path: Path,
        meta_path: Path,
    ) -> tuple[list[dict[str, object]], dict[str, object], str]:
        responses = iter(
            [
                make_result(
                    {
                        "response": {
                            "apps": [{"appid": 20, "name": "Twenty", "last_modified": 2}],
                            "have_more_results": True,
                            "last_appid": 20,
                        }
                    }
                ),
                make_result(
                    {
                        "response": {
                            "apps": [{"appid": 10, "name": "Ten", "last_modified": 1}],
                            "have_more_results": False,
                        }
                    }
                ),
            ]
        )
        monkeypatch.setattr(
            fetch_app_catalog_weekly,
            "request_with_retry",
            lambda **kwargs: next(responses),
        )
        rows = fetch_app_catalog_weekly.run(
            output_path=snapshot_path,
            checkpoint_path=checkpoint_path,
            timeout_seconds=1.0,
            max_attempts=2,
            backoff_base_seconds=0.5,
            jitter_max_seconds=0.1,
            max_backoff_seconds=2.0,
            max_results=1000,
            meta_path=meta_path,
        )
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        snapshot_text = snapshot_path.read_text(encoding="utf-8")
        return rows, checkpoint, snapshot_text

    monkeypatch.setenv("STEAM_API_KEY", "fake-test-key")

    first = run_once(
        tmp_path / "snapshot1.jsonl",
        tmp_path / "checkpoint1.json",
        tmp_path / "meta1.json",
    )
    second = run_once(
        tmp_path / "snapshot2.jsonl",
        tmp_path / "checkpoint2.json",
        tmp_path / "meta2.json",
    )

    assert first[0] == second[0]
    assert first[1]["status"] == second[1]["status"] == "completed"
    assert first[1]["last_appid"] is None
    assert second[1]["last_appid"] is None
    assert first[2] == second[2]
