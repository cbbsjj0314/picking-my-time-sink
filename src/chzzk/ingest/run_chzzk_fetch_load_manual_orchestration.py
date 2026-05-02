"""Manual Chzzk bounded fetch-load orchestration boundary."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from chzzk.ingest import run_chzzk_recurring_write_path as recurring
from chzzk.ingest import run_chzzk_regular_write_path as regular
from chzzk.probe import live_list_temporal_probe
from steam.common.execution_meta import utc_now_iso

PROVIDER = "chzzk"
JOB_NAME = "chzzk_fetch_load_manual_orchestration"
SCHEMA_VERSION = "1"
DEFAULT_BASE_DIR = Path("tmp/chzzk/fetch-load-manual-orchestration")
DEFAULT_PROBE_OUTPUT_DIR = Path("tmp/chzzk/temporal-probe")
LOCK_BASENAME = "chzzk-fetch-load-manual-orchestration.lock"
LOCK_BUSY_EXIT_CODE = regular.LOCK_BUSY_EXIT_CODE
DEFAULT_FETCH_PAGES = 3
DEFAULT_FETCH_SIZE = 20
SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
REQUIRED_CHZZK_ENV = ("CHZZK_CLIENT_ID", "CHZZK_CLIENT_SECRET")
REQUIRED_DB_ENV = ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")

Fetcher = Callable[..., Mapping[str, Any]]
RecurringRunner = Callable[..., Mapping[str, Any]]
RelationChecker = Callable[[], Mapping[str, Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class OrchestrationPaths:
    """Resolved local/private paths for one manual orchestration run."""

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


def _utc_run_id() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")


def build_paths(
    *,
    base_dir: Path = DEFAULT_BASE_DIR,
    run_id: str | None = None,
) -> OrchestrationPaths:
    """Resolve orchestration-local paths without exposing absolute refs."""

    resolved_run_id = run_id or _utc_run_id()
    return OrchestrationPaths(
        run_id=resolved_run_id,
        run_dir=base_dir / resolved_run_id,
        result_path=base_dir / resolved_run_id / "result.json",
        lock_path=base_dir / "locks" / LOCK_BASENAME,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _duration_ms(started_at_utc: str, finished_at_utc: str) -> int:
    return regular._duration_ms(started_at_utc, finished_at_utc)


def _safe_run_id(value: str | None) -> str | None:
    if value is None:
        return None
    if value in {".", ".."}:
        return None
    if "/" in value or "\\" in value:
        return None
    if Path(value).is_absolute():
        return None
    if SAFE_RUN_ID_RE.fullmatch(value) is None:
        return None
    return value


def _presence(names: Sequence[str], environ: Mapping[str, str]) -> dict[str, str]:
    return {name: "present" if environ.get(name) else "missing" for name in names}


def _presence_failure_class(prefix: str, presence: Mapping[str, str]) -> str | None:
    missing = [name for name, status in presence.items() if status != "present"]
    return f"{prefix}_env_missing" if missing else None


def _line_count(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return None


def _artifact_entry(probe_run_id: str, basename: str, path: Path) -> dict[str, Any]:
    exists = path.is_file()
    entry: dict[str, Any] = {
        "basename": basename,
        "exists": exists,
        "run_relative_ref": f"{probe_run_id}/{basename}",
        "status": "present" if exists else "missing",
    }
    if basename.endswith(".jsonl"):
        entry["line_count"] = _line_count(path) if exists else None
    return entry


def check_selected_artifact(probe_run_dir: Path) -> dict[str, dict[str, Any]]:
    """Check selected probe artifacts using only basename/run-relative refs."""

    probe_run_id = probe_run_dir.name
    return {
        "summary": _artifact_entry(probe_run_id, "summary.json", probe_run_dir / "summary.json"),
        "category": _artifact_entry(
            probe_run_id,
            "category-result.jsonl",
            probe_run_dir / "category-result.jsonl",
        ),
        "channel": _artifact_entry(
            probe_run_id,
            "channel-result.jsonl",
            probe_run_dir / "channel-result.jsonl",
        ),
    }


def _artifact_failure_class(artifact_checks: Mapping[str, Mapping[str, Any]]) -> str | None:
    if not artifact_checks["summary"]["exists"]:
        return "probe_summary_missing"
    if not artifact_checks["category"]["exists"]:
        return "category_artifact_missing"
    if not artifact_checks["channel"]["exists"]:
        return "channel_artifact_missing"
    return None


def _read_probe_summary(probe_run_dir: Path) -> Mapping[str, Any] | None:
    return regular._read_probe_summary(probe_run_dir)


def _sanitize_probe_summary(probe_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if probe_summary is None:
        return {"status": "unavailable"}
    pagination = probe_summary.get("pagination")
    if not isinstance(pagination, Mapping):
        pagination = {}
    coverage = probe_summary.get("coverage")
    if not isinstance(coverage, Mapping):
        coverage = {}
    failure = probe_summary.get("failure")
    failure_kind = failure.get("kind") if isinstance(failure, Mapping) else None
    return {
        "bounded_page_cutoff": pagination.get("bounded_page_cutoff"),
        "category_result_rows": probe_summary.get("category_result_rows"),
        "channel_result_rows": probe_summary.get("channel_result_rows"),
        "coverage_status": coverage.get("status"),
        "failure_kind": failure_kind,
        "last_page_next_present": pagination.get("last_page_next_present"),
        "pages_fetched": pagination.get("pages_fetched", probe_summary.get("pages_fetched")),
        "pages_requested": pagination.get(
            "pages_requested",
            probe_summary.get("pages_requested"),
        ),
        "result_status": probe_summary.get("result_status"),
        "run_status": probe_summary.get("run_status"),
        "status": "available",
    }


def _sanitize_recurring_result(result: Mapping[str, Any] | None) -> dict[str, Any]:
    if result is None:
        return {
            "failure_class": None,
            "mode": None,
            "result_ref": None,
            "status": "not_started",
            "success": False,
        }
    category = result.get("category")
    if not isinstance(category, Mapping):
        category = {}
    channel = result.get("channel")
    if not isinstance(channel, Mapping):
        channel = {}
    api_read_smoke = result.get("api_read_smoke")
    if not isinstance(api_read_smoke, Mapping):
        api_read_smoke = regular.disabled_api_read_smoke()
    return {
        "api_read_smoke": {
            "enabled": api_read_smoke.get("enabled"),
            "failure_class": api_read_smoke.get("failure_class"),
            "http_status": api_read_smoke.get("http_status"),
            "status": api_read_smoke.get("status"),
        },
        "category": {
            "committed_row_count": category.get("committed_row_count"),
            "input_row_count": category.get("input_row_count"),
            "load_attempted": category.get("load_attempted"),
            "planned_upsert_attempt_count": category.get("planned_upsert_attempt_count"),
            "status": category.get("status"),
            "valid_row_count": category.get("valid_row_count"),
        },
        "channel": {
            "committed_row_count": channel.get("committed_row_count"),
            "input_row_count": channel.get("input_row_count"),
            "load_attempted": channel.get("load_attempted"),
            "planned_upsert_attempt_count": channel.get("planned_upsert_attempt_count"),
            "status": channel.get("status"),
            "valid_row_count": channel.get("valid_row_count"),
        },
        "failure_class": result.get("failure_class"),
        "mode": result.get("mode"),
        "partial_success": result.get("partial_success"),
        "result_ref": result.get("result_ref"),
        "status": result.get("status"),
        "success": bool(result.get("success")) and result.get("status") == "success",
    }


def _sanitization() -> dict[str, bool]:
    return {
        "absolute_local_paths_in_summary": False,
        "api_response_body_in_summary": False,
        "credential_lengths_in_summary": False,
        "credentials_in_summary": False,
        "db_env_details_in_summary": False,
        "private_host_or_path_in_summary": False,
        "provider_label_values_in_summary": False,
        "raw_jsonl_rows_in_summary": False,
        "raw_probe_summary_in_summary": False,
        "raw_provider_payload_in_summary": False,
        "scheduler_details_in_summary": False,
    }


def _action_policy(
    *,
    live_fetch_enabled: bool,
    db_write_enabled: bool,
    api_read_smoke_enabled: bool,
) -> dict[str, Any]:
    return {
        "api_read_smoke_enabled": api_read_smoke_enabled,
        "backfill_enabled": False,
        "db_write_enabled": db_write_enabled,
        "ddl_bootstrap_enabled": False,
        "live_fetch_enabled": live_fetch_enabled,
        "live_fetch_invocation_limit": 1,
        "retry_loop_enabled": False,
        "scheduler_registration_enabled": False,
        "selected_artifact_required": True,
    }


def _empty_guarded_write(status: str = "not_started") -> dict[str, Any]:
    return {
        "enabled": False,
        "failure_class": None,
        "mode": None,
        "result_ref": None,
        "status": status,
        "success": False,
    }


def _build_result(
    *,
    paths: OrchestrationPaths,
    started_at_utc: str,
    finished_at_utc: str,
    status: str,
    failure_class: str | None,
    action_policy: Mapping[str, Any],
    credential_preconditions: Mapping[str, Any],
    db_env_preconditions: Mapping[str, Any],
    relation_preconditions: Mapping[str, Any],
    prior_result_validation: Mapping[str, Any],
    live_fetch: Mapping[str, Any],
    selected_artifact_run_id: str | None,
    artifact_checks: Mapping[str, Any],
    probe_summary: Mapping[str, Any],
    recurring_no_write_dry_run: Mapping[str, Any],
    guarded_write: Mapping[str, Any],
    idempotency_rerun: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "action_policy": action_policy,
        "artifact_checks": artifact_checks,
        "credential_preconditions": credential_preconditions,
        "db_env_preconditions": db_env_preconditions,
        "duration_ms": _duration_ms(started_at_utc, finished_at_utc),
        "failure_class": failure_class,
        "finished_at_utc": finished_at_utc,
        "guarded_write": guarded_write,
        "hard_failure": status == "hard_failure",
        "idempotency_rerun": idempotency_rerun,
        "job_name": JOB_NAME,
        "live_fetch": live_fetch,
        "lock": {
            "lock_ref": paths.lock_ref,
            "status": "busy" if status == "lock_busy" else "acquired",
        },
        "lock_busy": status == "lock_busy",
        "partial_success": status == "partial_success",
        "prior_result_validation": prior_result_validation,
        "probe_summary": probe_summary,
        "provider": PROVIDER,
        "recurring_no_write_dry_run": recurring_no_write_dry_run,
        "relation_preconditions": relation_preconditions,
        "result_ref": paths.result_ref,
        "run_id": paths.run_id,
        "sanitization": _sanitization(),
        "schema_version": SCHEMA_VERSION,
        "selected_artifact_run_id": selected_artifact_run_id,
        "started_at_utc": started_at_utc,
        "status": status,
        "success": status in {"success", "partial_success"},
    }


def _finish(
    *,
    paths: OrchestrationPaths,
    started_at_utc: str,
    status: str,
    failure_class: str | None,
    action_policy: Mapping[str, Any],
    credential_preconditions: Mapping[str, Any] | None = None,
    db_env_preconditions: Mapping[str, Any] | None = None,
    relation_preconditions: Mapping[str, Any] | None = None,
    prior_result_validation: Mapping[str, Any] | None = None,
    live_fetch: Mapping[str, Any] | None = None,
    selected_artifact_run_id: str | None = None,
    artifact_checks: Mapping[str, Any] | None = None,
    probe_summary: Mapping[str, Any] | None = None,
    recurring_no_write_dry_run: Mapping[str, Any] | None = None,
    guarded_write: Mapping[str, Any] | None = None,
    idempotency_rerun: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = _build_result(
        paths=paths,
        started_at_utc=started_at_utc,
        finished_at_utc=utc_now_iso(),
        status=status,
        failure_class=failure_class,
        action_policy=action_policy,
        credential_preconditions=credential_preconditions or {"checked": False},
        db_env_preconditions=db_env_preconditions or {"checked": False},
        relation_preconditions=relation_preconditions or {},
        prior_result_validation=prior_result_validation or {"checked": False},
        live_fetch=live_fetch or {"invocation_count": 0, "status": "not_started"},
        selected_artifact_run_id=selected_artifact_run_id,
        artifact_checks=artifact_checks or {},
        probe_summary=probe_summary or {"status": "not_started"},
        recurring_no_write_dry_run=recurring_no_write_dry_run
        or _sanitize_recurring_result(None),
        guarded_write=guarded_write or _empty_guarded_write(),
        idempotency_rerun=idempotency_rerun
        or {"enabled": False, "status": "not_applicable"},
    )
    _write_json(paths.result_path, result)
    return result


def _default_fetcher(
    *,
    output_dir: Path,
    run_id: str,
    pages: int,
    size: int,
    base_url: str,
    timeout: float,
    environ: Mapping[str, str],
) -> Mapping[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        fetch_result = live_list_temporal_probe.fetch_pages(
            client=client,
            headers={
                "Client-Id": environ["CHZZK_CLIENT_ID"],
                "Client-Secret": environ["CHZZK_CLIENT_SECRET"],
            },
            base_url=base_url,
            size=size,
            pages=pages,
        )
    return live_list_temporal_probe.write_probe_run(
        output_dir=output_dir,
        pages=fetch_result["pages"],
        collected_at=live_list_temporal_probe.utc_now(),
        pages_requested=pages,
        size=size,
        run_id=run_id,
        failure=fetch_result["failure"],
    )


def _check_db_env(environ: Mapping[str, str]) -> dict[str, Any]:
    presence = _presence(REQUIRED_DB_ENV, environ)
    failure_class = _presence_failure_class("db", presence)
    return {
        "checked": True,
        "failure_class": failure_class,
        "presence": presence,
        "status": "missing" if failure_class else "present",
    }


def _check_chzzk_credentials(environ: Mapping[str, str], *, required: bool) -> dict[str, Any]:
    if not required:
        return {"checked": False, "required": False, "status": "not_required"}
    presence = _presence(REQUIRED_CHZZK_ENV, environ)
    failure_class = _presence_failure_class("chzzk", presence)
    return {
        "checked": True,
        "failure_class": failure_class,
        "presence": presence,
        "required": True,
        "status": "missing" if failure_class else "present",
    }


def _check_relations(relation_checker: RelationChecker) -> tuple[dict[str, Any], str | None]:
    relation_preconditions = dict(relation_checker())
    return relation_preconditions, regular._relation_failure_class(relation_preconditions)


def _run_recurring_dry_run(
    *,
    recurring_runner: RecurringRunner,
    paths: OrchestrationPaths,
    probe_run_dir: Path,
    api_smoke_url: str | None,
    api_client: Any | None,
) -> Mapping[str, Any]:
    return recurring_runner(
        probe_run_dir=probe_run_dir,
        base_dir=paths.run_dir / "recurring",
        run_id=f"{paths.run_id}-dry-run",
        write_enabled=False,
        api_smoke_url=api_smoke_url,
        api_client=api_client,
    )


def _run_guarded_write(
    *,
    recurring_runner: RecurringRunner,
    paths: OrchestrationPaths,
    probe_run_dir: Path,
    api_smoke_url: str | None,
    api_client: Any | None,
    suffix: str,
) -> Mapping[str, Any]:
    return recurring_runner(
        probe_run_dir=probe_run_dir,
        base_dir=paths.run_dir / "recurring",
        run_id=f"{paths.run_id}-{suffix}",
        write_enabled=True,
        api_smoke_url=api_smoke_url,
        api_client=api_client,
    )


def _load_prior_result(
    *,
    orchestration_run_id: str,
    base_dir: Path,
) -> Mapping[str, Any] | None:
    try:
        payload = json.loads((base_dir / orchestration_run_id / "result.json").read_text())
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _validate_prior_result(
    *,
    prior_result: Mapping[str, Any] | None,
    probe_output_dir: Path,
) -> tuple[dict[str, Any], str | None, str | None, Path | None]:
    if prior_result is None:
        return (
            {"checked": True, "failure_class": "prior_result_unavailable", "status": "failed"},
            "prior_result_unavailable",
            None,
            None,
        )

    selected_artifact_run_id = prior_result.get("selected_artifact_run_id")
    safe_selected = (
        _safe_run_id(str(selected_artifact_run_id)) if selected_artifact_run_id else None
    )
    if safe_selected is None:
        return (
            {
                "checked": True,
                "failure_class": "prior_selected_artifact_run_id_invalid",
                "status": "failed",
            },
            "prior_selected_artifact_run_id_invalid",
            None,
            None,
        )

    action_policy = prior_result.get("action_policy")
    if not isinstance(action_policy, Mapping):
        action_policy = {}
    recurring_dry_run = prior_result.get("recurring_no_write_dry_run")
    if not isinstance(recurring_dry_run, Mapping):
        recurring_dry_run = {}

    expected_policy = {
        "db_write_enabled": False,
        "live_fetch_enabled": True,
        "live_fetch_invocation_limit": 1,
        "scheduler_registration_enabled": False,
    }
    for key, expected in expected_policy.items():
        if action_policy.get(key) != expected:
            return (
                {
                    "checked": True,
                    "failure_class": "prior_action_policy_invalid",
                    "status": "failed",
                },
                "prior_action_policy_invalid",
                safe_selected,
                None,
            )

    if not (
        prior_result.get("status") == "success"
        and recurring_dry_run.get("status") == "success"
        and recurring_dry_run.get("success") is True
        and recurring_dry_run.get("mode") == recurring.DRY_RUN_MODE
    ):
        return (
            {
                "checked": True,
                "failure_class": "prior_no_write_dry_run_not_successful",
                "status": "failed",
            },
            "prior_no_write_dry_run_not_successful",
            safe_selected,
            None,
        )

    probe_run_dir = probe_output_dir / safe_selected
    artifact_checks = check_selected_artifact(probe_run_dir)
    artifact_failure = _artifact_failure_class(artifact_checks)
    if artifact_failure is not None:
        return (
            {
                "artifact_checks": artifact_checks,
                "checked": True,
                "failure_class": f"prior_{artifact_failure}",
                "selected_artifact_run_id": safe_selected,
                "status": "failed",
            },
            f"prior_{artifact_failure}",
            safe_selected,
            None,
        )

    return (
        {
            "artifact_checks": artifact_checks,
            "checked": True,
            "selected_artifact_run_id": safe_selected,
            "status": "passed",
        },
        None,
        safe_selected,
        probe_run_dir,
    )


def run_orchestration(
    *,
    allow_live_fetch_once: bool = False,
    from_orchestration_run_id: str | None = None,
    write_enabled: bool = False,
    idempotency_rerun_enabled: bool = False,
    base_dir: Path = DEFAULT_BASE_DIR,
    probe_output_dir: Path = DEFAULT_PROBE_OUTPUT_DIR,
    run_id: str | None = None,
    lock_wait_seconds: float = 0.0,
    api_smoke_url: str | None = None,
    api_client: Any | None = None,
    fetch_pages: int = DEFAULT_FETCH_PAGES,
    fetch_size: int = DEFAULT_FETCH_SIZE,
    fetch_base_url: str = live_list_temporal_probe.DEFAULT_LIVES_URL,
    fetch_timeout: float = 20.0,
    environ: Mapping[str, str] | None = None,
    fetcher: Fetcher = _default_fetcher,
    recurring_runner: RecurringRunner = recurring.run_recurring_with_evidence,
    relation_checker: RelationChecker = regular.check_relation_preconditions,
) -> dict[str, Any]:
    """Run the manual Chzzk fetch-load orchestration boundary."""

    started_at_utc = utc_now_iso()
    source = environ or os.environ
    paths = build_paths(base_dir=base_dir, run_id=run_id)
    live_fetch_mode = allow_live_fetch_once
    action_policy = _action_policy(
        live_fetch_enabled=live_fetch_mode,
        db_write_enabled=write_enabled,
        api_read_smoke_enabled=api_smoke_url is not None,
    )

    lock = regular.NoOverlapLock(paths.lock_path)
    if not lock.acquire(wait_seconds=lock_wait_seconds):
        return _finish(
            paths=paths,
            started_at_utc=started_at_utc,
            status="lock_busy",
            failure_class="lock_busy",
            action_policy=action_policy,
        )

    try:
        if allow_live_fetch_once == (from_orchestration_run_id is not None):
            return _finish(
                paths=paths,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class="orchestration_source_invalid",
                action_policy=action_policy,
            )

        if from_orchestration_run_id is not None:
            safe_prior_run_id = _safe_run_id(from_orchestration_run_id)
            if safe_prior_run_id is None:
                return _finish(
                    paths=paths,
                    started_at_utc=started_at_utc,
                    status="hard_failure",
                    failure_class="from_orchestration_run_id_invalid",
                    action_policy=action_policy,
                    credential_preconditions=_check_chzzk_credentials(source, required=False),
                    prior_result_validation={
                        "checked": True,
                        "failure_class": "from_orchestration_run_id_invalid",
                        "status": "failed",
                    },
                )
            prior_result = _load_prior_result(
                orchestration_run_id=safe_prior_run_id,
                base_dir=base_dir,
            )
            prior_validation, prior_failure, selected_artifact_run_id, probe_run_dir = (
                _validate_prior_result(
                    prior_result=prior_result,
                    probe_output_dir=probe_output_dir,
                )
            )
            credential_preconditions = _check_chzzk_credentials(source, required=False)
            if prior_failure is not None or probe_run_dir is None:
                return _finish(
                    paths=paths,
                    started_at_utc=started_at_utc,
                    status="hard_failure",
                    failure_class=prior_failure,
                    action_policy=action_policy,
                    credential_preconditions=credential_preconditions,
                    prior_result_validation=prior_validation,
                    selected_artifact_run_id=selected_artifact_run_id,
                )
        else:
            selected_artifact_run_id = paths.run_id
            probe_run_dir = probe_output_dir / selected_artifact_run_id
            prior_validation = {"checked": False, "status": "not_applicable"}
            credential_preconditions = _check_chzzk_credentials(source, required=True)
            credential_failure = credential_preconditions.get("failure_class")
            if credential_failure is not None:
                return _finish(
                    paths=paths,
                    started_at_utc=started_at_utc,
                    status="hard_failure",
                    failure_class=str(credential_failure),
                    action_policy=action_policy,
                    credential_preconditions=credential_preconditions,
                    prior_result_validation=prior_validation,
                    selected_artifact_run_id=selected_artifact_run_id,
                )

        db_env_preconditions = _check_db_env(source)
        db_env_failure = db_env_preconditions.get("failure_class")
        if db_env_failure is not None:
            return _finish(
                paths=paths,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class=str(db_env_failure),
                action_policy=action_policy,
                credential_preconditions=credential_preconditions,
                db_env_preconditions=db_env_preconditions,
                prior_result_validation=prior_validation,
                selected_artifact_run_id=selected_artifact_run_id,
            )

        relation_preconditions, relation_failure = _check_relations(relation_checker)
        if relation_failure is not None:
            return _finish(
                paths=paths,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class=relation_failure,
                action_policy=action_policy,
                credential_preconditions=credential_preconditions,
                db_env_preconditions=db_env_preconditions,
                relation_preconditions=relation_preconditions,
                prior_result_validation=prior_validation,
                selected_artifact_run_id=selected_artifact_run_id,
            )

        live_fetch = {"invocation_count": 0, "status": "not_started"}
        if live_fetch_mode:
            try:
                fetcher(
                    output_dir=probe_output_dir,
                    run_id=selected_artifact_run_id,
                    pages=fetch_pages,
                    size=fetch_size,
                    base_url=fetch_base_url,
                    timeout=fetch_timeout,
                    environ=source,
                )
            except Exception:
                return _finish(
                    paths=paths,
                    started_at_utc=started_at_utc,
                    status="hard_failure",
                    failure_class="live_fetch_failed",
                    action_policy=action_policy,
                    credential_preconditions=credential_preconditions,
                    db_env_preconditions=db_env_preconditions,
                    relation_preconditions=relation_preconditions,
                    prior_result_validation=prior_validation,
                    live_fetch={"invocation_count": 1, "status": "failed"},
                    selected_artifact_run_id=selected_artifact_run_id,
                )
            live_fetch = {
                "invocation_count": 1,
                "pages_requested": fetch_pages,
                "retry_loop_enabled": False,
                "size": fetch_size,
                "status": "completed",
            }

        artifact_checks = check_selected_artifact(probe_run_dir)
        probe_summary = _sanitize_probe_summary(_read_probe_summary(probe_run_dir))
        artifact_failure = _artifact_failure_class(artifact_checks)
        if artifact_failure is not None:
            return _finish(
                paths=paths,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class=artifact_failure,
                action_policy=action_policy,
                credential_preconditions=credential_preconditions,
                db_env_preconditions=db_env_preconditions,
                relation_preconditions=relation_preconditions,
                prior_result_validation=prior_validation,
                live_fetch=live_fetch,
                selected_artifact_run_id=selected_artifact_run_id,
                artifact_checks=artifact_checks,
                probe_summary=probe_summary,
            )

        dry_run_result = _run_recurring_dry_run(
            recurring_runner=recurring_runner,
            paths=paths,
            probe_run_dir=probe_run_dir,
            api_smoke_url=api_smoke_url,
            api_client=api_client,
        )
        recurring_no_write_dry_run = _sanitize_recurring_result(dry_run_result)
        if recurring_no_write_dry_run["success"] is not True:
            return _finish(
                paths=paths,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class="recurring_no_write_dry_run_failed",
                action_policy=action_policy,
                credential_preconditions=credential_preconditions,
                db_env_preconditions=db_env_preconditions,
                relation_preconditions=relation_preconditions,
                prior_result_validation=prior_validation,
                live_fetch=live_fetch,
                selected_artifact_run_id=selected_artifact_run_id,
                artifact_checks=artifact_checks,
                probe_summary=probe_summary,
                recurring_no_write_dry_run=recurring_no_write_dry_run,
            )

        guarded_write = _empty_guarded_write("not_requested")
        idempotency_rerun = {"enabled": False, "status": "not_requested"}
        status = "success"
        failure_class: str | None = None
        if write_enabled:
            write_result = _run_guarded_write(
                recurring_runner=recurring_runner,
                paths=paths,
                probe_run_dir=probe_run_dir,
                api_smoke_url=api_smoke_url,
                api_client=api_client,
                suffix="guarded-write",
            )
            guarded_write = {
                "enabled": True,
                **_sanitize_recurring_result(write_result),
            }
            write_status = str(guarded_write["status"])
            if write_status == "hard_failure":
                status = "hard_failure"
                failure_class = str(guarded_write.get("failure_class"))
            elif write_status == "partial_success":
                status = "partial_success"
                failure_class = str(guarded_write.get("failure_class"))
            elif write_status != "success":
                status = "hard_failure"
                failure_class = "guarded_write_failed"
            elif idempotency_rerun_enabled:
                rerun_result = _run_guarded_write(
                    recurring_runner=recurring_runner,
                    paths=paths,
                    probe_run_dir=probe_run_dir,
                    api_smoke_url=api_smoke_url,
                    api_client=api_client,
                    suffix="guarded-write-idempotency",
                )
                idempotency_rerun = {
                    "enabled": True,
                    **_sanitize_recurring_result(rerun_result),
                }
                if idempotency_rerun["status"] != "success":
                    status = "hard_failure"
                    failure_class = "idempotency_rerun_failed"
            elif idempotency_rerun_enabled:
                idempotency_rerun = {
                    "enabled": True,
                    "status": "skipped_after_guarded_write_failure",
                }

        return _finish(
            paths=paths,
            started_at_utc=started_at_utc,
            status=status,
            failure_class=failure_class,
            action_policy=action_policy,
            credential_preconditions=credential_preconditions,
            db_env_preconditions=db_env_preconditions,
            relation_preconditions=relation_preconditions,
            prior_result_validation=prior_validation,
            live_fetch=live_fetch,
            selected_artifact_run_id=selected_artifact_run_id,
            artifact_checks=artifact_checks,
            probe_summary=probe_summary,
            recurring_no_write_dry_run=recurring_no_write_dry_run,
            guarded_write=guarded_write,
            idempotency_rerun=idempotency_rerun,
        )
    finally:
        lock.release()


def exit_code_for_status(status: str) -> int:
    """Return scheduler-friendly process exit code for orchestration status."""

    if status in {"success", "partial_success"}:
        return 0
    if status == "lock_busy":
        return LOCK_BUSY_EXIT_CODE
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the manual Chzzk fetch-load orchestration."""

    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--allow-live-fetch-once", action="store_true")
    source.add_argument("--from-orchestration-run-id")
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--probe-output-dir", type=Path, default=DEFAULT_PROBE_OUTPUT_DIR)
    parser.add_argument("--run-id")
    parser.add_argument("--lock-wait-sec", type=float, default=0.0)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--idempotency-rerun", action="store_true")
    parser.add_argument("--api-smoke-url")
    parser.add_argument("--fetch-pages", type=int, default=DEFAULT_FETCH_PAGES)
    parser.add_argument("--fetch-size", type=int, default=DEFAULT_FETCH_SIZE)
    parser.add_argument("--fetch-base-url", default=live_list_temporal_probe.DEFAULT_LIVES_URL)
    parser.add_argument("--fetch-timeout", type=float, default=20.0)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for the manual Chzzk fetch-load orchestration."""

    args = build_parser().parse_args(argv)
    result = run_orchestration(
        allow_live_fetch_once=args.allow_live_fetch_once,
        from_orchestration_run_id=args.from_orchestration_run_id,
        write_enabled=args.write,
        idempotency_rerun_enabled=args.idempotency_rerun,
        base_dir=args.base_dir,
        probe_output_dir=args.probe_output_dir,
        run_id=args.run_id,
        lock_wait_seconds=args.lock_wait_sec,
        api_smoke_url=args.api_smoke_url,
        fetch_pages=args.fetch_pages,
        fetch_size=args.fetch_size,
        fetch_base_url=args.fetch_base_url,
        fetch_timeout=args.fetch_timeout,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    raise SystemExit(exit_code_for_status(str(result["status"])))


if __name__ == "__main__":
    main()
