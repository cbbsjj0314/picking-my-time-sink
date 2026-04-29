from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from chzzk.normalize import channel_result_to_gold
from chzzk.normalize.channel_result_to_gold import (
    ChzzkCategoryChannelFactRow,
    MissingChzzkCategoryChannelFactRelationError,
    format_kst_iso,
    load_channel_result_rows,
    process_channel_result_rows,
)
from chzzk.normalize.channel_result_to_gold import (
    main as channel_result_to_gold_main,
)

SENSITIVE_CHANNEL_NAME = "Sensitive Synthetic Channel Name"
SENSITIVE_CATEGORY_NAME = "Sensitive Synthetic Category Name"
SENSITIVE_PRIVATE_PATH_FRAGMENT = "sensitive-private-root"


def valid_channel_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bucket_time": "2026-04-23T10:30:00+09:00",
        "category_name": SENSITIVE_CATEGORY_NAME,
        "category_type": "GAME",
        "channel_id": "synthetic-channel-alpha",
        "channel_name": SENSITIVE_CHANNEL_NAME,
        "chzzk_category_id": "synthetic-category-alpha",
        "collected_at": "2026-04-23T10:42:00+09:00",
        "concurrent_user_count": 25,
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


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], ChzzkCategoryChannelFactRow] = {}

    def upsert(self, row: ChzzkCategoryChannelFactRow) -> None:
        self.rows[
            (
                row.chzzk_category_id,
                format_kst_iso(row.bucket_time),
                row.channel_id,
            )
        ] = row


