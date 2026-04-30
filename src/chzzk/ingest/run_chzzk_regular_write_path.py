"""Dry-run wrapper for the Chzzk regular write-path boundary."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from chzzk.normalize import category_result_to_gold, channel_result_to_gold
from chzzk.probe.live_list_temporal_probe import read_json
from steam.common.execution_meta import utc_now_iso

PROVIDER = "chzzk"
JOB_NAME = "chzzk_regular_write_path"
MODE = "dry-run"
SCHEMA_VERSION = "1"
DEFAULT_BASE_DIR = Path("tmp/chzzk/regular-write-path")
LOCK_BUSY_EXIT_CODE = 75
LOCK_BASENAME = "chzzk-regular-write-path.lock"
CATEGORY_RELATION = "fact_chzzk_category_30m"
CHANNEL_RELATION = "fact_chzzk_category_channel_30m"
CATEGORY_DDL_REF = "sql/postgres/015_fact_chzzk_category_30m.sql"
CHANNEL_DDL_REF = "sql/postgres/016_fact_chzzk_category_channel_30m.sql"
RELATION_CHECK_SQL = "SELECT to_regclass(%s)"
RETENTION_CAVEAT = (
    "Chzzk regular write-path wrapper evidence remains local/private; raw provider "
    "payload and derived JSONL artifacts must not be promoted to public docs, "
    "fixtures, APIs, or UI."
)


class RelationPreconditionUnavailable(RuntimeError):
    """Raised when relation readiness cannot be checked safely."""


@dataclass(frozen=True, slots=True)
class RelationSpec:
    role: str
    relation: str
    ddl_ref: str


@dataclass(frozen=True, slots=True)
class WrapperPaths:
    """Resolved local/private paths for one wrapper run."""

    run_id: str
    run_dir: Path
    result_path: Path
    lock_path: Path

    @property
    def result_ref(self) -> str:
        return f"{self.run_id}/result.json"

    @property
    def lock_ref(self) -> str:
        return self.lock_path.name


class NoOverlapLock:
    """Small fcntl-based lock for one local Chzzk wrapper boundary."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: Any | None = None

    def acquire(self, *, wait_seconds: float = 0.0) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + max(wait_seconds, 0.0)

        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                self._write_owner()
                return True
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if wait_seconds <= 0.0 or remaining <= 0.0:
                    handle.close()
                    return False
                time.sleep(min(0.25, remaining))

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None

    def _write_owner(self) -> None:
        if self._handle is None:
            return
        owner = {"locked_at_utc": utc_now_iso(), "pid": os.getpid()}
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(json.dumps(owner, ensure_ascii=True, sort_keys=True))
        self._handle.write("\n")
        self._handle.flush()


RELATION_SPECS = (
    RelationSpec("category", CATEGORY_RELATION, CATEGORY_DDL_REF),
    RelationSpec("channel", CHANNEL_RELATION, CHANNEL_DDL_REF),
)


def _utc_run_id() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _parse_iso_utc(value: str) -> dt.datetime:
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _duration_ms(started_at_utc: str, finished_at_utc: str) -> int:
    started_at = _parse_iso_utc(started_at_utc)
    finished_at = _parse_iso_utc(finished_at_utc)
    return int((finished_at - started_at).total_seconds() * 1000)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_paths(
    *,
    base_dir: Path = DEFAULT_BASE_DIR,
    run_id: str | None = None,
) -> WrapperPaths:
    """Resolve wrapper-local artifact paths without exposing them in summaries."""

    resolved_run_id = run_id or _utc_run_id()
    run_dir = base_dir / resolved_run_id
    return WrapperPaths(
        run_id=resolved_run_id,
        run_dir=run_dir,
        result_path=run_dir / "result.json",
        lock_path=base_dir / "locks" / LOCK_BASENAME,
    )


