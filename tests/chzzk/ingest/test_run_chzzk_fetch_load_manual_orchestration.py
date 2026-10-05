from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from chzzk.ingest import run_chzzk_fetch_load_manual_orchestration as orch
from chzzk.ingest import run_chzzk_recurring_write_path as recurring
from chzzk.ingest import run_chzzk_regular_write_path as regular
from chzzk.probe import live_list_temporal_probe as probe

SENSITIVE_CATEGORY_NAME = "Sensitive Synthetic Category Name"
SENSITIVE_CATEGORY_ID = "sensitive-category-id"
SENSITIVE_CHANNEL_NAME = "Sensitive Synthetic Channel Name"
SENSITIVE_CHANNEL_ID = "sensitive-channel-id"
SENSITIVE_LIVE_TITLE = "Sensitive Live Title"
SENSITIVE_THUMBNAIL = "https://example.invalid/sensitive-thumbnail.jpg"
SENSITIVE_CREDENTIAL = "credential-like-sentinel-secret"
SENSITIVE_DB_VALUE = "postgres-secret-sentinel"
SENSITIVE_CONNINFO = "host=private-host dbname=private-db user=private-user"
SENSITIVE_PRIVATE_PATH = "/tmp/private/chzzk/raw/page-001.json"
SENSITIVE_API_BODY = "raw api body sentinel"
SCHEDULER_TASK_NAME = "LOCAL_SCHEDULER_TASK_SENTINEL_SHOULD_NOT_APPEAR"


def env(*, chzzk: bool = True, db: bool = True) -> dict[str, str]:
    values: dict[str, str] = {}
    if chzzk:
        values.update(
            {
                "CHZZK_CLIENT_ID": "client-id",
                "CHZZK_CLIENT_SECRET": SENSITIVE_CREDENTIAL,
            }
        )
    if db:
        values.update(
            {
                "POSTGRES_DB": SENSITIVE_DB_VALUE,
                "POSTGRES_HOST": "private-host",
                "POSTGRES_PASSWORD": SENSITIVE_DB_VALUE,
                "POSTGRES_USER": "private-user",
            }
        )
    return values


def relation_exists() -> dict[str, dict[str, Any]]:
    return {
        "category": {
            "checked": True,
            "ddl_ref": regular.CATEGORY_DDL_REF,
            "relation": regular.CATEGORY_RELATION,
            "role": "category",
            "status": "exists",
        },
        "channel": {
            "checked": True,
            "ddl_ref": regular.CHANNEL_DDL_REF,
            "relation": regular.CHANNEL_RELATION,
            "role": "channel",
            "status": "exists",
        },
    }