def test_process_channel_result_rows_upserts_valid_rows_idempotently(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "channel-result.jsonl"
    write_jsonl(
        input_path,
        [
            valid_channel_row(concurrent_user_count=25),
            valid_channel_row(concurrent_user_count=30),
        ],
    )
    parsed = load_channel_result_rows(input_path)
    store = FakeFactStore()

    first_count = process_channel_result_rows(parsed.valid_rows, upsert_row=store.upsert)
    second_count = process_channel_result_rows(parsed.valid_rows, upsert_row=store.upsert)

    assert first_count == 2
    assert second_count == 2
    assert len(store.rows) == 1
    key = (
        "synthetic-category-alpha",
        "2026-04-23T10:30:00+09:00",
        "synthetic-channel-alpha",
    )
    assert store.rows[key].concurrent_user_count == 30


def test_load_channel_result_rows_accepts_optional_channel_name_but_omits_it(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "channel-result.jsonl"
    write_jsonl(input_path, [valid_channel_row()])

    parsed = load_channel_result_rows(input_path)

    assert len(parsed.valid_rows) == 1
    assert "channel_name" not in {field.name for field in dataclasses.fields(parsed.valid_rows[0])}
    assert SENSITIVE_CHANNEL_NAME not in repr(parsed.valid_rows[0])


def test_load_channel_result_rows_skips_invalid_rows_with_sanitized_reasons(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "channel-result.jsonl"
    write_jsonl(
        input_path,
        [
            valid_channel_row(),
            "{not-json",
            ["not", "object"],
            valid_channel_row(category_type="NOT_A_TYPE"),
            valid_channel_row(bucket_time="2026-04-23T10:31:00+09:00"),
            valid_channel_row(concurrent_user_count=-1),
            valid_channel_row(collected_at="not-a-timestamp"),
            valid_channel_row(channel_id=""),
            valid_channel_row(category_name=""),
            valid_channel_row(chzzk_category_id=None),
        ],
    )

    parsed = load_channel_result_rows(input_path)

    assert len(parsed.valid_rows) == 1
    assert [row.reason for row in parsed.skipped_rows] == [
        "invalid_json",
        "row_must_be_object",
        "invalid_category_type",
        "invalid_bucket_boundary",
        "negative_concurrent_user_count",
        "invalid_timestamp",
        "blank_required_field",
        "blank_required_field",
        "missing_required_field",
    ]
    assert [row.line_number for row in parsed.skipped_rows] == list(range(2, 11))
    skipped_text = json.dumps(
        [dataclasses.asdict(row) for row in parsed.skipped_rows],
        sort_keys=True,
    )
    assert "channel_name" not in skipped_text
    assert SENSITIVE_CHANNEL_NAME not in skipped_text
    assert SENSITIVE_CATEGORY_NAME not in skipped_text


class FakeCursor:
    def __init__(
        self,
        events: list[str],
        upsert_params: list[tuple[object, ...]],
        *,
        relation_exists: bool = True,
        fail_on_upsert: bool = False,
    ) -> None:
        self.events = events
        self.upsert_params = upsert_params
        self.relation_exists = relation_exists
        self.fail_on_upsert = fail_on_upsert
        self.last_query = ""

    def __enter__(self) -> FakeCursor:
        self.events.append("cursor_enter")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        self.events.append("cursor_exit")
        return False

    def execute(self, query: str, params: object | None = None) -> None:
        self.last_query = query
        if query == channel_result_to_gold.RELATION_CHECK_SQL:
            self.events.append("relation_check")
            return
        self.events.append("upsert")
        assert isinstance(params, tuple)
        self.upsert_params.append(params)
        if self.fail_on_upsert:
            raise RuntimeError(
                f"synthetic db failure {SENSITIVE_CHANNEL_NAME} "
                f"/tmp/{SENSITIVE_PRIVATE_PATH_FRAGMENT}/channel-result.jsonl"
            )

    def fetchone(self) -> tuple[str | None]:
        if self.relation_exists:
            return ("fact_chzzk_category_channel_30m",)
        return (None,)


class FakeConnection:
    def __init__(
        self,
        events: list[str],
        upsert_params: list[tuple[object, ...]],
        *,
        relation_exists: bool = True,
        fail_on_upsert: bool = False,
    ) -> None:
        self.events = events
        self.upsert_params = upsert_params
        self.relation_exists = relation_exists
        self.fail_on_upsert = fail_on_upsert

    def cursor(self) -> FakeCursor:
        return FakeCursor(
            self.events,
            self.upsert_params,
            relation_exists=self.relation_exists,
            fail_on_upsert=self.fail_on_upsert,
        )

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


class FakePsycopg:
    events: list[str] = []
    upsert_params: list[tuple[object, ...]] = []
    relation_exists = True
    fail_on_upsert = False

    @classmethod
    def connect(cls, *, conninfo: str) -> FakeConnection:
        assert conninfo == "fake-conninfo"
        cls.events.append("connect")
        return FakeConnection(
            cls.events,
            cls.upsert_params,
            relation_exists=cls.relation_exists,
            fail_on_upsert=cls.fail_on_upsert,
        )


def patch_fake_db(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePsycopg.events = []
    FakePsycopg.upsert_params = []
    FakePsycopg.relation_exists = True
    FakePsycopg.fail_on_upsert = False
    monkeypatch.setattr(channel_result_to_gold, "require_psycopg", lambda: FakePsycopg)
    monkeypatch.setattr(
        channel_result_to_gold,
        "build_pg_conninfo_from_env",
        lambda: "fake-conninfo",
    )


def test_run_commits_after_relation_check_and_upsert(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_fake_db(monkeypatch)
    input_path = tmp_path / SENSITIVE_PRIVATE_PATH_FRAGMENT / "channel-result.jsonl"
    result_path = tmp_path / "summary.json"
    meta_path = tmp_path / "meta.json"
    write_jsonl(input_path, [valid_channel_row()])

    summary = channel_result_to_gold.run(
        input_path=input_path,
        result_path=result_path,
        meta_path=meta_path,
    )

    assert summary["status"] == "success"
    assert summary["valid_row_count"] == 1
    assert summary["upsert_attempt_count"] == 1
    assert summary["committed_row_count"] == 1
    assert summary["failed_row_count"] == 0
    assert summary["input_basename"] == "channel-result.jsonl"
    assert "input_path" not in summary
    assert FakePsycopg.events == [
        "connect",
        "cursor_enter",
        "relation_check",
        "upsert",
        "cursor_exit",
        "commit",
        "close",
    ]
    assert len(FakePsycopg.upsert_params) == 1
    params_text = json.dumps([str(value) for value in FakePsycopg.upsert_params[0]])
    assert "channel_name" not in params_text
    assert SENSITIVE_CHANNEL_NAME not in params_text
    assert json.loads(result_path.read_text(encoding="utf-8")) == summary
    assert json.loads(meta_path.read_text(encoding="utf-8"))["success"] is True


def test_run_summary_omits_names_and_full_private_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_fake_db(monkeypatch)
    input_path = tmp_path / SENSITIVE_PRIVATE_PATH_FRAGMENT / "channel-result.jsonl"
    result_path = tmp_path / "summary.json"
    meta_path = tmp_path / "meta.json"
    write_jsonl(input_path, [valid_channel_row(), valid_channel_row(category_type="INVALID")])

    summary = channel_result_to_gold.run(
        input_path=input_path,
        result_path=result_path,
        meta_path=meta_path,
    )
    summary_text = json.dumps(summary, ensure_ascii=False, sort_keys=True)

    assert summary["skip_reasons"] == {"invalid_category_type": 1}
    assert "channel_name" not in summary_text
    assert "category_name" not in summary_text
    assert SENSITIVE_CHANNEL_NAME not in summary_text
    assert SENSITIVE_CATEGORY_NAME not in summary_text
    assert str(input_path) not in summary_text
    assert SENSITIVE_PRIVATE_PATH_FRAGMENT not in summary_text


def test_run_does_not_connect_when_no_valid_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_fake_db(monkeypatch)
    input_path = tmp_path / "channel-result.jsonl"
    result_path = tmp_path / "summary.json"
    meta_path = tmp_path / "meta.json"
    write_jsonl(input_path, [valid_channel_row(category_type="INVALID")])

    summary = channel_result_to_gold.run(
        input_path=input_path,
        result_path=result_path,
        meta_path=meta_path,
    )

    assert summary["status"] == "success"
    assert summary["valid_row_count"] == 0
    assert summary["upsert_attempt_count"] == 0
    assert summary["committed_row_count"] == 0
    assert FakePsycopg.events == []


def test_run_missing_relation_rolls_back_and_writes_failed_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_fake_db(monkeypatch)
    FakePsycopg.relation_exists = False
    input_path = tmp_path / SENSITIVE_PRIVATE_PATH_FRAGMENT / "channel-result.jsonl"
    result_path = tmp_path / "summary.json"
    meta_path = tmp_path / "meta.json"
    write_jsonl(input_path, [valid_channel_row()])

    with pytest.raises(MissingChzzkCategoryChannelFactRelationError, match="016_fact"):
        channel_result_to_gold.run(
            input_path=input_path,
            result_path=result_path,
            meta_path=meta_path,
        )

    summary = json.loads(result_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    failure_text = json.dumps({"meta": meta, "summary": summary}, sort_keys=True)
    assert summary["status"] == "failed"
    assert summary["valid_row_count"] == 1
    assert summary["upsert_attempt_count"] == 1
    assert summary["committed_row_count"] == 0
    assert summary["failed_row_count"] == 1
    assert summary["failure_reason"] == (
        "fact_chzzk_category_channel_30m relation is missing; "
        "apply sql/postgres/016_fact_chzzk_category_channel_30m.sql"
    )
    assert str(input_path) not in failure_text
    assert SENSITIVE_PRIVATE_PATH_FRAGMENT not in failure_text
    assert SENSITIVE_CHANNEL_NAME not in failure_text
    assert FakePsycopg.events == [
        "connect",
        "cursor_enter",
        "relation_check",
        "cursor_exit",
        "rollback",
        "close",
    ]


def test_run_db_failure_rolls_back_without_claiming_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_fake_db(monkeypatch)
    FakePsycopg.fail_on_upsert = True
    input_path = tmp_path / SENSITIVE_PRIVATE_PATH_FRAGMENT / "channel-result.jsonl"
    result_path = tmp_path / "summary.json"
    meta_path = tmp_path / "meta.json"
    write_jsonl(input_path, [valid_channel_row()])

    with pytest.raises(RuntimeError):
        channel_result_to_gold.run(
            input_path=input_path,
            result_path=result_path,
            meta_path=meta_path,
        )

    summary = json.loads(result_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    failure_text = json.dumps({"meta": meta, "summary": summary}, sort_keys=True)
    assert summary["status"] == "failed"
    assert summary["valid_row_count"] == 1
    assert summary["upsert_attempt_count"] == 1
    assert summary["committed_row_count"] == 0
    assert summary["failed_row_count"] == 1
    assert summary["failure_reason"] == "database_write_failed:RuntimeError"
    assert str(input_path) not in failure_text
    assert SENSITIVE_PRIVATE_PATH_FRAGMENT not in failure_text
    assert SENSITIVE_CHANNEL_NAME not in failure_text
    assert "rollback" in FakePsycopg.events
    assert "commit" not in FakePsycopg.events


def test_cli_help_is_safe_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        channel_result_to_gold,
        "require_psycopg",
        lambda: pytest.fail("help should not import psycopg"),
    )

    with pytest.raises(SystemExit) as exc_info:
        channel_result_to_gold_main(["--help"])

    assert exc_info.value.code == 0
