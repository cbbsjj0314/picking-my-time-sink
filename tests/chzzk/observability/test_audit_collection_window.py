from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from chzzk.normalize.category_lives import KST
from chzzk.observability import audit_collection_window as audit


def make_window(intervals: int = 2) -> audit.WindowSpec:
    return audit.parse_window(
        "2026-01-01T00:00:00+09:00",
        f"2026-01-01T{intervals // 2:02d}:{30 if intervals % 2 else 0:02d}:00+09:00",
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_run(
    base_dir: Path,
    bucket: dt.datetime,
    *,
    duplicate_index: int = 0,
    exit_code: object = "0",
    status: object = "success",
    committed_rows: object = 3,
    no_write: object = None,
    guarded: object = None,
) -> Path:
    boundary = bucket.astimezone(dt.UTC) + dt.timedelta(minutes=29, seconds=duplicate_index)
    run_dir = base_dir / boundary.strftime(audit.BOUNDARY_ID_FORMAT)
    write_json(run_dir / "trace" / "end.json", {"exit_code": exit_code})
    if no_write is None:
        no_write = {
            "status": "success",
            "success": True,
            "failure_class": None,
            "live_fetch": {"invocation_count": 1},
            "action_policy": {
                "db_write_enabled": False,
                "scheduler_registration_enabled": False,
            },
            "artifact_checks": {
                "category": {"status": "present"},
                "channel": {"status": "present"},
            },
            "run_id": "private-no-write-run-id",
            "selected_artifact_run_id": "private-no-write-run-id",
            "private_value": "not-exported",
        }
    if no_write != "missing":
        if no_write == "empty":
            (run_dir / "no-write-result.json").parent.mkdir(parents=True, exist_ok=True)
            (run_dir / "no-write-result.json").write_bytes(b"")
        elif no_write == "invalid_json":
            (run_dir / "no-write-result.json").parent.mkdir(parents=True, exist_ok=True)
            (run_dir / "no-write-result.json").write_text("{", encoding="utf-8")
        else:
            write_json(run_dir / "no-write-result.json", no_write)
    if guarded is None:
        guarded = {
            "status": status,
            "guarded_write": {"category": {"committed_row_count": committed_rows}},
            "run_id": "private-run-id",
            "provider_payload": {"category": "private-category"},
        }
    if guarded != "missing":
        write_json(run_dir / "guarded-write-result.json", guarded)
    return run_dir


def complete_reader(window: audit.WindowSpec) -> audit.BucketReader:
    def reader(_start: dt.datetime, _end: dt.datetime) -> audit.DatabaseReadResult:
        return audit.DatabaseReadResult(
            query_status="success",
            relation_available=True,
            buckets=window.expected_buckets,
        )

    return reader


def build_report(
    tmp_path: Path,
    window: audit.WindowSpec,
    *,
    reader: audit.BucketReader | None = None,
) -> dict[str, Any]:
    return audit.build_audit_report(
        window=window,
        wrapper_base_dir=tmp_path / "wrapper",
        bucket_reader=reader or complete_reader(window),
    )


def test_parse_window_normalizes_aware_inputs_to_kst() -> None:
    window = audit.parse_window(
        "2026-01-01T00:00:00+09:00",
        "2026-01-02T00:00:00+09:00",
    )

    assert window.start_kst == dt.datetime(2026, 1, 1, tzinfo=KST)
    assert window.end_kst == dt.datetime(2026, 1, 2, tzinfo=KST)
    assert window.expected_interval_count == 48


def test_parse_window_normalizes_utc_offset_to_same_kst_window() -> None:
    kst_window = audit.parse_window(
        "2026-01-01T00:00:00+09:00",
        "2026-01-01T01:00:00+09:00",
    )
    utc_window = audit.parse_window(
        "2025-12-31T15:00:00+00:00",
        "2025-12-31T16:00:00+00:00",
    )

    assert utc_window == kst_window


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-01-01T00:00:00", "2026-01-01T01:00:00+09:00"),
        ("2026-01-01T00:00:00+09:00", "2026-01-01T00:00:00+09:00"),
        ("2026-01-01T00:00:00+09:00", "2025-12-31T23:30:00+09:00"),
        ("2026-01-01T00:01:00+09:00", "2026-01-01T01:01:00+09:00"),
        ("2026-01-01T00:00:00+09:00", "2026-01-01T00:45:00+09:00"),
    ],
)
def test_parse_window_rejects_invalid_contract(start: str, end: str) -> None:
    with pytest.raises(ValueError):
        audit.parse_window(start, end)


