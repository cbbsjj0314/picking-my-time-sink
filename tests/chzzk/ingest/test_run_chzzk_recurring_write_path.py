from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from chzzk.ingest import run_chzzk_recurring_write_path as recurring

SENSITIVE_CATEGORY_NAME = "Sensitive Synthetic Category Name"
SENSITIVE_CHANNEL_NAME = "Sensitive Synthetic Channel Name"
SENSITIVE_CHANNEL_ID = "synthetic-channel-alpha"
SENSITIVE_CREDENTIAL = "credential-like-sentinel-secret"
SENSITIVE_DB_VALUE = "postgres-secret-sentinel"
SENSITIVE_PRIVATE_PATH = "/tmp/private/chzzk/category-result.jsonl"
SENSITIVE_API_BODY = "raw api body sentinel"
SCHEDULER_TASK_NAME = "LOCAL_SCHEDULER_TASK_SENTINEL_SHOULD_NOT_APPEAR"


def category_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bucket_time": "2026-04-23T10:30:00+09:00",
        "category_name": SENSITIVE_CATEGORY_NAME,
        "category_type": "GAME",
        "chzzk_category_id": "synthetic-category-alpha",
        "collected_at": "2026-04-23T10:42:00+09:00",
        "concurrent_sum": 25,
        "live_count": 2,
        "live_title": "Sensitive Live Title",
        "thumbnail": "https://example.invalid/sensitive-thumbnail.jpg",
        "top_channel_concurrent": 15,
        "top_channel_id": SENSITIVE_CHANNEL_ID,
        "top_channel_name": SENSITIVE_CHANNEL_NAME,
    }
    row.update(overrides)
    return row


def channel_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bucket_time": "2026-04-23T10:30:00+09:00",
        "category_name": SENSITIVE_CATEGORY_NAME,
        "category_type": "GAME",
        "channel_id": SENSITIVE_CHANNEL_ID,
        "channel_name": SENSITIVE_CHANNEL_NAME,
        "chzzk_category_id": "synthetic-category-alpha",
        "collected_at": "2026-04-23T10:42:00+09:00",
        "concurrent_user_count": 25,
        "live_title": "Sensitive Live Title",
        "thumbnail": "https://example.invalid/sensitive-thumbnail.jpg",
    }
    row.update(overrides)
    return row


def write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            row if isinstance(row, str) else json.dumps(row, sort_keys=True)
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )


def write_probe_run(
    tmp_path: Path,
    *,
    category_rows: list[object] | None = None,
    channel_rows: list[object] | None = None,
    include_channel: bool = True,
) -> Path:
    run_dir = tmp_path / "private-root" / "temporal-probe" / "probe-run-a"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "coverage": {"status": "observed_bucket_only"},
                "pagination": {
                    "bounded_page_cutoff": True,
                    "last_page_next_present": True,
                    "pages_fetched": 3,
                    "pages_requested": 3,
                },
                "run_id": "probe-run-a",
                "run_status": "success",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_jsonl(run_dir / "category-result.jsonl", category_rows or [category_row()])
    if include_channel:
        write_jsonl(run_dir / "channel-result.jsonl", channel_rows or [channel_row()])
    return run_dir


def patch_relation_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recurring.dry_run,
        "check_relation_preconditions",
        lambda: {
            "category": {
                "checked": True,
                "ddl_ref": recurring.dry_run.CATEGORY_DDL_REF,
                "relation": recurring.dry_run.CATEGORY_RELATION,
                "role": "category",
                "status": "exists",
            },
            "channel": {
                "checked": True,
                "ddl_ref": recurring.dry_run.CHANNEL_DDL_REF,
                "relation": recurring.dry_run.CHANNEL_RELATION,
                "role": "channel",
                "status": "exists",
            },
        },
    )


def fake_loader_summary(role: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "bucket_max": "2026-04-23T10:30:00+09:00",
        "bucket_min": "2026-04-23T10:30:00+09:00",
        "category_name": SENSITIVE_CATEGORY_NAME,
        "channel_id": SENSITIVE_CHANNEL_ID,
        "channel_name": SENSITIVE_CHANNEL_NAME,
        "committed_row_count": 1,
        "credential": SENSITIVE_CREDENTIAL,
        "failed_row_count": 0,
        "input_path": SENSITIVE_PRIVATE_PATH,
        "input_row_count": 1,
        "live_title": "Sensitive Live Title",
        "meta_path": "/tmp/private/chzzk/meta.json",
        "raw_rows": [category_row()],
        "scheduler_task": SCHEDULER_TASK_NAME,
        "skip_reasons": {},
        "skipped_row_count": 0,
        "status": "success",
        "thumbnail": "https://example.invalid/sensitive-thumbnail.jpg",
        "upsert_attempt_count": 1,
        "valid_row_count": 1,
    }
    if role == "category":
        summary["unique_category_count"] = 1
    else:
        summary["unique_category_count"] = 1
        summary["unique_channel_count"] = 1
    return summary