def write_probe_artifacts(output_dir: Path, run_id: str) -> None:
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_probe_summary(output_dir, run_id)
    raw_row = {
        "category_name": SENSITIVE_CATEGORY_NAME,
        "channel_id": SENSITIVE_CHANNEL_ID,
        "channel_name": SENSITIVE_CHANNEL_NAME,
        "chzzk_category_id": SENSITIVE_CATEGORY_ID,
        "live_title": SENSITIVE_LIVE_TITLE,
        "thumbnail": SENSITIVE_THUMBNAIL,
    }
    (run_dir / "category-result.jsonl").write_text(
        json.dumps(raw_row, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "channel-result.jsonl").write_text(
        json.dumps(raw_row, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_probe_summary(
    output_dir: Path,
    run_id: str,
    *,
    failure_kind: str | None = None,
    result_status: str = "category_results_available",
    run_status: str = "success",
) -> None:
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    failure = None
    if failure_kind is not None:
        failure = {
            "http_status_code": 500,
            "kind": failure_kind,
            "message": SENSITIVE_API_BODY,
            "page_index": 1,
            "pages_fetched_before_failure": 0,
            "retryable": True,
        }
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "category_result_path": SENSITIVE_PRIVATE_PATH,
                "category_result_rows": 0 if failure_kind is not None else 1,
                "channel_result_path": SENSITIVE_PRIVATE_PATH,
                "channel_result_rows": 0 if failure_kind is not None else 1,
                "coverage": {"status": "observed_bucket_only"},
                "failure": failure,
                "pagination": {
                    "bounded_page_cutoff": failure_kind is None,
                    "last_page_next_present": failure_kind is None,
                    "pages_fetched": 0 if failure_kind is not None else 3,
                    "pages_requested": 3,
                },
                "raw_page_dir": SENSITIVE_PRIVATE_PATH,
                "result_status": result_status,
                "run_status": run_status,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def fake_fetch(events: list[str], probe_output_dir: Path) -> orch.Fetcher:
    def fetcher(
        *,
        output_dir: Path,
        run_id: str,
        pages: int,
        size: int,
        base_url: str,
        timeout: float,
        environ: dict[str, str],
    ) -> dict[str, Any]:
        del base_url, timeout
        assert output_dir == probe_output_dir
        assert pages == 3
        assert size == 20
        assert environ["CHZZK_CLIENT_SECRET"] == SENSITIVE_CREDENTIAL
        events.append(f"fetch:{run_id}")
        write_probe_artifacts(output_dir, run_id)
        return {"run_status": "success"}

    return fetcher


def recurring_result(
    *,
    mode: str,
    status: str = "success",
    failure_class: str | None = None,
) -> dict[str, Any]:
    loaded = mode == recurring.GUARDED_WRITE_MODE
    return {
        "api_read_smoke": {
            "enabled": True,
            "failure_class": "api_read_smoke_request_failed",
            "http_status": None,
            "raw_body": SENSITIVE_API_BODY,
            "status": "failed",
        },
        "category": {
            "category_name": SENSITIVE_CATEGORY_NAME,
            "committed_row_count": 1 if loaded else 0,
            "input_path": SENSITIVE_PRIVATE_PATH,
            "input_row_count": 1,
            "load_attempted": loaded,
            "planned_upsert_attempt_count": 1,
            "status": "loaded" if loaded else "dry_run_planned",
            "valid_row_count": 1,
        },
        "channel": {
            "channel_id": SENSITIVE_CHANNEL_ID,
            "channel_name": SENSITIVE_CHANNEL_NAME,
            "committed_row_count": 1 if loaded and status == "success" else 0,
            "input_row_count": 1,
            "load_attempted": loaded,
            "planned_upsert_attempt_count": 1,
            "status": "loaded" if loaded and status == "success" else "load_failed",
            "valid_row_count": 1,
        },
        "failure_class": failure_class,
        "mode": mode,
        "partial_success": status == "partial_success",
        "result_ref": "safe-run/result.json",
        "scheduler_task": SCHEDULER_TASK_NAME,
        "status": status,
        "success": status in {"success", "partial_success"},
    }


def fake_recurring(events: list[str]) -> orch.RecurringRunner:
    def runner(**kwargs: Any) -> dict[str, Any]:
        write_enabled = bool(kwargs["write_enabled"])
        probe_run_dir = kwargs["probe_run_dir"]
        events.append(f"recurring:{write_enabled}:{probe_run_dir.name}")
        return recurring_result(
            mode=recurring.GUARDED_WRITE_MODE if write_enabled else recurring.DRY_RUN_MODE
        )

    return runner


def fake_relation(events: list[str]) -> orch.RelationChecker:
    def checker() -> dict[str, dict[str, Any]]:
        events.append("relation")
        return relation_exists()

    return checker


def run(
    tmp_path: Path,
    *,
    events: list[str] | None = None,
    probe_output_dir: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    event_log = events if events is not None else []
    probe_root = probe_output_dir or tmp_path / "temporal-probe"
    return orch.run_orchestration(
        base_dir=tmp_path / "orchestration",
        probe_output_dir=probe_root,
        run_id=kwargs.pop("run_id", "orch-run-a"),
        environ=kwargs.pop("environ", env()),
        fetcher=kwargs.pop("fetcher", fake_fetch(event_log, probe_root)),
        recurring_runner=kwargs.pop("recurring_runner", fake_recurring(event_log)),
        relation_checker=kwargs.pop("relation_checker", fake_relation(event_log)),
        **kwargs,
    )


def assert_no_sensitive_leak(result: dict[str, Any], tmp_path: Path) -> None:
    result_text = json.dumps(result, sort_keys=True)
    forbidden = [
        "category_result_path",
        "channel_result_path",
        "raw_page_dir",
        "raw_body",
        "category_name",
        "channel_name",
        "channel_id",
        SENSITIVE_CATEGORY_NAME,
        SENSITIVE_CATEGORY_ID,
        SENSITIVE_CHANNEL_NAME,
        SENSITIVE_CHANNEL_ID,
        SENSITIVE_LIVE_TITLE,
        SENSITIVE_THUMBNAIL,
        SENSITIVE_CREDENTIAL,
        SENSITIVE_DB_VALUE,
        SENSITIVE_CONNINFO,
        SENSITIVE_PRIVATE_PATH,
        SENSITIVE_API_BODY,
        SCHEDULER_TASK_NAME,
        str(tmp_path),
        "/tmp/",
        "private-host",
        "private-db",
        "private-user",
    ]
    for value in forbidden:
        assert value not in result_text


def test_assert_no_sensitive_leak_allows_harmless_numeric_metadata(
    tmp_path: Path,
) -> None:
    result = {
        "duration_ms": 31,
        "finished_at_utc": "2026-05-17T13:31:05Z",
        "run_id": "safe-run-31",
        "started_at_utc": "2026-05-17T13:31:04Z",
        "status": "success",
    }

    assert_no_sensitive_leak(result, tmp_path)


def test_first_invocation_checks_credentials_db_relations_before_one_fetch(
    tmp_path: Path,
) -> None:
    events: list[str] = []

    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
    )

    assert events == [
        "relation",
        "fetch:orch-run-a",
        "recurring:False:orch-run-a",
    ]
    assert result["status"] == "success"
    assert result["action_policy"]["live_fetch_enabled"] is True
    assert result["action_policy"]["db_write_enabled"] is False
    assert result["action_policy"]["scheduler_registration_enabled"] is False
    assert result["live_fetch"]["invocation_count"] == 1
    assert result["selected_artifact_run_id"] == "orch-run-a"
    assert result["recurring_no_write_dry_run"]["status"] == "success"
    assert result["guarded_write"]["status"] == "not_requested"
    assert result["probe_summary"] == {
        "bounded_page_cutoff": True,
        "category_result_rows": 1,
        "channel_result_rows": 1,
        "coverage_status": "observed_bucket_only",
        "failure_kind": None,
        "last_page_next_present": True,
        "pages_fetched": 3,
        "pages_requested": 3,
        "result_status": "category_results_available",
        "run_status": "success",
        "status": "available",
    }
    assert_no_sensitive_leak(result, tmp_path)


def test_no_source_selected_is_hard_failure_without_side_effects(tmp_path: Path) -> None:
    events: list[str] = []

    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=False,
        from_orchestration_run_id=None,
    )

    assert events == []
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "orchestration_source_invalid"
    assert result["action_policy"]["live_fetch_enabled"] is False
    assert result["credential_preconditions"] == {"checked": False}
    assert result["db_env_preconditions"] == {"checked": False}
    assert result["relation_preconditions"] == {}
    assert result["live_fetch"]["invocation_count"] == 0
    assert result["recurring_no_write_dry_run"]["status"] == "not_started"


def test_both_sources_selected_is_hard_failure_without_side_effects(tmp_path: Path) -> None:
    events: list[str] = []

    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        from_orchestration_run_id="prior-run",
    )

    assert events == []
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "orchestration_source_invalid"
    assert result["action_policy"]["live_fetch_enabled"] is False
    assert result["credential_preconditions"] == {"checked": False}
    assert result["db_env_preconditions"] == {"checked": False}
    assert result["relation_preconditions"] == {}
    assert result["live_fetch"]["invocation_count"] == 0
    assert result["recurring_no_write_dry_run"]["status"] == "not_started"


def test_missing_db_env_blocks_live_fetch_before_relation_check(tmp_path: Path) -> None:
    events: list[str] = []

    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        environ=env(chzzk=True, db=False),
    )

    assert events == []
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "db_env_missing"
    assert result["live_fetch"]["invocation_count"] == 0