def test_parse_window_counts_seven_days() -> None:
    window = audit.parse_window(
        "2026-01-01T00:00:00+09:00",
        "2026-01-08T00:00:00+09:00",
    )

    assert window.expected_interval_count == 336


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, ("zero", 0)),
        ("0", ("zero", 0)),
        (1, ("nonzero", 1)),
        ("1", ("nonzero", 1)),
        (" 0 ", ("zero", 0)),
        ("invalid", ("invalid", None)),
        (1.0, ("invalid", None)),
        (True, ("invalid", None)),
    ],
)
def test_normalize_exit_code(value: object, expected: tuple[str, int | None]) -> None:
    assert audit.normalize_exit_code(value) == expected


def test_normalize_exit_code_distinguishes_missing() -> None:
    assert audit.normalize_exit_code() == ("missing", None)


@pytest.mark.parametrize(
    ("content", "state"),
    [
        (b"", "empty"),
        (b"{", "invalid_json"),
        (b"[]", "invalid_shape"),
        (b"{}", "present_valid"),
    ],
)
def test_json_artifact_states(tmp_path: Path, content: bytes, state: str) -> None:
    path = tmp_path / "artifact.json"
    path.write_bytes(content)

    assert audit.read_json_artifact(path).state == state


def test_json_artifact_missing_state(tmp_path: Path) -> None:
    assert audit.read_json_artifact(tmp_path / "missing.json").state == "missing"


def test_clean_synthetic_window(tmp_path: Path) -> None:
    window = make_window()
    for bucket in window.expected_buckets:
        write_run(tmp_path / "wrapper", bucket)

    report = build_report(tmp_path, window)

    assert report["classification"] == "clean"
    assert report["reasons"] == []
    assert report["wrapper"]["unique_mapped_interval_count"] == 2
    assert report["wrapper"]["exit_code_counts"]["zero"] == 2
    assert report["wrapper"]["guarded_status_counts"]["success"] == 2
    assert report["wrapper"]["category"]["positive_committed_row_run_count"] == 2
    assert report["database"]["present_distinct_bucket_count"] == 2


def test_known_incident_shape_is_degraded_and_sanitized(tmp_path: Path) -> None:
    window = make_window(1)
    run_dir = write_run(
        tmp_path / "wrapper",
        window.expected_buckets[0],
        exit_code="1",
        no_write="empty",
        guarded="missing",
    )
    write_json(run_dir / "trace" / "private.json", {"stderr": "private traceback"})

    report = build_report(tmp_path, window)
    serialized = json.dumps(report, sort_keys=True)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["confirmed_failure_run_count"] == 1
    assert report["wrapper"]["artifact_state_counts"]["no_write_result"]["empty"] == 1
    assert "wrapper_nonzero_exit_code" in report["reasons"]
    assert "private traceback" not in serialized
    assert str(tmp_path) not in serialized


def test_missing_internal_wrapper_interval_is_degraded(tmp_path: Path) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.expected_buckets[0])
    write_run(tmp_path / "wrapper", window.expected_buckets[2])

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["missing_expected_interval_count"] == 1
    assert "wrapper_expected_interval_missing" in report["reasons"]


def test_missing_first_interval_with_surrounding_evidence_is_degraded(
    tmp_path: Path,
) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.start_kst - audit.INTERVAL)
    for bucket in window.expected_buckets[1:]:
        write_run(tmp_path / "wrapper", bucket)
    write_run(tmp_path / "wrapper", window.end_kst)

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["retention_covers_window"] is True
    assert report["wrapper"]["missing_expected_interval_count"] == 1
    assert "wrapper_expected_interval_missing" in report["reasons"]


def test_missing_last_interval_with_surrounding_evidence_is_degraded(
    tmp_path: Path,
) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.start_kst - audit.INTERVAL)
    for bucket in window.expected_buckets[:-1]:
        write_run(tmp_path / "wrapper", bucket)
    write_run(tmp_path / "wrapper", window.end_kst)

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["retention_covers_window"] is True
    assert report["wrapper"]["missing_expected_interval_count"] == 1
    assert "wrapper_expected_interval_missing" in report["reasons"]