def make_loader(role: str, events: list[str]) -> recurring.Loader:
    def loader(*, input_path: Path, result_path: Path, meta_path: Path) -> dict[str, Any]:
        assert input_path.name in {"category-result.jsonl", "channel-result.jsonl"}
        assert result_path.name == f"{role}-loader-summary.json"
        assert meta_path.name == f"{role}-loader-meta.json"
        events.append(role)
        summary = fake_loader_summary(role)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
        return summary

    return loader


def run_recurring(
    tmp_path: Path,
    probe_run_dir: Path,
    **kwargs: object,
) -> dict[str, Any]:
    return recurring.run_recurring_with_evidence(
        probe_run_dir=probe_run_dir,
        base_dir=tmp_path / "recurring-write-path",
        run_id="recurring-run-a",
        **kwargs,
    )


def test_default_run_is_dry_run_no_write_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)

    def fail_loader(**_kwargs: object) -> dict[str, Any]:
        pytest.fail("default recurring run must not call DB loaders")

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        category_loader=fail_loader,
        channel_loader=fail_loader,
    )

    assert result["mode"] == recurring.DRY_RUN_MODE
    assert result["status"] == "success"
    assert result["action_policy"] == {
        "api_read_smoke_enabled": False,
        "db_write_enabled": False,
        "live_fetch_enabled": False,
        "scheduler_registration_enabled": False,
        "selected_artifact_required": True,
    }
    assert result["category"]["load_attempted"] is False
    assert result["channel"]["load_attempted"] is False


def test_explicit_write_mode_uses_fake_loaders_and_sanitizes_loader_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)
    events: list[str] = []
    monkeypatch.setenv("POSTGRES_PASSWORD", SENSITIVE_DB_VALUE)

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        write_enabled=True,
        category_loader=make_loader("category", events),
        channel_loader=make_loader("channel", events),
    )
    result_text = json.dumps(result, sort_keys=True)

    assert events == ["category", "channel"]
    assert result["mode"] == recurring.GUARDED_WRITE_MODE
    assert result["status"] == "success"
    assert result["action_policy"]["db_write_enabled"] is True
    assert result["category"]["status"] == "loaded"
    assert result["category"]["committed_row_count"] == 1
    assert result["channel"]["status"] == "loaded"
    assert result["post_write_dry_run"]["enabled"] is True
    assert result["post_write_dry_run"]["lock_reacquired"] is False
    for forbidden in [
        "input_path",
        "meta_path",
        SENSITIVE_PRIVATE_PATH,
        SENSITIVE_CATEGORY_NAME,
        SENSITIVE_CHANNEL_NAME,
        SENSITIVE_CHANNEL_ID,
        "Sensitive Live Title",
        "thumbnail",
        SENSITIVE_CREDENTIAL,
        SENSITIVE_DB_VALUE,
        "POSTGRES_PASSWORD",
        "conninfo",
        SCHEDULER_TASK_NAME,
    ]:
        assert forbidden not in result_text


def test_channel_loader_failure_after_category_commit_is_partial_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)
    events: list[str] = []

    def fail_channel_loader(**_kwargs: object) -> dict[str, Any]:
        events.append("channel")
        raise RuntimeError("connection string " + SENSITIVE_DB_VALUE)

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        write_enabled=True,
        category_loader=make_loader("category", events),
        channel_loader=fail_channel_loader,
    )
    result_text = json.dumps(result, sort_keys=True)

    assert events == ["category", "channel"]
    assert result["status"] == "partial_success"
    assert result["failure_class"] == "channel_load_failed"
    assert result["success"] is True
    assert result["category"]["status"] == "loaded"
    assert result["transaction_caveat"]["separate_loader_transactions"] is True
    assert result["transaction_caveat"][
        "category_commit_not_rolled_back_by_channel_failure"
    ] is True
    assert SENSITIVE_DB_VALUE not in result_text
    assert "connection string" not in result_text


def test_category_validation_failure_skips_channel_and_is_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(
        tmp_path,
        category_rows=[category_row(category_type="NOT_A_TYPE")],
    )

    def fail_channel_loader(**_kwargs: object) -> dict[str, Any]:
        pytest.fail("channel must not start after category validation failure")

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        write_enabled=True,
        category_loader=make_loader("category", []),
        channel_loader=fail_channel_loader,
    )

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "category_no_usable_rows"
    assert result["channel"]["status"] == "skipped_after_category_unusable"


class FailingApiClient:
    def get(self, url: str) -> object:
        del url
        raise RuntimeError(SENSITIVE_API_BODY)