def test_missing_relation_blocks_live_fetch(tmp_path: Path) -> None:
    events: list[str] = []

    def missing_relation() -> dict[str, dict[str, Any]]:
        events.append("relation")
        results = relation_exists()
        results["channel"]["status"] = "missing"
        return results

    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        relation_checker=missing_relation,
    )

    assert events == ["relation"]
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "channel_relation_missing"
    assert result["live_fetch"]["invocation_count"] == 0


def test_probe_fetch_failure_prefers_probe_failure_over_category_artifact_missing(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    probe_root = tmp_path / "temporal-probe"

    def failing_fetcher(
        *,
        output_dir: Path,
        run_id: str,
        pages: int,
        size: int,
        base_url: str,
        timeout: float,
        environ: dict[str, str],
    ) -> dict[str, Any]:
        del pages, size, base_url, timeout, environ
        events.append(f"fetch:{run_id}")
        write_probe_summary(
            output_dir,
            run_id,
            failure_kind="http_error",
            result_status="not_generated_due_to_fetch_failure",
            run_status="failed",
        )
        return {"run_status": "failed"}

    result = run(
        tmp_path,
        events=events,
        probe_output_dir=probe_root,
        allow_live_fetch_once=True,
        fetcher=failing_fetcher,
    )

    assert events == ["relation", "fetch:orch-run-a"]
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "probe_http_error"
    assert result["artifact_checks"]["category"]["status"] == "missing"
    assert result["probe_summary"]["failure_kind"] == "http_error"
    assert result["probe_summary"]["run_status"] == "failed"
    assert result["probe_summary"]["result_status"] == "not_generated_due_to_fetch_failure"
    assert_no_sensitive_leak(result, tmp_path)


def test_missing_probe_summary_keeps_probe_summary_missing(tmp_path: Path) -> None:
    events: list[str] = []
    probe_root = tmp_path / "temporal-probe"

    def missing_summary_fetcher(
        *,
        output_dir: Path,
        run_id: str,
        pages: int,
        size: int,
        base_url: str,
        timeout: float,
        environ: dict[str, str],
    ) -> dict[str, Any]:
        del pages, size, base_url, timeout, environ
        events.append(f"fetch:{run_id}")
        (output_dir / run_id).mkdir(parents=True)
        return {"run_status": "failed"}

    result = run(
        tmp_path,
        events=events,
        probe_output_dir=probe_root,
        allow_live_fetch_once=True,
        fetcher=missing_summary_fetcher,
    )

    assert events == ["relation", "fetch:orch-run-a"]
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "probe_summary_missing"
    assert result["probe_summary"] == {"status": "unavailable"}
    assert_no_sensitive_leak(result, tmp_path)


@pytest.mark.parametrize(
    ("include_category", "expected_failure_class"),
    [
        (False, "category_artifact_missing"),
        (True, "channel_artifact_missing"),
    ],
)
def test_artifact_missing_without_fetch_failure_keeps_artifact_missing_semantics(
    tmp_path: Path,
    include_category: bool,
    expected_failure_class: str,
) -> None:
    events: list[str] = []
    probe_root = tmp_path / "temporal-probe"

    def artifact_missing_fetcher(
        *,
        output_dir: Path,
        run_id: str,
        pages: int,
        size: int,
        base_url: str,
        timeout: float,
        environ: dict[str, str],
    ) -> dict[str, Any]:
        del pages, size, base_url, timeout, environ
        events.append(f"fetch:{run_id}")
        write_probe_summary(output_dir, run_id)
        if include_category:
            (output_dir / run_id / "category-result.jsonl").write_text(
                "{}\n",
                encoding="utf-8",
            )
        return {"run_status": "success"}

    result = run(
        tmp_path,
        events=events,
        probe_output_dir=probe_root,
        allow_live_fetch_once=True,
        fetcher=artifact_missing_fetcher,
    )

    assert events == ["relation", "fetch:orch-run-a"]
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == expected_failure_class
    assert result["probe_summary"]["failure_kind"] is None
    assert result["probe_summary"]["run_status"] == "success"
    assert result["probe_summary"]["result_status"] == "category_results_available"
    assert_no_sensitive_leak(result, tmp_path)


def test_prior_artifact_validation_prefixes_probe_fetch_failure(tmp_path: Path) -> None:
    probe_root = tmp_path / "temporal-probe"
    write_probe_summary(
        probe_root,
        "probe-run-a",
        failure_kind="http_error",
        result_status="not_generated_due_to_fetch_failure",
        run_status="failed",
    )
    prior_dir = tmp_path / "orchestration" / "prior-run"
    prior_dir.mkdir(parents=True)
    (prior_dir / "result.json").write_text(
        json.dumps(
            {
                "action_policy": {
                    "db_write_enabled": False,
                    "live_fetch_enabled": True,
                    "live_fetch_invocation_limit": 1,
                    "scheduler_registration_enabled": False,
                },
                "recurring_no_write_dry_run": {
                    "mode": recurring.DRY_RUN_MODE,
                    "status": "success",
                    "success": True,
                },
                "selected_artifact_run_id": "probe-run-a",
                "status": "success",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run(
        tmp_path,
        probe_output_dir=probe_root,
        from_orchestration_run_id="prior-run",
        write_enabled=True,
        run_id="write-run",
        environ=env(chzzk=False, db=True),
    )

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "prior_probe_http_error"
    assert result["prior_result_validation"]["failure_class"] == "prior_probe_http_error"
    assert result["live_fetch"]["invocation_count"] == 0
    assert_no_sensitive_leak(result, tmp_path)


def test_from_orchestration_run_id_reuses_same_artifact_without_chzzk_credentials(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    first = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        run_id="first-run",
    )
    assert first["status"] == "success"

    second = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=False,
        from_orchestration_run_id="first-run",
        write_enabled=True,
        idempotency_rerun_enabled=True,
        run_id="write-run",
        environ=env(chzzk=False, db=True),
    )

    assert events == [
        "relation",
        "fetch:first-run",
        "recurring:False:first-run",
        "relation",
        "recurring:False:first-run",
        "recurring:True:first-run",
        "recurring:True:first-run",
    ]
    assert second["status"] == "success"
    assert second["credential_preconditions"]["status"] == "not_required"
    assert second["live_fetch"]["invocation_count"] == 0
    assert second["selected_artifact_run_id"] == "first-run"
    assert second["prior_result_validation"]["status"] == "passed"
    assert second["guarded_write"]["status"] == "success"
    assert second["idempotency_rerun"]["status"] == "success"


def test_prior_result_integrity_blocks_write_when_no_write_gate_not_successful(
    tmp_path: Path,
) -> None:
    probe_root = tmp_path / "temporal-probe"
    write_probe_artifacts(probe_root, "probe-run-a")
    prior_dir = tmp_path / "orchestration" / "prior-run"
    prior_dir.mkdir(parents=True)
    (prior_dir / "result.json").write_text(
        json.dumps(
            {
                "action_policy": {
                    "db_write_enabled": False,
                    "live_fetch_enabled": True,
                    "live_fetch_invocation_limit": 1,
                    "scheduler_registration_enabled": False,
                },
                "recurring_no_write_dry_run": {
                    "mode": recurring.DRY_RUN_MODE,
                    "status": "hard_failure",
                    "success": False,
                },
                "selected_artifact_run_id": "probe-run-a",
                "status": "hard_failure",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run(
        tmp_path,
        probe_output_dir=probe_root,
        from_orchestration_run_id="prior-run",
        write_enabled=True,
        run_id="write-run",
        environ=env(chzzk=False, db=True),
    )

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "prior_no_write_dry_run_not_successful"
    assert result["live_fetch"]["invocation_count"] == 0
    assert result["guarded_write"]["status"] == "not_started"


@pytest.mark.parametrize(
    "unsafe_run_id",
    ["../prior", "prior/run", "prior\\run", "/tmp/prior", ".."],
)
def test_from_orchestration_run_id_rejects_path_traversal(
    tmp_path: Path,
    unsafe_run_id: str,
) -> None:
    result = run(
        tmp_path,
        from_orchestration_run_id=unsafe_run_id,
        write_enabled=True,
        environ=env(chzzk=False, db=True),
    )

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "from_orchestration_run_id_invalid"
    assert result["live_fetch"]["invocation_count"] == 0


def test_prior_selected_artifact_run_id_rejects_path_traversal(tmp_path: Path) -> None:
    prior_dir = tmp_path / "orchestration" / "prior-run"
    prior_dir.mkdir(parents=True)
    (prior_dir / "result.json").write_text(
        json.dumps(
            {
                "action_policy": {
                    "db_write_enabled": False,
                    "live_fetch_enabled": True,
                    "live_fetch_invocation_limit": 1,
                    "scheduler_registration_enabled": False,
                },
                "recurring_no_write_dry_run": {
                    "mode": recurring.DRY_RUN_MODE,
                    "status": "success",
                    "success": True,
                },
                "selected_artifact_run_id": "../probe",
                "status": "success",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run(
        tmp_path,
        from_orchestration_run_id="prior-run",
        write_enabled=True,
        run_id="write-run",
        environ=env(chzzk=False, db=True),
    )

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "prior_selected_artifact_run_id_invalid"
    assert result["live_fetch"]["invocation_count"] == 0


def synthetic_live_page(next_cursor: str | None) -> dict[str, Any]:
    return {
        "code": 200,
        "content": {
            "data": [
                {
                    "categoryType": "GAME",
                    "liveCategory": "synthetic",
                    "liveCategoryValue": "Synthetic",
                    "concurrentUserCount": 7,
                    "channelId": "synthetic-channel",
                    "channelName": "Synthetic Channel",
                }
            ],
            "page": {"next": next_cursor},
        },
    }


def test_default_bounded_three_pages_remain_write_eligible_and_use_completion_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    events: list[str] = []
    anchor = probe.parse_timestamp("2026-10-05T10:29:59+09:00")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal anchor
        requests.append(request)
        anchor = probe.parse_timestamp("2026-10-05T10:30:01+09:00")
        return httpx.Response(200, json=synthetic_live_page(f"cursor-{len(requests)}"))

    client_class = httpx.Client
    monkeypatch.setattr(
        orch.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(probe, "utc_now", lambda: anchor)
    result = run(
        tmp_path,
        allow_live_fetch_once=True,
        write_enabled=True,
        fetcher=None,
        events=events,
    )

    assert orch.DEFAULT_FETCH_PAGES == 3
    assert [request.url.params.get("next") for request in requests] == [
        None,
        "cursor-1",
        "cursor-2",
    ]
    assert result["status"] == "success"
    assert events == ["relation", "recurring:False:orch-run-a", "recurring:True:orch-run-a"]
    assert result["guarded_write"]["status"] == "success"
    summary = probe.read_json(tmp_path / "temporal-probe" / "orch-run-a" / "summary.json")
    assert summary["failure"] is None
    assert summary["run_status"] == "success"
    assert summary["result_status"] == "category_results_available"
    assert summary["pagination"] == {
        "bounded_page_cutoff": True,
        "followed": True,
        "last_page_next_present": True,
        "last_page_next_type": "str",
        "pages_fetched": 3,
        "pages_requested": 3,
    }
    assert summary["collected_at"] == "2026-10-05T10:30:01+09:00"
    assert summary["bucket_time"] == "2026-10-05T10:30:00+09:00"
    assert summary["category_result_rows"] == 1
    assert summary["channel_result_rows"] == 3
    for role in ("category", "channel"):
        assert Path(summary[f"{role}_result_path"]).is_file()


@pytest.mark.parametrize(
    "termination",
    [
        "pagination_exhausted",
        "safety_cutoff",
        "deadline_exceeded",
        "pagination_loop_detected",
        "quota_http_error",
        "http_error",
        "request_error",
        "invalid_json",
        "malformed_page",
    ],
)
def test_explicit_exhaustion_keeps_lock_and_fail_closed_load_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    termination: str,
) -> None:
    events: list[str] = []
    request_count = 0

    def assert_contender_blocked() -> None:
        contender_events: list[str] = []
        contender = run(
            tmp_path, allow_live_fetch_once=True, run_id="contender", events=contender_events
        )
        assert contender_events == []
        assert contender["status"] == contender["failure_class"] == "lock_busy"
        assert orch.exit_code_for_status(contender["status"]) == orch.LOCK_BUSY_EXIT_CODE

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert_contender_blocked()
        if request_count == 2:
            if termination == "quota_http_error":
                return httpx.Response(429, text=SENSITIVE_API_BODY)
            if termination == "http_error":
                return httpx.Response(503, text=SENSITIVE_API_BODY)
            if termination == "request_error":
                raise httpx.ReadError(SENSITIVE_API_BODY)
            if termination == "invalid_json":
                return httpx.Response(200, text=SENSITIVE_API_BODY)
            if termination == "malformed_page":
                return httpx.Response(200, json={"content": SENSITIVE_API_BODY})
        cursor = (
            None
            if request_count == 2 and termination == "pagination_exhausted"
            else (
                SENSITIVE_CREDENTIAL
                if termination == "pagination_loop_detected"
                else f"cursor-{request_count}"
            )
        )
        return httpx.Response(200, json=synthetic_live_page(cursor))

    real_probe = probe.run_exhaustion_probe

    async def collect(**kwargs: Any) -> dict[str, Any]:
        return await real_probe(
            **kwargs,
            monotonic=lambda: 5 if termination == "deadline_exceeded" and request_count == 2 else 0,
        )

    def transport(*, retries: int) -> httpx.MockTransport:
        assert retries == 0
        return httpx.MockTransport(handler)

    monkeypatch.setattr(orch.httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(probe, "run_exhaustion_probe", collect)

    def runner(**kwargs: Any) -> dict[str, Any]:
        assert_contender_blocked()
        return fake_recurring(events)(**kwargs)

    result = run(
        tmp_path,
        allow_live_fetch_once=True,
        write_enabled=True,
        events=events,
        fetcher=None,
        fetch_pagination_mode="exhaustion",
        fetch_max_pages=2,
        fetch_time_budget_seconds=5,
        recurring_runner=runner,
    )

    assert request_count == 2
    assert result["probe_summary"]["pagination"] == {
        "mode": "exhaustion",
        "termination": termination,
        "requests_performed": 2,
        "pages_requested": 2,
        "time_budget_seconds": 5,
    }
    assert result["probe_summary"]["bounded_page_cutoff"] == (termination == "safety_cutoff")
    assert_no_sensitive_leak(result, tmp_path)
    if termination == "pagination_exhausted":
        assert result["status"] == "success"
        assert events == ["relation", "recurring:False:orch-run-a", "recurring:True:orch-run-a"]
    else:
        assert result["status"] == "hard_failure"
        assert result["guarded_write"]["status"] == "not_started"
        assert result["failure_class"] == f"probe_{termination}"
        assert events == ["relation"]
        for role in ("category", "channel"):
            assert not result["artifact_checks"][role]["exists"]
    lock = regular.NoOverlapLock(
        orch.build_paths(base_dir=tmp_path / "orchestration", run_id="after").lock_path
    )
    assert lock.acquire(wait_seconds=0.0)
    lock.release()


def test_approved_exhaustion_cli_preserves_anchor_multiplicity_and_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    requests: list[httpx.Request] = []
    anchor = probe.parse_timestamp("2026-10-05T10:29:59+09:00")
    real_probe = probe.run_exhaustion_probe

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal anchor
        requests.append(request)
        assert request.url.params["size"] == "20"
        anchor = probe.parse_timestamp("2026-10-05T10:30:01+09:00")
        page = synthetic_live_page(SENSITIVE_CREDENTIAL if len(requests) == 1 else None)
        page["content"]["data"][0].update(
            channelName=SENSITIVE_CHANNEL_NAME,
            liveTitle=SENSITIVE_LIVE_TITLE,
            liveCategoryValue=SENSITIVE_CATEGORY_NAME,
        )
        return httpx.Response(200, json=page)

    async def collect(**kwargs: Any) -> dict[str, Any]:
        assert isinstance(kwargs["client"], httpx.AsyncClient)
        assert kwargs["max_pages"] == 120
        assert kwargs["time_budget_seconds"] == 60
        assert kwargs["size"] == 20
        return await real_probe(**kwargs, clock=lambda: anchor, monotonic=lambda: 0)

    def transport(*, retries: int) -> httpx.MockTransport:
        assert retries == 0
        return httpx.MockTransport(handler)

    real_orchestration = orch.run_orchestration

    def orchestration(**kwargs: Any) -> dict[str, Any]:
        return real_orchestration(
            **kwargs,
            environ=env(),
            relation_checker=relation_exists,
            recurring_runner=fake_recurring([]),
        )

    monkeypatch.setattr(orch.httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(probe, "run_exhaustion_probe", collect)
    monkeypatch.setattr(orch, "run_orchestration", orchestration)
    with pytest.raises(SystemExit) as exc:
        orch.main(
            [
                "--allow-live-fetch-once",
                "--fetch-pagination-mode",
                "exhaustion",
                "--fetch-max-pages",
                "120",
                "--fetch-time-budget-seconds",
                "60",
                "--fetch-size",
                "20",
                "--base-dir",
                str(tmp_path / "orchestration"),
                "--probe-output-dir",
                str(tmp_path / "probe"),
                "--run-id",
                "approved-config",
            ]
        )
    assert exc.value.code == 0
    result = json.loads(capsys.readouterr().out)
    assert len(requests) == 2
    assert result["status"] == "success"
    assert result["recurring_no_write_dry_run"]["success"] is True
    assert result["guarded_write"]["status"] == "not_requested"
    assert result["live_fetch"]["pagination_mode"] == "exhaustion"
    assert result["live_fetch"]["pages_requested"] == 120
    assert result["probe_summary"]["pagination"] == {
        "mode": "exhaustion",
        "termination": "pagination_exhausted",
        "requests_performed": 2,
        "pages_requested": 120,
        "time_budget_seconds": 60,
    }
    assert result["probe_summary"]["last_page_next_present"] is False
    assert result["probe_summary"]["bounded_page_cutoff"] is False
    assert_no_sensitive_leak(result, tmp_path)
    run_dir = tmp_path / "probe" / "approved-config"
    categories = [
        json.loads(line) for line in (run_dir / "category-result.jsonl").read_text().splitlines()
    ]
    channels = [
        json.loads(line) for line in (run_dir / "channel-result.jsonl").read_text().splitlines()
    ]
    assert len(categories) == 1
    assert categories[0]["live_count"] == 2
    assert len(channels) == 2
    for row in categories + channels:
        assert row["collected_at"] == "2026-10-05T10:29:59+09:00"
        assert row["bucket_time"] == "2026-10-05T10:00:00+09:00"


@pytest.mark.parametrize(
    "options",
    [
        {"fetch_pagination_mode": "unknown"},
        {"fetch_max_pages": 120},
        {"fetch_time_budget_seconds": 60},
        {"fetch_pagination_mode": "exhaustion"},
        {"fetch_pagination_mode": "exhaustion", "fetch_max_pages": 120},
        {"fetch_pagination_mode": "exhaustion", "fetch_time_budget_seconds": 60},
        *[
            {
                "fetch_pagination_mode": "exhaustion",
                "fetch_max_pages": value,
                "fetch_time_budget_seconds": 60,
            }
            for value in (0, -1, 121, True, 1.5, "120")
        ],
        *[
            {
                "fetch_pagination_mode": "exhaustion",
                "fetch_max_pages": 120,
                "fetch_time_budget_seconds": value,
            }
            for value in (0, -1, 61, True, float("inf"), float("nan"), "60")
        ],
        *[
            {
                "fetch_pagination_mode": "exhaustion",
                "fetch_max_pages": 120,
                "fetch_time_budget_seconds": 60,
                **extra,
            }
            for extra in (
                {"fetch_pages": 3},
                {"fetch_pages": 120},
                {"fetch_size": 21},
                {"fetch_size": 1},
                {"allow_live_fetch_once": False, "from_orchestration_run_id": "prior"},
            )
        ],
    ],
)
def test_invalid_fetch_selection_fails_before_fetch_or_load(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    events: list[str] = []
    result = run(
        tmp_path,
        events=events,
        write_enabled=True,
        **{"allow_live_fetch_once": True, **options},
    )
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "fetch_selection_invalid"
    assert result["live_fetch"]["invocation_count"] == 0
    assert result["guarded_write"]["status"] == "not_started"
    assert events == []


@pytest.mark.parametrize(
    "termination",
    [None, "safety_cutoff", "deadline_exceeded", "pagination_loop_detected", SENSITIVE_API_BODY],
)
def test_exhaustion_cannot_load_existing_artifacts_without_exhausted_termination(
    tmp_path: Path, termination: str | None
) -> None:
    def fetcher(**kwargs: Any) -> dict[str, Any]:
        write_probe_artifacts(kwargs["output_dir"], kwargs["run_id"])
        path = kwargs["output_dir"] / kwargs["run_id"] / "summary.json"
        summary = json.loads(path.read_text())
        summary["pagination"].update(mode="exhaustion", termination=termination)
        path.write_text(json.dumps(summary))
        return summary

    events: list[str] = []
    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        write_enabled=True,
        fetcher=fetcher,
        fetch_pagination_mode="exhaustion",
        fetch_max_pages=120,
        fetch_time_budget_seconds=60,
    )
    assert result["status"] == "hard_failure"
    assert result["failure_class"] == orch.PROBE_FETCH_FAILURE_CLASSES.get(
        termination, "probe_fetch_failed"
    )
    assert result["guarded_write"]["status"] == "not_started"
    assert events == ["relation"]
    assert_no_sensitive_leak(result, tmp_path)


def test_explicit_exhaustion_rejects_bounded_artifacts(tmp_path: Path) -> None:
    def fetcher(**kwargs: Any) -> dict[str, Any]:
        write_probe_artifacts(kwargs["output_dir"], kwargs["run_id"])
        return {}

    events: list[str] = []
    result = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        write_enabled=True,
        fetcher=fetcher,
        fetch_pagination_mode="exhaustion",
        fetch_max_pages=120,
        fetch_time_budget_seconds=60,
    )
    assert result["failure_class"] == "probe_pagination_mode_invalid"
    assert result["guarded_write"]["status"] == "not_started"
    assert events == ["relation"]


def test_exhaustion_pagination_evidence_excludes_untrusted_values(tmp_path: Path) -> None:
    result = orch._sanitize_probe_summary(
        {
            "pagination": {
                "mode": SENSITIVE_PRIVATE_PATH,
                "termination": SENSITIVE_API_BODY,
                "requests_performed": SENSITIVE_CREDENTIAL,
                "time_budget_seconds": SENSITIVE_DB_VALUE,
                "next": SENSITIVE_CREDENTIAL,
            }
        }
    )
    assert result["pagination"] == {
        "mode": "unknown",
        "termination": "unknown",
        "requests_performed": None,
        "pages_requested": None,
        "time_budget_seconds": None,
    }
    assert_no_sensitive_leak(result, tmp_path)


def test_prior_exhaustion_artifact_cannot_bypass_termination_gate(tmp_path: Path) -> None:
    prior = run(tmp_path, allow_live_fetch_once=True)
    path = tmp_path / "temporal-probe" / prior["selected_artifact_run_id"] / "summary.json"
    summary = json.loads(path.read_text())
    summary["pagination"].update(mode="exhaustion", termination="deadline_exceeded")
    path.write_text(json.dumps(summary))
    events: list[str] = []
    result = run(
        tmp_path,
        run_id="reuse",
        from_orchestration_run_id=prior["run_id"],
        write_enabled=True,
        events=events,
    )
    assert result["failure_class"] == "prior_probe_deadline_exceeded"
    assert result["guarded_write"]["status"] == "not_started"
    assert events == []


def test_lock_busy_starts_no_steps(tmp_path: Path) -> None:
    events: list[str] = []
    base_dir = tmp_path / "orchestration"
    held_paths = orch.build_paths(base_dir=base_dir, run_id="held")
    held_lock = regular.NoOverlapLock(held_paths.lock_path)

    try:
        assert held_lock.acquire(wait_seconds=0.0) is True
        result = orch.run_orchestration(
            allow_live_fetch_once=True,
            base_dir=base_dir,
            probe_output_dir=tmp_path / "temporal-probe",
            run_id="blocked",
            environ=env(),
            fetcher=fake_fetch(events, tmp_path / "temporal-probe"),
            recurring_runner=fake_recurring(events),
            relation_checker=fake_relation(events),
        )
    finally:
        held_lock.release()

    assert events == []
    assert result["status"] == "lock_busy"
    assert orch.exit_code_for_status(str(result["status"])) == orch.LOCK_BUSY_EXIT_CODE


def test_channel_failure_after_category_success_is_partial_success(tmp_path: Path) -> None:
    events: list[str] = []
    first = run(
        tmp_path,
        events=events,
        allow_live_fetch_once=True,
        run_id="first-run",
    )
    assert first["status"] == "success"

    def partial_recurring(**kwargs: Any) -> dict[str, Any]:
        write_enabled = bool(kwargs["write_enabled"])
        probe_run_dir = kwargs["probe_run_dir"]
        events.append(f"partial:{write_enabled}:{probe_run_dir.name}")
        if write_enabled:
            return recurring_result(
                mode=recurring.GUARDED_WRITE_MODE,
                status="partial_success",
                failure_class="channel_load_failed",
            )
        return recurring_result(mode=recurring.DRY_RUN_MODE)

    result = run(
        tmp_path,
        events=events,
        from_orchestration_run_id="first-run",
        write_enabled=True,
        idempotency_rerun_enabled=True,
        run_id="write-run",
        environ=env(chzzk=False, db=True),
        recurring_runner=partial_recurring,
    )

    assert result["status"] == "partial_success"
    assert result["failure_class"] == "channel_load_failed"
    assert result["idempotency_rerun"]["status"] == "not_requested"


def test_api_failure_is_non_blocking_and_body_is_not_stored(tmp_path: Path) -> None:
    result = run(
        tmp_path,
        allow_live_fetch_once=True,
        api_smoke_url="http://127.0.0.1:8000/chzzk/categories/overview?limit=5",
    )

    assert result["status"] == "success"
    assert result["recurring_no_write_dry_run"]["api_read_smoke"] == {
        "enabled": True,
        "failure_class": "api_read_smoke_request_failed",
        "http_status": None,
        "status": "failed",
    }
    assert SENSITIVE_API_BODY not in json.dumps(result, sort_keys=True)


def test_cli_help_does_not_start_steps(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        orch,
        "run_orchestration",
        lambda **_kwargs: pytest.fail("help must not run orchestration"),
    )

    with pytest.raises(SystemExit) as exc_info:
        orch.main(["--help"])

    assert exc_info.value.code == 0
    assert "--allow-live-fetch-once" in capsys.readouterr().out


def test_cli_rejects_both_source_modes_before_orchestration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orch,
        "run_orchestration",
        lambda **_kwargs: pytest.fail("parser must reject both source modes"),
    )

    with pytest.raises(SystemExit) as exc_info:
        orch.main(
            [
                "--allow-live-fetch-once",
                "--from-orchestration-run-id",
                "prior-run",
            ]
        )

    assert exc_info.value.code == 2
