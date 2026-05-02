from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from chzzk.ingest import run_chzzk_fetch_load_manual_orchestration as orch
from chzzk.ingest import run_chzzk_recurring_write_path as recurring
from chzzk.ingest import run_chzzk_regular_write_path as regular

SENSITIVE_CATEGORY_NAME = "Sensitive Synthetic Category Name"
SENSITIVE_CATEGORY_ID = "sensitive-category-id"
SENSITIVE_CHANNEL_NAME = "Sensitive Synthetic Channel Name"
SENSITIVE_CHANNEL_ID = "sensitive-channel-id"
SENSITIVE_LIVE_TITLE = "Sensitive Live Title"
SENSITIVE_THUMBNAIL = "https://example.invalid/sensitive-thumbnail.jpg"
SENSITIVE_CREDENTIAL = "credential-like-sentinel-secret"
SENSITIVE_CREDENTIAL_LENGTH = str(len(SENSITIVE_CREDENTIAL))
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
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "category_result_path": SENSITIVE_PRIVATE_PATH,
                "category_result_rows": 1,
                "channel_result_path": SENSITIVE_PRIVATE_PATH,
                "channel_result_rows": 1,
                "coverage": {"status": "observed_bucket_only"},
                "pagination": {
                    "bounded_page_cutoff": True,
                    "last_page_next_present": True,
                    "pages_fetched": 3,
                    "pages_requested": 3,
                },
                "raw_page_dir": SENSITIVE_PRIVATE_PATH,
                "result_status": "category_results_available",
                "run_status": "success",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
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
        SENSITIVE_CREDENTIAL_LENGTH,
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