def test_retained_evidence_starting_inside_window_is_incomplete(tmp_path: Path) -> None:
    window = make_window(3)
    for bucket in window.expected_buckets[1:]:
        write_run(tmp_path / "wrapper", bucket)
    write_run(tmp_path / "wrapper", window.end_kst)

    report = build_report(tmp_path, window)

    assert report["classification"] == "incomplete_evidence"
    assert report["wrapper"]["retention_covers_window"] is False
    assert "wrapper_window_evidence_incomplete" in report["reasons"]


def test_retained_evidence_ending_inside_window_is_incomplete(tmp_path: Path) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.start_kst - audit.INTERVAL)
    for bucket in window.expected_buckets[:-1]:
        write_run(tmp_path / "wrapper", bucket)

    report = build_report(tmp_path, window)

    assert report["classification"] == "incomplete_evidence"
    assert report["wrapper"]["retention_covers_window"] is False
    assert "wrapper_window_evidence_incomplete" in report["reasons"]


def test_complete_window_with_surrounding_evidence_stays_clean(tmp_path: Path) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.start_kst - audit.INTERVAL)
    for bucket in window.expected_buckets:
        write_run(tmp_path / "wrapper", bucket)
    write_run(tmp_path / "wrapper", window.end_kst)

    report = build_report(tmp_path, window)

    assert report["classification"] == "clean"
    assert report["wrapper"]["retention_covers_window"] is True


def test_surrounding_evidence_is_excluded_from_target_counts(tmp_path: Path) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.start_kst - audit.INTERVAL)
    for bucket in window.expected_buckets:
        write_run(tmp_path / "wrapper", bucket)
    write_run(tmp_path / "wrapper", window.end_kst)

    report = build_report(tmp_path, window)

    assert report["wrapper"]["recognized_run_directory_count"] == 3
    assert report["wrapper"]["unique_mapped_interval_count"] == 3
    assert report["wrapper"]["duplicate_mapped_interval_count"] == 0
    assert report["wrapper"]["exit_code_counts"]["zero"] == 3


def test_duplicate_wrapper_interval_is_degraded(tmp_path: Path) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0])
    write_run(tmp_path / "wrapper", window.expected_buckets[0], duplicate_index=1)

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["duplicate_mapped_interval_count"] == 1


def test_missing_database_bucket_is_degraded(tmp_path: Path) -> None:
    window = make_window(2)
    for bucket in window.expected_buckets:
        write_run(tmp_path / "wrapper", bucket)

    def reader(_start: dt.datetime, _end: dt.datetime) -> audit.DatabaseReadResult:
        return audit.DatabaseReadResult("success", True, window.expected_buckets[:1])

    report = build_report(tmp_path, window, reader=reader)

    assert report["classification"] == "degraded"
    assert report["database"]["missing_bucket_count"] == 1
    assert "wrapper_database_bucket_contradiction" in report["reasons"]


@pytest.mark.parametrize(
    ("run_kwargs", "reason"),
    [
        ({"committed_rows": 0}, "wrapper_category_committed_rows_zero"),
        ({"exit_code": "1"}, "wrapper_exit_status_conflict"),
        ({"guarded": "missing"}, "wrapper_zero_exit_guarded_result_missing"),
        ({"status": "partial_success"}, "wrapper_status_not_success"),
        ({"no_write": "invalid_json"}, "wrapper_no_write_result_invalid_json"),
    ],
)
def test_additional_wrapper_degradation(
    tmp_path: Path,
    run_kwargs: dict[str, object],
    reason: str,
) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0], **run_kwargs)

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert reason in report["reasons"]


def test_unknown_wrapper_status_is_counted_separately(tmp_path: Path) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0], status="unknown")

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["guarded_status_counts"]["unknown"] == 1
    assert report["wrapper"]["guarded_status_counts"]["unrecognized"] == 0


@pytest.mark.parametrize(
    "no_write",
    [
        {},
        {"status": "hard_failure"},
        {"status": "success", "success": False},
        {"status": "success", "artifact_checks": {"category": 1}},
    ],
)
def test_no_write_success_contract_failure_is_degraded(
    tmp_path: Path,
    no_write: dict[str, object],
) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0], no_write=no_write)

    report = build_report(tmp_path, window)

    assert report["classification"] == "degraded"
    assert report["wrapper"]["no_write_success_contract_invalid_count"] == 1
    assert "wrapper_no_write_result_semantic_invalid" in report["reasons"]


def test_wrapper_base_missing_is_incomplete(tmp_path: Path) -> None:
    window = make_window(1)

    report = build_report(tmp_path, window)

    assert report["classification"] == "incomplete_evidence"
    assert report["reasons"] == ["wrapper_base_unavailable"]


