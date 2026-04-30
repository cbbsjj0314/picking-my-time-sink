from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from chzzk.ingest import run_chzzk_regular_write_path as wrapper

SENSITIVE_CATEGORY_NAME = "Sensitive Synthetic Category Name"
SENSITIVE_CHANNEL_NAME = "Sensitive Synthetic Channel Name"
SENSITIVE_CREDENTIAL = "credential-like-sentinel-secret"
SENSITIVE_DB_VALUE = "postgres-secret-sentinel"
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
        "top_channel_id": "synthetic-channel-alpha",
        "top_channel_name": SENSITIVE_CHANNEL_NAME,
    }
    row.update(overrides)
    return row


def channel_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bucket_time": "2026-04-23T10:30:00+09:00",
        "category_name": SENSITIVE_CATEGORY_NAME,
        "category_type": "GAME",
        "channel_id": "synthetic-channel-alpha",
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
    lines: list[str] = []
    for row in rows:
        if isinstance(row, str):
            lines.append(row)
        else:
            lines.append(json.dumps(row, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_probe_run(
    tmp_path: Path,
    *,
    category_rows: list[object] | None = None,
    channel_rows: list[object] | None = None,
    include_summary: bool = True,
    include_category: bool = True,
    include_channel: bool = True,
) -> Path:
    run_dir = tmp_path / "private-root" / "temporal-probe" / "probe-run-a"
    run_dir.mkdir(parents=True, exist_ok=True)
    if include_summary:
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
                    "result_status": "category_results_available",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    if include_category:
        write_jsonl(run_dir / "category-result.jsonl", category_rows or [category_row()])
    if include_channel:
        write_jsonl(run_dir / "channel-result.jsonl", channel_rows or [channel_row()])
    return run_dir


class FakeCursor:
    def __init__(self, relation_exists: dict[str, bool], events: list[str]) -> None:
        self.relation_exists = relation_exists
        self.events = events
        self.current_relation = ""

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False

    def execute(self, query: str, params: tuple[str]) -> None:
        assert query == wrapper.RELATION_CHECK_SQL
        self.current_relation = params[0]
        self.events.append(f"relation:{self.current_relation}")

    def fetchone(self) -> tuple[str | None]:
        if self.relation_exists[self.current_relation]:
            return (self.current_relation,)
        return (None,)


class FakeConnection:
    def __init__(self, relation_exists: dict[str, bool], events: list[str]) -> None:
        self.relation_exists = relation_exists
        self.events = events

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.relation_exists, self.events)


class FakePsycopg:
    relation_exists = {
        wrapper.CATEGORY_RELATION: True,
        wrapper.CHANNEL_RELATION: True,
    }
    events: list[str] = []

    @classmethod
    def connect(cls, *, conninfo: str) -> FakeConnection:
        assert conninfo == "fake-conninfo"
        cls.events.append("connect")
        return FakeConnection(cls.relation_exists, cls.events)


def patch_relation_checks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    category_exists: bool = True,
    channel_exists: bool = True,
) -> list[str]:
    FakePsycopg.relation_exists = {
        wrapper.CATEGORY_RELATION: category_exists,
        wrapper.CHANNEL_RELATION: channel_exists,
    }
    FakePsycopg.events = []
    monkeypatch.setattr(wrapper, "require_psycopg", lambda: FakePsycopg)
    monkeypatch.setattr(wrapper, "build_pg_conninfo_from_env", lambda environ=None: "fake-conninfo")
    return FakePsycopg.events


def run_wrapper(
    tmp_path: Path,
    probe_run_dir: Path,
    **kwargs: object,
) -> dict[str, Any]:
    return wrapper.run_wrapper_with_evidence(
        probe_run_dir=probe_run_dir,
        base_dir=tmp_path / "regular-write-path",
        run_id="wrapper-run-a",
        **kwargs,
    )