def test_api_smoke_failure_is_non_blocking_and_body_is_not_stored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        api_smoke_url="http://127.0.0.1:8000/chzzk/categories/overview?limit=5",
        api_client=FailingApiClient(),
    )
    result_text = json.dumps(result, sort_keys=True)

    assert result["status"] == "success"
    assert result["api_read_smoke"] == {
        "enabled": True,
        "failure_class": "api_read_smoke_request_failed",
        "http_status": None,
        "status": "failed",
    }
    assert result["action_policy"]["api_read_smoke_enabled"] is True
    assert SENSITIVE_API_BODY not in result_text


def test_lock_busy_starts_no_relation_load_or_api_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    probe_run_dir = write_probe_run(tmp_path)
    base_dir = tmp_path / "recurring-write-path"
    held_paths = recurring.build_paths(base_dir=base_dir, run_id="held")
    held_lock = recurring.dry_run.NoOverlapLock(held_paths.lock_path)

    def fail_relation_check() -> dict[str, Any]:
        pytest.fail("relation checks must not start when lock is busy")

    monkeypatch.setattr(recurring.dry_run, "check_relation_preconditions", fail_relation_check)

    try:
        assert held_lock.acquire(wait_seconds=0.0) is True
        result = recurring.run_recurring_with_evidence(
            probe_run_dir=probe_run_dir,
            base_dir=base_dir,
            run_id="blocked",
            api_smoke_url="http://127.0.0.1:8000/chzzk/categories/overview?limit=5",
        )
    finally:
        held_lock.release()

    assert result["status"] == "lock_busy"
    assert recurring.exit_code_for_status(str(result["status"])) == recurring.LOCK_BUSY_EXIT_CODE
    assert result["api_read_smoke"]["status"] == "disabled"
    assert result["lock"]["lock_ref"] == recurring.LOCK_BASENAME


def test_relation_missing_is_hard_failure_before_artifact_or_load_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    probe_run_dir = write_probe_run(tmp_path, category_rows=["{not-json"])
    monkeypatch.setattr(
        recurring.dry_run,
        "check_relation_preconditions",
        lambda: {
            "category": {
                "checked": True,
                "ddl_ref": recurring.dry_run.CATEGORY_DDL_REF,
                "relation": recurring.dry_run.CATEGORY_RELATION,
                "role": "category",
                "status": "missing",
            },
            "channel": {
                "checked": True,
                "ddl_ref": recurring.dry_run.CHANNEL_DDL_REF,
                "relation": recurring.dry_run.CHANNEL_RELATION,
                "role": "channel",
                "status": "exists",
            },
        },
    )

    def fail_loader(**_kwargs: object) -> dict[str, Any]:
        pytest.fail("loaders must not start after relation failure")

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        write_enabled=True,
        category_loader=fail_loader,
        channel_loader=fail_loader,
    )

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "category_relation_missing"
    assert result["artifact_checks"] == {}
    assert result["category"]["status"] == "skipped_due_to_relation_precondition_failure"
    assert result["channel"]["status"] == "skipped_due_to_relation_precondition_failure"


def test_post_write_verification_does_not_reacquire_whole_run_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)
    original_lock = recurring.dry_run.NoOverlapLock
    acquire_count = 0

    class CountingLock:
        def __init__(self, path: Path) -> None:
            self.inner = original_lock(path)

        def acquire(self, *, wait_seconds: float = 0.0) -> bool:
            nonlocal acquire_count
            acquire_count += 1
            return self.inner.acquire(wait_seconds=wait_seconds)

        def release(self) -> None:
            self.inner.release()

    monkeypatch.setattr(recurring.dry_run, "NoOverlapLock", CountingLock)

    result = run_recurring(
        tmp_path,
        probe_run_dir,
        write_enabled=True,
        category_loader=make_loader("category", []),
        channel_loader=make_loader("channel", []),
    )

    assert result["status"] == "success"
    assert result["post_write_dry_run"]["lock_reacquired"] is False
    assert acquire_count == 1


def test_wsl_wrapper_is_dry_run_no_write_only_and_bash_valid() -> None:
    script_path = Path("scripts/local/run_chzzk_regular_write_path_wsl.sh")
    script = script_path.read_text(encoding="utf-8")

    assert "--write" not in script
    assert "dry-run/no-write only" in script
    assert "run_chzzk_recurring_write_path" in script
    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_cli_help_does_not_run_relations_or_loaders(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        recurring.dry_run,
        "check_relation_preconditions",
        lambda: pytest.fail("help must not check DB relations"),
    )

    with pytest.raises(SystemExit) as exc_info:
        recurring.main(["--help"])

    assert exc_info.value.code == 0
    assert "--write" in capsys.readouterr().out