def test_database_reader_unavailable_is_incomplete(tmp_path: Path) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0])

    def reader(_start: dt.datetime, _end: dt.datetime) -> audit.DatabaseReadResult:
        raise RuntimeError("secret connection detail")

    report = build_report(tmp_path, window, reader=reader)

    assert report["classification"] == "incomplete_evidence"
    assert report["reasons"] == ["database_query_unavailable"]
    assert "secret connection detail" not in json.dumps(report)


def test_confirmed_degradation_wins_when_database_is_unavailable(tmp_path: Path) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0], exit_code=1)

    def reader(_start: dt.datetime, _end: dt.datetime) -> audit.DatabaseReadResult:
        raise RuntimeError("unavailable")

    report = build_report(tmp_path, window, reader=reader)

    assert report["classification"] == "degraded"
    assert "database_query_unavailable" in report["reasons"]
    assert "wrapper_nonzero_exit_code" in report["reasons"]


def test_mapping_cannot_be_grounded_is_incomplete(tmp_path: Path) -> None:
    window = make_window(1)
    write_json(
        tmp_path / "wrapper" / "not-a-boundary" / "trace" / "end.json",
        {"exit_code": 0},
    )

    report = build_report(tmp_path, window)

    assert report["classification"] == "incomplete_evidence"
    assert "wrapper_mapping_unavailable" in report["reasons"]


def test_retained_evidence_not_spanning_window_is_incomplete(tmp_path: Path) -> None:
    window = make_window(3)
    write_run(tmp_path / "wrapper", window.expected_buckets[-1])

    report = build_report(tmp_path, window)

    assert report["classification"] == "incomplete_evidence"
    assert report["wrapper"]["missing_expected_interval_count"] == 2
    assert "wrapper_window_evidence_incomplete" in report["reasons"]


def test_report_json_is_deterministic_and_aggregate_only(tmp_path: Path) -> None:
    window = make_window(1)
    write_run(tmp_path / "wrapper", window.expected_buckets[0])
    report = build_report(tmp_path, window)
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    audit.write_report_json(first_path, report)
    audit.write_report_json(second_path, report)
    first = first_path.read_text(encoding="utf-8")

    assert first == second_path.read_text(encoding="utf-8")
    assert first.endswith("\n")
    assert str(tmp_path) not in first
    assert "private-run-id" not in first
    assert "private-category" not in first
    assert "not-exported" not in first
    assert "password" not in first.lower()


class FakeCursor:
    def __init__(self, bucket: dt.datetime) -> None:
        self.bucket = bucket
        self.statements: list[str] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.statements.append(sql.strip())

    def fetchone(self) -> tuple[str]:
        return (audit.RELATION,)

    def fetchall(self) -> list[tuple[dt.datetime]]:
        return [(self.bucket,)]


class FakeTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


class FakeConnection:
    def __init__(self, bucket: dt.datetime) -> None:
        self.read_only = False
        self.cursor_value = FakeCursor(bucket)
        self.transaction_called = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def transaction(self) -> FakeTransaction:
        self.transaction_called = True
        return FakeTransaction()

    def cursor(self) -> FakeCursor:
        return self.cursor_value


def test_database_reader_uses_read_only_transaction_and_selects(monkeypatch) -> None:
    window = make_window(1)
    connection = FakeConnection(window.expected_buckets[0])
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_DB", "app")
    monkeypatch.setenv("POSTGRES_USER", "reader")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")

    result = audit.read_database_buckets(
        window.start_kst,
        window.end_kst,
        connect=lambda _conninfo: connection,
    )

    assert result.buckets == window.expected_buckets
    assert connection.read_only is True
    assert connection.transaction_called is True
    assert len(connection.cursor_value.statements) == 2
    assert all(statement.startswith("SELECT") for statement in connection.cursor_value.statements)


@pytest.mark.parametrize(
    ("classification", "expected"),
    [("clean", 0), ("degraded", 1), ("incomplete_evidence", 2)],
)
def test_classification_exit_codes(classification: str, expected: int) -> None:
    assert audit.classification_exit_code(classification) == expected


def test_invalid_cli_window_returns_two(capsys) -> None:
    exit_code = audit.run_cli(
        [
            "--window-start",
            "2026-01-01T00:00:00",
            "--window-end",
            "2026-01-01T01:00:00+09:00",
        ]
    )

    assert exit_code == 2
    assert "timestamp must include timezone" in capsys.readouterr().err