def test_dry_run_success_summary_from_synthetic_probe_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)

    result = run_wrapper(tmp_path, probe_run_dir)

    assert result["status"] == "success"
    assert result["success"] is True
    assert result["partial_success"] is False
    assert result["failure_class"] is None
    assert result["category"]["input_row_count"] == 1
    assert result["category"]["valid_row_count"] == 1
    assert result["category"]["planned_upsert_attempt_count"] == 1
    assert result["category"]["committed_row_count"] == 0
    assert result["category"]["load_attempted"] is False
    assert result["channel"]["valid_row_count"] == 1
    assert result["channel"]["committed_row_count"] == 0
    assert result["channel"]["load_attempted"] is False
    assert result["api_read_smoke"]["enabled"] is False
    assert result["temporal_summary_hook"] == {"enabled": False, "status": "disabled"}
    assert result["artifact_checks"]["category"]["run_relative_ref"] == (
        "probe-run-a/category-result.jsonl"
    )
    assert result["bounded_sample_caveat"]["bounded_page_cutoff"] is True
    assert result["bounded_sample_caveat"]["last_page_next_present"] is True
    saved = json.loads(
        (tmp_path / "regular-write-path" / "wrapper-run-a" / "result.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved == result


def test_missing_category_relation_is_hard_failure_and_skips_artifact_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events = patch_relation_checks(monkeypatch, category_exists=False)
    probe_run_dir = write_probe_run(tmp_path, category_rows=["{not-json"])

    def fail_artifact_check(_probe_run_dir: Path) -> dict[str, dict[str, Any]]:
        pytest.fail("artifact checks must not start after relation failure")

    monkeypatch.setattr(wrapper, "check_probe_artifacts", fail_artifact_check)

    result = run_wrapper(tmp_path, probe_run_dir)

    assert events == [
        "connect",
        f"relation:{wrapper.CATEGORY_RELATION}",
        f"relation:{wrapper.CHANNEL_RELATION}",
    ]
    assert result["status"] == "hard_failure"
    assert result["success"] is False
    assert result["failure_class"] == "category_relation_missing"
    assert result["relation_preconditions"]["category"]["ddl_ref"] == wrapper.CATEGORY_DDL_REF
    assert result["category"]["status"] == "skipped_due_to_relation_precondition_failure"
    assert result["channel"]["status"] == "skipped_due_to_relation_precondition_failure"
    assert result["artifact_checks"] == {}


def test_missing_channel_relation_is_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch, channel_exists=False)
    probe_run_dir = write_probe_run(tmp_path)

    result = run_wrapper(tmp_path, probe_run_dir)

    assert result["status"] == "hard_failure"
    assert result["success"] is False
    assert result["failure_class"] == "channel_relation_missing"
    assert result["relation_preconditions"]["channel"]["ddl_ref"] == wrapper.CHANNEL_DDL_REF
    assert result["category"]["status"] == "skipped_due_to_relation_precondition_failure"
    assert result["channel"]["status"] == "skipped_due_to_relation_precondition_failure"


def test_relation_precondition_unavailable_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    probe_run_dir = write_probe_run(tmp_path)
    monkeypatch.setenv("POSTGRES_PASSWORD", SENSITIVE_DB_VALUE)
    monkeypatch.setattr(
        wrapper,
        "build_pg_conninfo_from_env",
        lambda environ=None: (_ for _ in ()).throw(
            wrapper.RelationPreconditionUnavailable(SENSITIVE_DB_VALUE)
        ),
    )

    result = run_wrapper(tmp_path, probe_run_dir)
    result_text = json.dumps(result, sort_keys=True)

    assert result["status"] == "hard_failure"
    assert result["failure_class"] == "relation_precondition_unavailable"
    assert SENSITIVE_DB_VALUE not in result_text
    assert "POSTGRES_PASSWORD" not in result_text
    assert "conninfo" not in result_text.lower()


def test_missing_category_artifact_is_hard_failure_and_skips_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path, include_category=False)

    result = run_wrapper(tmp_path, probe_run_dir)

    assert result["status"] == "hard_failure"
    assert result["success"] is False
    assert result["failure_class"] == "category_artifact_missing"
    assert result["category"]["status"] == "missing"
    assert result["channel"]["status"] == "skipped_after_category_unusable"


def test_missing_channel_artifact_is_partial_success_after_category_usable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path, include_channel=False)

    result = run_wrapper(tmp_path, probe_run_dir)

    assert result["status"] == "partial_success"
    assert result["success"] is True
    assert result["partial_success"] is True
    assert result["failure_class"] == "channel_artifact_missing"
    assert result["category"]["status"] == "dry_run_planned"
    assert result["channel"]["status"] == "missing"
    assert result["channel"]["load_attempted"] is False


def test_category_parse_failure_skips_channel_and_is_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)

    def fail_category_parse(_path: Path) -> object:
        raise RuntimeError("parser failed with " + SENSITIVE_CATEGORY_NAME)

    monkeypatch.setattr(
        wrapper.category_result_to_gold,
        "load_category_result_rows",
        fail_category_parse,
    )

    result = run_wrapper(tmp_path, probe_run_dir)
    result_text = json.dumps(result, sort_keys=True)

    assert result["status"] == "hard_failure"
    assert result["success"] is False
    assert result["failure_class"] == "category_parse_failed"
    assert result["category"]["status"] == "parse_failed"
    assert result["channel"]["status"] == "skipped_after_category_unusable"
    assert SENSITIVE_CATEGORY_NAME not in result_text


def test_category_zero_valid_rows_skips_channel_and_is_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(
        tmp_path,
        category_rows=[category_row(category_type="NOT_A_TYPE")],
    )

    result = run_wrapper(tmp_path, probe_run_dir)

    assert result["status"] == "hard_failure"
    assert result["success"] is False
    assert result["failure_class"] == "category_no_usable_rows"
    assert result["category"]["valid_row_count"] == 0
    assert result["category"]["skip_reasons"] == {"invalid_category_type": 1}
    assert result["channel"]["status"] == "skipped_after_category_unusable"


