"""Audit fixed Chzzk collection windows using sanitized wrapper and DB evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chzzk.normalize.category_lives import (
    KST,
    floor_to_kst_half_hour,
    format_kst_iso,
    parse_timestamp,
)

SCHEMA_VERSION = "1"
PROVIDER = "chzzk"
JOB_NAME = "chzzk_collection_window_integrity_audit"
INTERVAL_MINUTES = 30
INTERVAL = dt.timedelta(minutes=INTERVAL_MINUTES)
DEFAULT_WRAPPER_BASE_DIR = Path("tmp/chzzk/guarded-write-scheduler-wrapper")
RELATION = "fact_chzzk_category_30m"
BOUNDARY_ID_FORMAT = "%Y%m%dT%H%M%SZ"
NUMERIC_STRING_RE = re.compile(r"^[+-]?\d+$")
ARTIFACT_STATES = (
    "present_valid",
    "missing",
    "empty",
    "invalid_json",
    "invalid_shape",
    "unreadable",
)
WRAPPER_STATUSES = (
    "success",
    "partial_success",
    "hard_failure",
    "lock_busy",
    "missing",
    "unknown",
    "unrecognized",
)
_MISSING = object()

BucketReader = Callable[[dt.datetime, dt.datetime], "DatabaseReadResult"]


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """Validated half-open KST collection window."""

    start_kst: dt.datetime
    end_kst: dt.datetime
    expected_buckets: tuple[dt.datetime, ...]

    @property
    def expected_interval_count(self) -> int:
        return len(self.expected_buckets)


@dataclass(frozen=True, slots=True)
class JsonArtifact:
    """Parsed JSON object and its filesystem state."""

    state: str
    payload: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DatabaseReadResult:
    """Read-only database query result before classification."""

    query_status: str
    relation_available: bool | None
    buckets: tuple[dt.datetime, ...] = ()


@dataclass(frozen=True, slots=True)
class WrapperAudit:
    """Sanitized wrapper aggregates plus internal comparison evidence."""

    summary: dict[str, Any]
    mapped_buckets: frozenset[dt.datetime]
    comparison_ready: bool
    degraded_reasons: frozenset[str]
    incomplete_reasons: frozenset[str]


@dataclass(frozen=True, slots=True)
class DatabaseAudit:
    """Sanitized database aggregates plus internal comparison evidence."""

    summary: dict[str, Any]
    present_buckets: frozenset[dt.datetime]
    available: bool
    degraded_reasons: frozenset[str]
    incomplete_reasons: frozenset[str]


def parse_window(window_start: str | dt.datetime, window_end: str | dt.datetime) -> WindowSpec:
    """Validate and normalize a half-open KST 30-minute window."""

    start = parse_timestamp(window_start)
    end = parse_timestamp(window_end)
    if end <= start:
        raise ValueError("window_end must be later than window_start")

    duration_seconds = (end - start).total_seconds()
    if duration_seconds % INTERVAL.total_seconds() != 0:
        raise ValueError("window duration must be an integer multiple of 30 minutes")

    start_kst = start.astimezone(KST)
    end_kst = end.astimezone(KST)
    if floor_to_kst_half_hour(start_kst) != start_kst:
        raise ValueError("window_start must be on a KST 30-minute boundary")
    if floor_to_kst_half_hour(end_kst) != end_kst:
        raise ValueError("window_end must be on a KST 30-minute boundary")

    expected_count = int(duration_seconds // INTERVAL.total_seconds())
    expected_buckets = tuple(start_kst + index * INTERVAL for index in range(expected_count))
    return WindowSpec(
        start_kst=start_kst,
        end_kst=end_kst,
        expected_buckets=expected_buckets,
    )


def normalize_exit_code(value: object = _MISSING) -> tuple[str, int | None]:
    """Normalize integer or numeric-string wrapper exit codes."""

    if value is _MISSING or value is None:
        return "missing", None
    if isinstance(value, bool) or not isinstance(value, int | str):
        return "invalid", None
    if isinstance(value, str):
        normalized = value.strip()
        if not NUMERIC_STRING_RE.fullmatch(normalized):
            return "invalid", None
        parsed = int(normalized)
    else:
        parsed = value
    return ("zero" if parsed == 0 else "nonzero"), parsed


def read_json_artifact(path: Path) -> JsonArtifact:
    """Read one JSON object while preserving missing, empty, and invalid states."""

    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return JsonArtifact("missing")
    except OSError:
        return JsonArtifact("unreadable")
    if not raw:
        return JsonArtifact("empty")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonArtifact("invalid_json")
    if not isinstance(payload, Mapping):
        return JsonArtifact("invalid_shape")
    return JsonArtifact("present_valid", payload)


def _parse_boundary_id(name: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(name, BOUNDARY_ID_FORMAT).replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _looks_like_unmapped_run(path: Path) -> bool:
    if path.name == "locks" or path.name.startswith("."):
        return False
    return any(
        candidate.exists()
        for candidate in (
            path / "trace" / "end.json",
            path / "no-write-result.json",
            path / "guarded-write-result.json",
        )
    )


def _empty_state_counts() -> dict[str, int]:
    return {state: 0 for state in ARTIFACT_STATES}


def _artifact_reason(prefix: str, state: str) -> str:
    return f"wrapper_{prefix}_{state}"


def _wrapper_status(guarded: JsonArtifact) -> str:
    if guarded.state == "missing":
        return "missing"
    if guarded.state != "present_valid" or guarded.payload is None:
        return "unknown"
    status = guarded.payload.get("status")
    if status is None:
        return "missing"
    if not isinstance(status, str):
        return "unknown"
    return status if status in WRAPPER_STATUSES[:-1] else "unrecognized"


def _category_committed_state(guarded: JsonArtifact) -> tuple[str, int | None]:
    if guarded.payload is None:
        return "missing", None
    guarded_write = guarded.payload.get("guarded_write")
    if not isinstance(guarded_write, Mapping):
        return "missing", None
    category = guarded_write.get("category")
    if not isinstance(category, Mapping) or "committed_row_count" not in category:
        return "missing", None
    value = category["committed_row_count"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "invalid", None
    return ("positive" if value > 0 else "zero"), value


def audit_wrapper_evidence(base_dir: Path, window: WindowSpec) -> WrapperAudit:
    """Aggregate sanitized guarded-write wrapper evidence for one window."""

    state_counts = {
        "trace_end": _empty_state_counts(),
        "no_write_result": _empty_state_counts(),
        "guarded_write_result": _empty_state_counts(),
    }
    exit_counts = {"zero": 0, "nonzero": 0, "missing": 0, "invalid": 0}
    status_counts = {status: 0 for status in WRAPPER_STATUSES}
    category_counts = {"positive": 0, "zero": 0, "missing": 0, "invalid": 0}
    degraded: set[str] = set()
    incomplete: set[str] = set()
    mapped: list[dt.datetime] = []
    mapping_unavailable = 0
    conflict_count = 0
    confirmed_failure_count = 0

    try:
        children = list(base_dir.iterdir())
    except OSError:
        summary = {
            "base_status": "unavailable",
            "recognized_run_directory_count": 0,
            "unique_mapped_interval_count": 0,
            "missing_expected_interval_count": window.expected_interval_count,
            "duplicate_mapped_interval_count": 0,
            "mapping_unavailable_run_count": 0,
            "retention_covers_window": False,
            "exit_code_counts": exit_counts,
            "artifact_state_counts": state_counts,
            "guarded_status_counts": status_counts,
            "wrapper_status_exit_conflict_count": 0,
            "category": {
                "positive_committed_row_run_count": 0,
                "zero_committed_row_run_count": 0,
                "missing_committed_row_count": 0,
                "invalid_committed_row_count": 0,
            },
            "confirmed_failure_run_count": 0,
        }
        return WrapperAudit(
            summary=summary,
            mapped_buckets=frozenset(),
            comparison_ready=False,
            degraded_reasons=frozenset(),
            incomplete_reasons=frozenset({"wrapper_base_unavailable"}),
        )

    for run_dir in children:
        if not run_dir.is_dir():
            continue
        boundary = _parse_boundary_id(run_dir.name)
        if boundary is None:
            if _looks_like_unmapped_run(run_dir):
                mapping_unavailable += 1
            continue
        bucket = floor_to_kst_half_hour(boundary)
        if not (window.start_kst <= bucket < window.end_kst):
            continue

        mapped.append(bucket)
        artifacts = {
            "trace_end": read_json_artifact(run_dir / "trace" / "end.json"),
            "no_write_result": read_json_artifact(run_dir / "no-write-result.json"),
            "guarded_write_result": read_json_artifact(
                run_dir / "guarded-write-result.json"
            ),
        }
        for name, artifact in artifacts.items():
            state_counts[name][artifact.state] += 1
            if artifact.state == "present_valid":
                continue
            reason = _artifact_reason(name, artifact.state)
            if artifact.state == "unreadable":
                incomplete.add(reason)
            else:
                degraded.add(reason)

        trace_payload = artifacts["trace_end"].payload
        raw_exit = trace_payload.get("exit_code", _MISSING) if trace_payload else _MISSING
        exit_state, exit_code = normalize_exit_code(raw_exit)
        exit_counts[exit_state] += 1
        if exit_state == "nonzero":
            degraded.add("wrapper_nonzero_exit_code")
        elif exit_state in {"missing", "invalid"}:
            degraded.add(f"wrapper_exit_code_{exit_state}")

        guarded = artifacts["guarded_write_result"]
        status = _wrapper_status(guarded)
        status_counts[status] += 1
        if status != "success":
            degraded.add("wrapper_status_not_success")
        if status == "success" and exit_state == "nonzero":
            conflict_count += 1
            degraded.add("wrapper_exit_status_conflict")
        if exit_code is not None and exit_code != 0 and guarded.state == "missing":
            confirmed_failure_count += 1
        if exit_state == "zero" and guarded.state == "missing":
            degraded.add("wrapper_zero_exit_guarded_result_missing")

        category_state, _committed_rows = _category_committed_state(guarded)
        category_counts[category_state] += 1
        if category_state == "zero":
            degraded.add("wrapper_category_committed_rows_zero")
        elif category_state in {"missing", "invalid"}:
            degraded.add(f"wrapper_category_committed_rows_{category_state}")

    if mapping_unavailable:
        incomplete.add("wrapper_mapping_unavailable")

    bucket_counts = Counter(mapped)
    mapped_set = frozenset(bucket_counts)
    duplicate_count = sum(count - 1 for count in bucket_counts.values() if count > 1)
    if duplicate_count:
        degraded.add("wrapper_duplicate_interval")

    expected_set = frozenset(window.expected_buckets)
    missing_count = len(expected_set - mapped_set)
    retention_covers_window = bool(
        mapped_set
        and window.expected_buckets[0] in mapped_set
        and window.expected_buckets[-1] in mapped_set
    )
    if missing_count:
        if retention_covers_window:
            degraded.add("wrapper_expected_interval_missing")
        else:
            incomplete.add("wrapper_window_evidence_incomplete")

    summary = {
        "base_status": "available",
        "recognized_run_directory_count": len(mapped),
        "unique_mapped_interval_count": len(mapped_set),
        "missing_expected_interval_count": missing_count,
        "duplicate_mapped_interval_count": duplicate_count,
        "mapping_unavailable_run_count": mapping_unavailable,
        "retention_covers_window": retention_covers_window,
        "exit_code_counts": exit_counts,
        "artifact_state_counts": state_counts,
        "guarded_status_counts": status_counts,
        "wrapper_status_exit_conflict_count": conflict_count,
        "category": {
            "positive_committed_row_run_count": category_counts["positive"],
            "zero_committed_row_run_count": category_counts["zero"],
            "missing_committed_row_count": category_counts["missing"],
            "invalid_committed_row_count": category_counts["invalid"],
        },
        "confirmed_failure_run_count": confirmed_failure_count,
    }
    return WrapperAudit(
        summary=summary,
        mapped_buckets=mapped_set,
        comparison_ready=retention_covers_window and mapping_unavailable == 0,
        degraded_reasons=frozenset(degraded),
        incomplete_reasons=frozenset(incomplete),
    )


def _build_pg_conninfo_from_env(environ: Mapping[str, str]) -> str:
    required = ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    values = {name: environ.get(name) for name in required}
    if any(not value for value in values.values()):
        raise RuntimeError("required Postgres environment is unavailable")
    try:
        from psycopg.conninfo import make_conninfo
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency is locked.
        raise RuntimeError("psycopg is unavailable") from exc
    return make_conninfo(
        host=values["POSTGRES_HOST"],
        port=environ.get("POSTGRES_PORT", "5432"),
        dbname=values["POSTGRES_DB"],
        user=values["POSTGRES_USER"],
        password=values["POSTGRES_PASSWORD"],
    )


def _default_pg_connect(conninfo: str) -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency is locked.
        raise RuntimeError("psycopg is unavailable") from exc
    return psycopg.connect(conninfo=conninfo)


def read_database_buckets(
    window_start: dt.datetime,
    window_end: dt.datetime,
    *,
    connect: Callable[[str], Any] = _default_pg_connect,
    environ: Mapping[str, str] | None = None,
) -> DatabaseReadResult:
    """Read distinct global category buckets in an explicit read-only transaction."""

    conninfo = _build_pg_conninfo_from_env(environ or os.environ)
    with connect(conninfo) as connection:
        connection.read_only = True
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass(%s)", (RELATION,))
                relation_row = cursor.fetchone()
                relation = relation_row[0] if relation_row else None
                if relation is None:
                    return DatabaseReadResult(
                        query_status="success",
                        relation_available=False,
                    )
                cursor.execute(
                    """
                    SELECT DISTINCT bucket_time
                    FROM fact_chzzk_category_30m
                    WHERE bucket_time >= %s
                      AND bucket_time < %s
                    ORDER BY bucket_time
                    """,
                    (window_start, window_end),
                )
                buckets = tuple(row[0] for row in cursor.fetchall())
    return DatabaseReadResult(
        query_status="success",
        relation_available=True,
        buckets=buckets,
    )


def audit_database_evidence(
    window: WindowSpec,
    bucket_reader: BucketReader,
) -> DatabaseAudit:
    """Compare read-only global DB bucket evidence with expected positions."""

    try:
        result = bucket_reader(window.start_kst, window.end_kst)
    except Exception:
        return DatabaseAudit(
            summary={
                "query_status": "unavailable",
                "relation_availability": "unknown",
                "expected_bucket_count": window.expected_interval_count,
                "present_distinct_bucket_count": 0,
                "missing_bucket_count": window.expected_interval_count,
                "unexpected_bucket_count": 0,
            },
            present_buckets=frozenset(),
            available=False,
            degraded_reasons=frozenset(),
            incomplete_reasons=frozenset({"database_query_unavailable"}),
        )

    if result.query_status != "success":
        return DatabaseAudit(
            summary={
                "query_status": "unavailable",
                "relation_availability": "unknown",
                "expected_bucket_count": window.expected_interval_count,
                "present_distinct_bucket_count": 0,
                "missing_bucket_count": window.expected_interval_count,
                "unexpected_bucket_count": 0,
            },
            present_buckets=frozenset(),
            available=False,
            degraded_reasons=frozenset(),
            incomplete_reasons=frozenset({"database_query_unavailable"}),
        )
    if result.relation_available is not True:
        return DatabaseAudit(
            summary={
                "query_status": "success",
                "relation_availability": "missing",
                "expected_bucket_count": window.expected_interval_count,
                "present_distinct_bucket_count": 0,
                "missing_bucket_count": window.expected_interval_count,
                "unexpected_bucket_count": 0,
            },
            present_buckets=frozenset(),
            available=False,
            degraded_reasons=frozenset(),
            incomplete_reasons=frozenset({"database_relation_unavailable"}),
        )

    try:
        present_values: set[dt.datetime] = set()
        for value in result.buckets:
            if not isinstance(value, str | dt.datetime):
                raise TypeError("database bucket must be datetime-like")
            present_values.add(parse_timestamp(value).astimezone(KST))
        present = frozenset(present_values)
    except (TypeError, ValueError):
        return DatabaseAudit(
            summary={
                "query_status": "unavailable",
                "relation_availability": "available",
                "expected_bucket_count": window.expected_interval_count,
                "present_distinct_bucket_count": 0,
                "missing_bucket_count": window.expected_interval_count,
                "unexpected_bucket_count": 0,
            },
            present_buckets=frozenset(),
            available=False,
            degraded_reasons=frozenset(),
            incomplete_reasons=frozenset({"database_bucket_evidence_invalid"}),
        )

    expected = frozenset(window.expected_buckets)
    missing_count = len(expected - present)
    unexpected_count = len(present - expected)
    degraded: set[str] = set()
    if missing_count:
        degraded.add("database_global_bucket_missing")
    if unexpected_count:
        degraded.add("database_unexpected_bucket_position")
    return DatabaseAudit(
        summary={
            "query_status": "success",
            "relation_availability": "available",
            "expected_bucket_count": window.expected_interval_count,
            "present_distinct_bucket_count": len(present),
            "missing_bucket_count": missing_count,
            "unexpected_bucket_count": unexpected_count,
        },
        present_buckets=present,
        available=True,
        degraded_reasons=frozenset(degraded),
        incomplete_reasons=frozenset(),
    )


def build_audit_report(
    *,
    window: WindowSpec,
    wrapper_base_dir: Path,
    bucket_reader: BucketReader = read_database_buckets,
) -> dict[str, Any]:
    """Build a deterministic aggregate-only collection window audit report."""

    wrapper = audit_wrapper_evidence(wrapper_base_dir, window)
    database = audit_database_evidence(window, bucket_reader)
    degraded = set(wrapper.degraded_reasons | database.degraded_reasons)
    incomplete = set(wrapper.incomplete_reasons | database.incomplete_reasons)
    if (
        wrapper.comparison_ready
        and database.available
        and wrapper.mapped_buckets != database.present_buckets
    ):
        degraded.add("wrapper_database_bucket_contradiction")

    if degraded:
        classification = "degraded"
        reasons = sorted(degraded | incomplete)
    elif incomplete:
        classification = "incomplete_evidence"
        reasons = sorted(incomplete)
    else:
        classification = "clean"
        reasons = []

    return {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "job_name": JOB_NAME,
        "classification": classification,
        "reasons": reasons,
        "window": {
            "start_kst": format_kst_iso(window.start_kst),
            "end_kst": format_kst_iso(window.end_kst),
            "interval_minutes": INTERVAL_MINUTES,
            "expected_interval_count": window.expected_interval_count,
        },
        "wrapper": wrapper.summary,
        "database": database.summary,
        "caveats": {
            "clean_scope": "scheduler_wrapper_global_category_fact_collection_only",
            "category_absence_is_zero": False,
            "full_live_list_completeness_proven": False,
            "category_level_coverage_evaluated": False,
        },
    }


def render_summary(report: Mapping[str, Any]) -> str:
    """Render a concise human-readable audit summary."""

    window = report["window"]
    wrapper = report["wrapper"]
    database = report["database"]
    reasons = report["reasons"]
    return "\n".join(
        (
            "Chzzk collection window integrity audit",
            f"classification: {report['classification']}",
            f"window: [{window['start_kst']}, {window['end_kst']})",
            f"expected intervals: {window['expected_interval_count']}",
            "wrapper intervals: "
            f"{wrapper['unique_mapped_interval_count']}/{window['expected_interval_count']} "
            f"(runs={wrapper['recognized_run_directory_count']})",
            "database buckets: "
            f"{database['present_distinct_bucket_count']}/{window['expected_interval_count']}",
            f"reasons: {', '.join(reasons) if reasons else 'none'}",
        )
    )


def write_report_json(path: Path, report: Mapping[str, Any]) -> None:
    """Write deterministic sanitized JSON with a trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def classification_exit_code(classification: str) -> int:
    """Map the stable classification contract to process exit status."""

    return {"clean": 0, "degraded": 1, "incomplete_evidence": 2}[classification]


def build_parser() -> argparse.ArgumentParser:
    """Build the collection window audit CLI parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Audit sanitized Chzzk guarded-write evidence against read-only global "
            "category buckets."
        )
    )
    parser.add_argument("--window-start", required=True, help="timezone-aware ISO 8601 start")
    parser.add_argument("--window-end", required=True, help="timezone-aware ISO 8601 end")
    parser.add_argument(
        "--wrapper-base-dir",
        type=Path,
        default=DEFAULT_WRAPPER_BASE_DIR,
        help="sanitized guarded-write wrapper evidence directory",
    )
    parser.add_argument("--output-path", type=Path, help="optional sanitized JSON output path")
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return classification-specific process status."""

    args = build_parser().parse_args(argv)
    try:
        window = parse_window(args.window_start, args.window_end)
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = build_audit_report(
        window=window,
        wrapper_base_dir=args.wrapper_base_dir,
    )
    print(render_summary(report))
    if args.output_path is not None:
        try:
            write_report_json(args.output_path, report)
        except OSError:
            print("error: unable to write sanitized JSON output", file=sys.stderr)
            return 2
    return classification_exit_code(str(report["classification"]))


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