def require_psycopg() -> Any:
    """Import psycopg for read-only relation checks."""

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RelationPreconditionUnavailable("psycopg_unavailable") from exc
    return psycopg


def build_pg_conninfo_from_env(environ: Mapping[str, str] | None = None) -> str:
    """Build Postgres conninfo without logging or summarizing env details."""

    source = environ or os.environ
    required_names = (
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    if any(not source.get(name) for name in required_names):
        raise RelationPreconditionUnavailable("db_env_unavailable")
    port = source.get("POSTGRES_PORT", "5432")
    return (
        f"host={source['POSTGRES_HOST']} port={port} dbname={source['POSTGRES_DB']} "
        f"user={source['POSTGRES_USER']} password={source['POSTGRES_PASSWORD']}"
    )


def _base_relation_result(spec: RelationSpec) -> dict[str, Any]:
    return {
        "checked": False,
        "ddl_ref": spec.ddl_ref,
        "relation": spec.relation,
        "role": spec.role,
        "status": "not_started",
    }


def _relation_value(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row.get("to_regclass")
    return row[0]


def check_relation_preconditions() -> dict[str, dict[str, Any]]:
    """Check required Chzzk fact relations without applying DDL."""

    results = {spec.role: _base_relation_result(spec) for spec in RELATION_SPECS}
    try:
        psycopg = require_psycopg()
        conninfo = build_pg_conninfo_from_env()
        with psycopg.connect(conninfo=conninfo) as conn:
            with conn.cursor() as cursor:
                for spec in RELATION_SPECS:
                    cursor.execute(RELATION_CHECK_SQL, (spec.relation,))
                    relation = _relation_value(cursor.fetchone())
                    results[spec.role].update(
                        {
                            "checked": True,
                            "status": "exists" if relation is not None else "missing",
                        }
                    )
    except RelationPreconditionUnavailable:
        for result in results.values():
            if result["status"] == "not_started":
                result.update({"checked": False, "status": "unavailable"})
        return results
    except Exception:
        for result in results.values():
            if result["status"] == "not_started":
                result.update({"checked": False, "status": "failed"})
        return results
    return results


def _relation_failure_class(results: Mapping[str, Mapping[str, Any]]) -> str | None:
    for role in ("category", "channel"):
        status = results[role]["status"]
        if status == "missing":
            return f"{role}_relation_missing"
        if status == "unavailable":
            return "relation_precondition_unavailable"
        if status == "failed":
            return "relation_check_failed"
    return None


def _safe_artifact_ref(probe_run_id: str, basename: str) -> dict[str, str]:
    return {
        "basename": basename,
        "run_relative_ref": f"{probe_run_id}/{basename}",
    }


def _artifact_result(
    *,
    probe_run_id: str,
    role: str,
    basename: str,
    exists: bool,
) -> dict[str, Any]:
    return {
        **_safe_artifact_ref(probe_run_id, basename),
        "exists": exists,
        "role": role,
        "status": "present" if exists else "missing",
    }


def check_probe_artifacts(probe_run_dir: Path) -> dict[str, dict[str, Any]]:
    """Check selected probe artifacts using only safe refs in returned data."""

    probe_run_id = probe_run_dir.name
    return {
        "summary": _artifact_result(
            probe_run_id=probe_run_id,
            role="probe_summary",
            basename="summary.json",
            exists=(probe_run_dir / "summary.json").is_file(),
        ),
        "category": _artifact_result(
            probe_run_id=probe_run_id,
            role="category_result",
            basename="category-result.jsonl",
            exists=(probe_run_dir / "category-result.jsonl").is_file(),
        ),
        "channel": _artifact_result(
            probe_run_id=probe_run_id,
            role="channel_result",
            basename="channel-result.jsonl",
            exists=(probe_run_dir / "channel-result.jsonl").is_file(),
        ),
    }


def _skip_reason_counts(rows: Sequence[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(row.reason) for row in rows).items()))


def _empty_plan(status: str) -> dict[str, Any]:
    return {
        "committed_row_count": 0,
        "failed_row_count": 0,
        "input_row_count": 0,
        "load_attempted": False,
        "planned_upsert_attempt_count": 0,
        "skipped_row_count": 0,
        "skip_reasons": {},
        "status": status,
        "valid_row_count": 0,
    }


def plan_category_dry_run(input_path: Path) -> dict[str, Any]:
    """Validate category JSONL and count dry-run upsert candidates."""

    try:
        parsed = category_result_to_gold.load_category_result_rows(input_path)
    except OSError:
        return {**_empty_plan("read_failed"), "failure_class": "category_artifact_read_failed"}
    except Exception:
        return {**_empty_plan("parse_failed"), "failure_class": "category_parse_failed"}

    valid_row_count = len(parsed.valid_rows)
    status = "dry_run_planned" if valid_row_count > 0 else "no_usable_rows"
    result = {
        "committed_row_count": 0,
        "failed_row_count": 0,
        "input_row_count": parsed.input_row_count,
        "load_attempted": False,
        "planned_upsert_attempt_count": valid_row_count,
        "skipped_row_count": len(parsed.skipped_rows),
        "skip_reasons": _skip_reason_counts(parsed.skipped_rows),
        "status": status,
        "valid_row_count": valid_row_count,
    }
    if valid_row_count == 0:
        result["failure_class"] = "category_no_usable_rows"
    return result


def plan_channel_dry_run(input_path: Path) -> dict[str, Any]:
    """Validate channel JSONL and count dry-run upsert candidates."""

    try:
        parsed = channel_result_to_gold.load_channel_result_rows(input_path)
    except OSError:
        return {**_empty_plan("read_failed"), "failure_class": "channel_artifact_read_failed"}
    except Exception:
        return {**_empty_plan("parse_failed"), "failure_class": "channel_parse_failed"}

    valid_row_count = len(parsed.valid_rows)
    status = "dry_run_planned" if valid_row_count > 0 else "no_usable_rows"
    result = {
        "committed_row_count": 0,
        "failed_row_count": 0,
        "input_row_count": parsed.input_row_count,
        "load_attempted": False,
        "planned_upsert_attempt_count": valid_row_count,
        "skipped_row_count": len(parsed.skipped_rows),
        "skip_reasons": _skip_reason_counts(parsed.skipped_rows),
        "status": status,
        "valid_row_count": valid_row_count,
    }
    if valid_row_count == 0:
        result["failure_class"] = "channel_no_usable_rows"
    return result


def _bounded_sample_caveat(probe_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if probe_summary is None:
        return {
            "bounded_sample": True,
            "bounded_page_cutoff": None,
            "last_page_next_present": None,
            "source": "probe_summary_unavailable",
        }
    pagination = probe_summary.get("pagination")
    if not isinstance(pagination, Mapping):
        pagination = {}
    coverage = probe_summary.get("coverage")
    if not isinstance(coverage, Mapping):
        coverage = {}
    return {
        "bounded_sample": True,
        "bounded_page_cutoff": pagination.get("bounded_page_cutoff"),
        "coverage_status": coverage.get("status"),
        "last_page_next_present": pagination.get("last_page_next_present"),
        "pages_fetched": pagination.get("pages_fetched", probe_summary.get("pages_fetched")),
        "pages_requested": pagination.get(
            "pages_requested",
            probe_summary.get("pages_requested"),
        ),
        "source": "selected_probe_summary_fields",
    }


def _read_probe_summary(probe_run_dir: Path) -> Mapping[str, Any] | None:
    try:
        payload = read_json(probe_run_dir / "summary.json")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def disabled_temporal_hook() -> dict[str, Any]:
    """Return the disabled temporal hook evidence for this dry-run slice."""

    return {
        "enabled": False,
        "status": "disabled",
    }


def disabled_api_read_smoke() -> dict[str, Any]:
    """Return disabled API read smoke evidence."""

    return {
        "enabled": False,
        "failure_class": None,
        "http_status": None,
        "status": "disabled",
    }


def run_api_read_smoke(url: str, *, client: Any | None = None) -> dict[str, Any]:
    """Run an optional GET-only route reachability smoke without storing the body."""

    close_client = False
    smoke_client = client
    if smoke_client is None:
        smoke_client = httpx.Client(timeout=10.0)
        close_client = True
    try:
        response = smoke_client.get(url)
        http_status = int(response.status_code)
        if 200 <= http_status < 400:
            return {
                "enabled": True,
                "failure_class": None,
                "http_status": http_status,
                "status": "success",
            }
        return {
            "enabled": True,
            "failure_class": "api_read_smoke_http_status",
            "http_status": http_status,
            "status": "failed",
        }
    except Exception:
        return {
            "enabled": True,
            "failure_class": "api_read_smoke_request_failed",
            "http_status": None,
            "status": "failed",
        }
    finally:
        close = getattr(smoke_client, "close", None)
        if close_client and callable(close):
            close()


def _build_result(
    *,
    paths: WrapperPaths,
    started_at_utc: str,
    finished_at_utc: str,
    status: str,
    failure_class: str | None,
    relation_preconditions: Mapping[str, Any],
    artifact_checks: Mapping[str, Any],
    category_plan: Mapping[str, Any],
    channel_plan: Mapping[str, Any],
    bounded_sample_caveat: Mapping[str, Any],
    temporal_summary_hook: Mapping[str, Any],
    api_read_smoke: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "api_read_smoke": api_read_smoke,
        "artifact_checks": artifact_checks,
        "bounded_sample_caveat": bounded_sample_caveat,
        "category": category_plan,
        "channel": channel_plan,
        "duration_ms": _duration_ms(started_at_utc, finished_at_utc),
        "failure_class": failure_class,
        "finished_at_utc": finished_at_utc,
        "hard_failure": status == "hard_failure",
        "job_name": JOB_NAME,
        "lock": {
            "lock_ref": paths.lock_ref,
            "status": "busy" if status == "lock_busy" else "acquired",
        },
        "lock_busy": status == "lock_busy",
        "mode": MODE,
        "partial_success": status == "partial_success",
        "provider": PROVIDER,
        "relation_preconditions": relation_preconditions,
        "result_ref": paths.result_ref,
        "retention_caveat": RETENTION_CAVEAT,
        "run_id": paths.run_id,
        "sanitization": {
            "absolute_local_paths_in_summary": False,
            "api_response_body_in_summary": False,
            "credentials_in_summary": False,
            "db_env_details_in_summary": False,
            "provider_label_values_in_summary": False,
            "raw_jsonl_rows_in_summary": False,
            "raw_provider_payload_in_summary": False,
            "scheduler_details_in_summary": False,
        },
        "schema_version": SCHEMA_VERSION,
        "started_at_utc": started_at_utc,
        "status": status,
        "success": status in {"success", "partial_success"},
        "temporal_summary_hook": temporal_summary_hook,
    }


def _relation_failure_summary(
    *,
    paths: WrapperPaths,
    started_at_utc: str,
    relation_preconditions: Mapping[str, Any],
) -> dict[str, Any]:
    finished_at_utc = utc_now_iso()
    return _build_result(
        paths=paths,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        status="hard_failure",
        failure_class=_relation_failure_class(relation_preconditions),
        relation_preconditions=relation_preconditions,
        artifact_checks={},
        category_plan=_empty_plan("skipped_due_to_relation_precondition_failure"),
        channel_plan=_empty_plan("skipped_due_to_relation_precondition_failure"),
        bounded_sample_caveat=_bounded_sample_caveat(None),
        temporal_summary_hook=disabled_temporal_hook(),
        api_read_smoke=disabled_api_read_smoke(),
    )


def _lock_busy_summary(*, paths: WrapperPaths, started_at_utc: str) -> dict[str, Any]:
    finished_at_utc = utc_now_iso()
    return _build_result(
        paths=paths,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        status="lock_busy",
        failure_class="lock_busy",
        relation_preconditions={},
        artifact_checks={},
        category_plan=_empty_plan("not_started"),
        channel_plan=_empty_plan("not_started"),
        bounded_sample_caveat=_bounded_sample_caveat(None),
        temporal_summary_hook=disabled_temporal_hook(),
        api_read_smoke=disabled_api_read_smoke(),
    )


def _hard_failure_result(
    *,
    paths: WrapperPaths,
    started_at_utc: str,
    failure_class: str,
    relation_preconditions: Mapping[str, Any],
    artifact_checks: Mapping[str, Any],
    category_plan: Mapping[str, Any],
    channel_plan: Mapping[str, Any],
    probe_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return _build_result(
        paths=paths,
        started_at_utc=started_at_utc,
        finished_at_utc=utc_now_iso(),
        status="hard_failure",
        failure_class=failure_class,
        relation_preconditions=relation_preconditions,
        artifact_checks=artifact_checks,
        category_plan=category_plan,
        channel_plan=channel_plan,
        bounded_sample_caveat=_bounded_sample_caveat(probe_summary),
        temporal_summary_hook=disabled_temporal_hook(),
        api_read_smoke=disabled_api_read_smoke(),
    )


def run_wrapper(
    *,
    probe_run_dir: Path,
    base_dir: Path = DEFAULT_BASE_DIR,
    run_id: str | None = None,
    lock_wait_seconds: float = 0.0,
    api_smoke_url: str | None = None,
    api_client: Any | None = None,
) -> dict[str, Any]:
    """Run the dry-run wrapper and persist one sanitized result summary."""

    started_at_utc = utc_now_iso()
    paths = build_paths(base_dir=base_dir, run_id=run_id)
    lock = NoOverlapLock(paths.lock_path)
    acquired = lock.acquire(wait_seconds=lock_wait_seconds)
    if not acquired:
        result = _lock_busy_summary(paths=paths, started_at_utc=started_at_utc)
        _write_json(paths.result_path, result)
        return result

    try:
        relation_preconditions = check_relation_preconditions()
        relation_failure_class = _relation_failure_class(relation_preconditions)
        if relation_failure_class is not None:
            result = _relation_failure_summary(
                paths=paths,
                started_at_utc=started_at_utc,
                relation_preconditions=relation_preconditions,
            )
            _write_json(paths.result_path, result)
            return result

        artifact_checks = check_probe_artifacts(probe_run_dir)
        probe_summary = _read_probe_summary(probe_run_dir)
        if not artifact_checks["summary"]["exists"]:
            result = _hard_failure_result(
                paths=paths,
                started_at_utc=started_at_utc,
                failure_class="probe_summary_missing",
                relation_preconditions=relation_preconditions,
                artifact_checks=artifact_checks,
                category_plan=_empty_plan("skipped_due_to_probe_summary_missing"),
                channel_plan=_empty_plan("skipped_after_category_unusable"),
                probe_summary=probe_summary,
            )
            _write_json(paths.result_path, result)
            return result
        if probe_summary is None:
            result = _hard_failure_result(
                paths=paths,
                started_at_utc=started_at_utc,
                failure_class="probe_summary_read_failed",
                relation_preconditions=relation_preconditions,
                artifact_checks=artifact_checks,
                category_plan=_empty_plan("skipped_due_to_probe_summary_read_failed"),
                channel_plan=_empty_plan("skipped_after_category_unusable"),
                probe_summary=probe_summary,
            )
            _write_json(paths.result_path, result)
            return result
        if not artifact_checks["category"]["exists"]:
            result = _hard_failure_result(
                paths=paths,
                started_at_utc=started_at_utc,
                failure_class="category_artifact_missing",
                relation_preconditions=relation_preconditions,
                artifact_checks=artifact_checks,
                category_plan=_empty_plan("missing"),
                channel_plan=_empty_plan("skipped_after_category_unusable"),
                probe_summary=probe_summary,
            )
            _write_json(paths.result_path, result)
            return result

        category_plan = plan_category_dry_run(probe_run_dir / "category-result.jsonl")
        category_failure_class = category_plan.get("failure_class")
        if category_failure_class is not None:
            result = _hard_failure_result(
                paths=paths,
                started_at_utc=started_at_utc,
                failure_class=str(category_failure_class),
                relation_preconditions=relation_preconditions,
                artifact_checks=artifact_checks,
                category_plan=category_plan,
                channel_plan=_empty_plan("skipped_after_category_unusable"),
                probe_summary=probe_summary,
            )
            _write_json(paths.result_path, result)
            return result

        status = "success"
        failure_class: str | None = None
        if not artifact_checks["channel"]["exists"]:
            status = "partial_success"
            failure_class = "channel_artifact_missing"
            channel_plan = _empty_plan("missing")
            channel_plan["failure_class"] = failure_class
        else:
            channel_plan = plan_channel_dry_run(probe_run_dir / "channel-result.jsonl")
            channel_failure_class = channel_plan.get("failure_class")
            if channel_failure_class is not None:
                status = "partial_success"
                failure_class = str(channel_failure_class)

        api_read_smoke = (
            run_api_read_smoke(api_smoke_url, client=api_client)
            if api_smoke_url is not None
            else disabled_api_read_smoke()
        )
        result = _build_result(
            paths=paths,
            started_at_utc=started_at_utc,
            finished_at_utc=utc_now_iso(),
            status=status,
            failure_class=failure_class,
            relation_preconditions=relation_preconditions,
            artifact_checks=artifact_checks,
            category_plan=category_plan,
            channel_plan=channel_plan,
            bounded_sample_caveat=_bounded_sample_caveat(probe_summary),
            temporal_summary_hook=disabled_temporal_hook(),
            api_read_smoke=api_read_smoke,
        )
        _write_json(paths.result_path, result)
        return result
    finally:
        lock.release()


def run_wrapper_with_evidence(
    *,
    probe_run_dir: Path,
    base_dir: Path = DEFAULT_BASE_DIR,
    run_id: str | None = None,
    lock_wait_seconds: float = 0.0,
    api_smoke_url: str | None = None,
    api_client: Any | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for tests and scheduler-like callers."""

    return run_wrapper(
        probe_run_dir=probe_run_dir,
        base_dir=base_dir,
        run_id=run_id,
        lock_wait_seconds=lock_wait_seconds,
        api_smoke_url=api_smoke_url,
        api_client=api_client,
    )


def exit_code_for_status(status: str) -> int:
    """Return scheduler-friendly process exit code for a wrapper status."""

    if status in {"success", "partial_success"}:
        return 0
    if status == "lock_busy":
        return LOCK_BUSY_EXIT_CODE
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the dry-run Chzzk regular write-path wrapper."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-run-dir", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--lock-wait-sec", type=float, default=0.0)
    parser.add_argument(
        "--api-smoke-url",
        default=None,
        help="Optional GET-only route reachability smoke against an already-running API",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for the dry-run Chzzk regular write-path wrapper."""

    args = build_parser().parse_args(argv)
    result = run_wrapper_with_evidence(
        probe_run_dir=args.probe_run_dir,
        base_dir=args.base_dir,
        run_id=args.run_id,
        lock_wait_seconds=args.lock_wait_sec,
        api_smoke_url=args.api_smoke_url,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    raise SystemExit(exit_code_for_status(str(result["status"])))


if __name__ == "__main__":
    main()