def test_channel_parse_failure_is_partial_success_with_sanitized_class(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)

    def fail_channel_parse(_path: Path) -> object:
        raise RuntimeError("parser failed with " + SENSITIVE_CHANNEL_NAME)

    monkeypatch.setattr(
        wrapper.channel_result_to_gold,
        "load_channel_result_rows",
        fail_channel_parse,
    )

    result = run_wrapper(tmp_path, probe_run_dir)
    result_text = json.dumps(result, sort_keys=True)

    assert result["status"] == "partial_success"
    assert result["success"] is True
    assert result["partial_success"] is True
    assert result["failure_class"] == "channel_parse_failed"
    assert result["channel"]["status"] == "parse_failed"
    assert SENSITIVE_CHANNEL_NAME not in result_text


def test_channel_zero_valid_rows_is_partial_success_after_category_usable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(
        tmp_path,
        channel_rows=[channel_row(category_type="NOT_A_TYPE")],
    )

    result = run_wrapper(tmp_path, probe_run_dir)

    assert result["status"] == "partial_success"
    assert result["success"] is True
    assert result["partial_success"] is True
    assert result["failure_class"] == "channel_no_usable_rows"
    assert result["channel"]["valid_row_count"] == 0
    assert result["channel"]["skip_reasons"] == {"invalid_category_type": 1}


def test_lock_busy_writes_safe_summary_and_starts_no_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    probe_run_dir = write_probe_run(tmp_path)
    base_dir = tmp_path / "regular-write-path"
    held_paths = wrapper.build_paths(base_dir=base_dir, run_id="held")
    held_lock = wrapper.NoOverlapLock(held_paths.lock_path)

    def fail_relation_check() -> dict[str, dict[str, Any]]:
        pytest.fail("relation checks must not start when the lock is busy")

    monkeypatch.setattr(wrapper, "check_relation_preconditions", fail_relation_check)

    try:
        assert held_lock.acquire(wait_seconds=0.0) is True
        result = wrapper.run_wrapper_with_evidence(
            probe_run_dir=probe_run_dir,
            base_dir=base_dir,
            run_id="blocked",
        )
    finally:
        held_lock.release()

    assert result["status"] == "lock_busy"
    assert result["success"] is False
    assert result["lock_busy"] is True
    assert wrapper.exit_code_for_status(str(result["status"])) == wrapper.LOCK_BUSY_EXIT_CODE
    assert result["lock"]["lock_ref"] == wrapper.LOCK_BASENAME
    assert (base_dir / "blocked" / "result.json").exists()


def test_summary_excludes_raw_rows_names_paths_credentials_db_and_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)
    monkeypatch.setenv("CHZZK_CLIENT_SECRET", SENSITIVE_CREDENTIAL)
    monkeypatch.setenv("POSTGRES_PASSWORD", SENSITIVE_DB_VALUE)

    result = run_wrapper(tmp_path, probe_run_dir)
    result_text = json.dumps(result, sort_keys=True)

    forbidden = [
        "category_name",
        "channel_name",
        "display_name",
        SENSITIVE_CATEGORY_NAME,
        SENSITIVE_CHANNEL_NAME,
        "live_title",
        "thumbnail",
        SENSITIVE_CREDENTIAL,
        SENSITIVE_DB_VALUE,
        str(tmp_path),
        "/home/",
        "/tmp/",
        SCHEDULER_TASK_NAME,
    ]
    for value in forbidden:
        assert value not in result_text
    assert result["sanitization"] == {
        "absolute_local_paths_in_summary": False,
        "api_response_body_in_summary": False,
        "credentials_in_summary": False,
        "db_env_details_in_summary": False,
        "provider_label_values_in_summary": False,
        "raw_jsonl_rows_in_summary": False,
        "raw_provider_payload_in_summary": False,
        "scheduler_details_in_summary": False,
    }


class FakeApiResponse:
    status_code = 204
    text = "raw api body " + SENSITIVE_CHANNEL_NAME


class FakeApiClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> FakeApiResponse:
        self.urls.append(url)
        return FakeApiResponse()


def test_api_read_smoke_enabled_uses_get_only_fake_client_without_body_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_relation_checks(monkeypatch)
    probe_run_dir = write_probe_run(tmp_path)
    client = FakeApiClient()

    result = run_wrapper(
        tmp_path,
        probe_run_dir,
        api_smoke_url="http://127.0.0.1:8000/chzzk/categories/overview?limit=5",
        api_client=client,
    )
    result_text = json.dumps(result, sort_keys=True)

    assert client.urls == ["http://127.0.0.1:8000/chzzk/categories/overview?limit=5"]
    assert result["api_read_smoke"] == {
        "enabled": True,
        "failure_class": None,
        "http_status": 204,
        "status": "success",
    }
    assert "raw api body" not in result_text
    assert SENSITIVE_CHANNEL_NAME not in result_text
