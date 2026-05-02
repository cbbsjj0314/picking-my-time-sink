"""Guarded recurring Chzzk write-path command for selected artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chzzk.ingest import run_chzzk_regular_write_path as dry_run
from chzzk.normalize import category_result_to_gold, channel_result_to_gold
from steam.common.execution_meta import utc_now_iso

PROVIDER = "chzzk"
JOB_NAME = "chzzk_recurring_write_path"
DRY_RUN_MODE = "dry-run"
GUARDED_WRITE_MODE = "guarded-write"
SCHEMA_VERSION = "1"
DEFAULT_BASE_DIR = Path("tmp/chzzk/recurring-write-path")
LOCK_BASENAME = "chzzk-recurring-write-path.lock"
LOCK_BUSY_EXIT_CODE = dry_run.LOCK_BUSY_EXIT_CODE
RETENTION_CAVEAT = dry_run.RETENTION_CAVEAT
SEPARATE_TRANSACTION_CAVEAT = (
    "Category and channel loaders own separate DB transactions in this slice; "
    "a category commit is not rolled back by a later channel validation/load failure."
)
LOADER_SUMMARY_ALLOWED_FIELDS = {
    "bucket_max",
    "bucket_min",
    "committed_row_count",
    "failed_row_count",
    "input_row_count",
    "skip_reasons",
    "skipped_row_count",
    "status",
    "unique_category_count",
    "unique_channel_count",
    "upsert_attempt_count",
    "valid_row_count",
}

Loader = Callable[..., Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class RecurringPaths:
    """Resolved local/private paths for one recurring command run."""

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
) -> RecurringPaths:
    """Resolve recurring-run paths without exposing absolute refs in summaries."""

    resolved_run_id = run_id or _utc_run_id()
    run_dir = base_dir / resolved_run_id
    return RecurringPaths(
        run_id=resolved_run_id,
        run_dir=run_dir,
        result_path=run_dir / "result.json",
        lock_path=base_dir / "locks" / LOCK_BASENAME,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _action_policy(*, db_write_enabled: bool, api_read_smoke_enabled: bool) -> dict[str, Any]:
    return {
        "api_read_smoke_enabled": api_read_smoke_enabled,
        "db_write_enabled": db_write_enabled,
        "live_fetch_enabled": False,
        "scheduler_registration_enabled": False,
        "selected_artifact_required": True,
    }


def _sanitization() -> dict[str, bool]:
    return {
        "absolute_local_paths_in_summary": False,
        "api_response_body_in_summary": False,
        "credentials_in_summary": False,
        "db_env_details_in_summary": False,
        "loader_raw_summary_in_summary": False,
        "provider_label_values_in_summary": False,
        "raw_jsonl_rows_in_summary": False,
        "raw_provider_payload_in_summary": False,
        "scheduler_details_in_summary": False,
    }


def _duration_ms(started_at_utc: str, finished_at_utc: str) -> int:
    return dry_run._duration_ms(started_at_utc, finished_at_utc)


def _empty_step(status: str) -> dict[str, Any]:
    return dry_run._empty_plan(status)


def _selected_artifact_ref(probe_run_dir: Path) -> dict[str, str]:
    return {
        "run_relative_ref": probe_run_dir.name,
        "selected_artifact_run_id": probe_run_dir.name,
    }


def _sanitize_loader_summary(summary: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for field in sorted(LOADER_SUMMARY_ALLOWED_FIELDS):
        if field in summary:
            sanitized[field] = summary[field]

    upsert_attempt_count = sanitized.pop("upsert_attempt_count", None)
    if upsert_attempt_count is not None:
        sanitized["planned_upsert_attempt_count"] = upsert_attempt_count
    else:
        sanitized.setdefault("planned_upsert_attempt_count", 0)

    loader_status = str(sanitized.get("status", "unknown"))
    sanitized["status"] = "loaded" if loader_status == "success" else "load_failed"
    sanitized["load_attempted"] = True
    sanitized.setdefault("committed_row_count", 0)
    sanitized.setdefault("failed_row_count", 0)
    sanitized.setdefault("input_row_count", 0)
    sanitized.setdefault("skip_reasons", {})
    sanitized.setdefault("skipped_row_count", 0)
    sanitized.setdefault("valid_row_count", 0)
    if sanitized["status"] != "loaded":
        sanitized["failure_class"] = f"{role}_load_failed"
    return sanitized


def _load_failed_step(role: str) -> dict[str, Any]:
    return {
        **_empty_step("load_failed"),
        "failure_class": f"{role}_load_failed",
        "load_attempted": True,
    }


def _build_post_write_dry_run(
    *,
    enabled: bool,
    probe_run_dir: Path,
    category_enabled: bool,
    channel_enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "lock_reacquired": False,
            "status": "not_applicable",
        }

    category = (
        dry_run.plan_category_dry_run(probe_run_dir / "category-result.jsonl")
        if category_enabled
        else _empty_step("not_started")
    )
    channel = (
        dry_run.plan_channel_dry_run(probe_run_dir / "channel-result.jsonl")
        if channel_enabled
        else _empty_step("not_started")
    )
    return {
        "category": category,
        "channel": channel,
        "enabled": True,
        "lock_reacquired": False,
        "status": "completed",
    }


def _build_result(
    *,
    paths: RecurringPaths,
    mode: str,
    started_at_utc: str,
    finished_at_utc: str,
    status: str,
    failure_class: str | None,
    action_policy: Mapping[str, Any],
    relation_preconditions: Mapping[str, Any],
    artifact_checks: Mapping[str, Any],
    selected_artifact: Mapping[str, Any],
    category: Mapping[str, Any],
    channel: Mapping[str, Any],
    bounded_sample_caveat: Mapping[str, Any],
    api_read_smoke: Mapping[str, Any],
    post_write_dry_run: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "action_policy": action_policy,
        "api_read_smoke": api_read_smoke,
        "artifact_checks": artifact_checks,
        "bounded_sample_caveat": bounded_sample_caveat,
        "category": category,
        "channel": channel,
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
        "mode": mode,
        "partial_success": status == "partial_success",
        "post_write_dry_run": post_write_dry_run,
        "provider": PROVIDER,
        "relation_preconditions": relation_preconditions,
        "result_ref": paths.result_ref,
        "retention_caveat": RETENTION_CAVEAT,
        "run_id": paths.run_id,
        "sanitization": _sanitization(),
        "schema_version": SCHEMA_VERSION,
        "selected_artifact": selected_artifact,
        "started_at_utc": started_at_utc,
        "status": status,
        "success": status in {"success", "partial_success"},
        "transaction_caveat": {
            "category_commit_not_rolled_back_by_channel_failure": mode
            == GUARDED_WRITE_MODE,
            "separate_loader_transactions": mode == GUARDED_WRITE_MODE,
            "summary": SEPARATE_TRANSACTION_CAVEAT
            if mode == GUARDED_WRITE_MODE
            else "not_applicable",
        },
    }


def _finish(
    *,
    paths: RecurringPaths,
    mode: str,
    started_at_utc: str,
    status: str,
    failure_class: str | None,
    action_policy: Mapping[str, Any],
    relation_preconditions: Mapping[str, Any],
    artifact_checks: Mapping[str, Any],
    selected_artifact: Mapping[str, Any],
    category: Mapping[str, Any],
    channel: Mapping[str, Any],
    bounded_sample_caveat: Mapping[str, Any],
    api_read_smoke: Mapping[str, Any],
    post_write_dry_run: Mapping[str, Any],
) -> dict[str, Any]:
    result = _build_result(
        paths=paths,
        mode=mode,
        started_at_utc=started_at_utc,
        finished_at_utc=utc_now_iso(),
        status=status,
        failure_class=failure_class,
        action_policy=action_policy,
        relation_preconditions=relation_preconditions,
        artifact_checks=artifact_checks,
        selected_artifact=selected_artifact,
        category=category,
        channel=channel,
        bounded_sample_caveat=bounded_sample_caveat,
        api_read_smoke=api_read_smoke,
        post_write_dry_run=post_write_dry_run,
    )
    _write_json(paths.result_path, result)
    return result


def _validate_selected_artifact_prefix(
    probe_run_dir: Path,
) -> tuple[dict[str, Any], Mapping[str, Any] | None, dict[str, Any] | None, str | None]:
    artifact_checks = dry_run.check_probe_artifacts(probe_run_dir)
    probe_summary = dry_run._read_probe_summary(probe_run_dir)
    if not artifact_checks["summary"]["exists"]:
        return (
            artifact_checks,
            probe_summary,
            _empty_step("skipped_due_to_probe_summary_missing"),
            "probe_summary_missing",
        )
    if probe_summary is None:
        return (
            artifact_checks,
            probe_summary,
            _empty_step("skipped_due_to_probe_summary_read_failed"),
            "probe_summary_read_failed",
        )
    if not artifact_checks["category"]["exists"]:
        return artifact_checks, probe_summary, _empty_step("missing"), "category_artifact_missing"
    category = dry_run.plan_category_dry_run(probe_run_dir / "category-result.jsonl")
    failure_class = category.get("failure_class")
    return (
        artifact_checks,
        probe_summary,
        category,
        str(failure_class) if failure_class is not None else None,
    )


def _run_loader(
    loader: Loader,
    *,
    input_path: Path,
    result_path: Path,
    meta_path: Path,
    role: str,
) -> dict[str, Any]:
    try:
        loader(input_path=input_path, result_path=result_path, meta_path=meta_path)
    except Exception:
        return _load_failed_step(role)
    try:
        summary = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _load_failed_step(role)
    if not isinstance(summary, Mapping):
        return _load_failed_step(role)
    return _sanitize_loader_summary(summary, role=role)


def run_recurring_with_evidence(
    *,
    probe_run_dir: Path,
    base_dir: Path = DEFAULT_BASE_DIR,
    run_id: str | None = None,
    lock_wait_seconds: float = 0.0,
    write_enabled: bool = False,
    api_smoke_url: str | None = None,
    api_client: Any | None = None,
    category_loader: Loader = category_result_to_gold.run,
    channel_loader: Loader = channel_result_to_gold.run,
) -> dict[str, Any]:
    """Run the guarded recurring boundary and persist a sanitized result."""

    started_at_utc = utc_now_iso()
    mode = GUARDED_WRITE_MODE if write_enabled else DRY_RUN_MODE
    action_policy = _action_policy(
        db_write_enabled=write_enabled,
        api_read_smoke_enabled=api_smoke_url is not None,
    )
    selected_artifact = _selected_artifact_ref(probe_run_dir)
    paths = build_paths(base_dir=base_dir, run_id=run_id)
    lock = dry_run.NoOverlapLock(paths.lock_path)
    if not lock.acquire(wait_seconds=lock_wait_seconds):
        return _finish(
            paths=paths,
            mode=mode,
            started_at_utc=started_at_utc,
            status="lock_busy",
            failure_class="lock_busy",
            action_policy=action_policy,
            relation_preconditions={},
            artifact_checks={},
            selected_artifact=selected_artifact,
            category=_empty_step("not_started"),
            channel=_empty_step("not_started"),
            bounded_sample_caveat=dry_run._bounded_sample_caveat(None),
            api_read_smoke=dry_run.disabled_api_read_smoke(),
            post_write_dry_run=_build_post_write_dry_run(
                enabled=False,
                probe_run_dir=probe_run_dir,
                category_enabled=False,
                channel_enabled=False,
            ),
        )

    try:
        relation_preconditions = dry_run.check_relation_preconditions()
        relation_failure_class = dry_run._relation_failure_class(relation_preconditions)
        if relation_failure_class is not None:
            return _finish(
                paths=paths,
                mode=mode,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class=relation_failure_class,
                action_policy=action_policy,
                relation_preconditions=relation_preconditions,
                artifact_checks={},
                selected_artifact=selected_artifact,
                category=_empty_step("skipped_due_to_relation_precondition_failure"),
                channel=_empty_step("skipped_due_to_relation_precondition_failure"),
                bounded_sample_caveat=dry_run._bounded_sample_caveat(None),
                api_read_smoke=dry_run.disabled_api_read_smoke(),
                post_write_dry_run=_build_post_write_dry_run(
                    enabled=False,
                    probe_run_dir=probe_run_dir,
                    category_enabled=False,
                    channel_enabled=False,
                ),
            )

        artifact_checks, probe_summary, category, category_failure = (
            _validate_selected_artifact_prefix(probe_run_dir)
        )
        if category_failure is not None:
            return _finish(
                paths=paths,
                mode=mode,
                started_at_utc=started_at_utc,
                status="hard_failure",
                failure_class=category_failure,
                action_policy=action_policy,
                relation_preconditions=relation_preconditions,
                artifact_checks=artifact_checks,
                selected_artifact=selected_artifact,
                category=category or _empty_step("not_started"),
                channel=_empty_step("skipped_after_category_unusable"),
                bounded_sample_caveat=dry_run._bounded_sample_caveat(probe_summary),
                api_read_smoke=dry_run.disabled_api_read_smoke(),
                post_write_dry_run=_build_post_write_dry_run(
                    enabled=False,
                    probe_run_dir=probe_run_dir,
                    category_enabled=False,
                    channel_enabled=False,
                ),
            )

        if write_enabled:
            category = _run_loader(
                category_loader,
                input_path=probe_run_dir / "category-result.jsonl",
                result_path=paths.run_dir / "category-loader-summary.json",
                meta_path=paths.run_dir / "category-loader-meta.json",
                role="category",
            )
            if category.get("failure_class") is not None:
                return _finish(
                    paths=paths,
                    mode=mode,
                    started_at_utc=started_at_utc,
                    status="hard_failure",
                    failure_class=str(category["failure_class"]),
                    action_policy=action_policy,
                    relation_preconditions=relation_preconditions,
                    artifact_checks=artifact_checks,
                    selected_artifact=selected_artifact,
                    category=category,
                    channel=_empty_step("skipped_after_category_unusable"),
                    bounded_sample_caveat=dry_run._bounded_sample_caveat(probe_summary),
                    api_read_smoke=dry_run.disabled_api_read_smoke(),
                    post_write_dry_run=_build_post_write_dry_run(
                        enabled=True,
                        probe_run_dir=probe_run_dir,
                        category_enabled=True,
                        channel_enabled=False,
                    ),
                )

        status = "success"
        failure_class: str | None = None
        if not artifact_checks["channel"]["exists"]:
            status = "partial_success"
            failure_class = "channel_artifact_missing"
            channel = {**_empty_step("missing"), "failure_class": failure_class}
        else:
            channel = dry_run.plan_channel_dry_run(probe_run_dir / "channel-result.jsonl")
            channel_failure = channel.get("failure_class")
            if channel_failure is not None:
                status = "partial_success"
                failure_class = str(channel_failure)
            elif write_enabled:
                channel = _run_loader(
                    channel_loader,
                    input_path=probe_run_dir / "channel-result.jsonl",
                    result_path=paths.run_dir / "channel-loader-summary.json",
                    meta_path=paths.run_dir / "channel-loader-meta.json",
                    role="channel",
                )
                if channel.get("failure_class") is not None:
                    status = "partial_success"
                    failure_class = str(channel["failure_class"])

        post_write_dry_run = _build_post_write_dry_run(
            enabled=write_enabled,
            probe_run_dir=probe_run_dir,
            category_enabled=write_enabled,
            channel_enabled=write_enabled and artifact_checks["channel"]["exists"],
        )
        api_read_smoke = (
            dry_run.run_api_read_smoke(api_smoke_url, client=api_client)
            if api_smoke_url is not None
            else dry_run.disabled_api_read_smoke()
        )
        return _finish(
            paths=paths,
            mode=mode,
            started_at_utc=started_at_utc,
            status=status,
            failure_class=failure_class,
            action_policy=action_policy,
            relation_preconditions=relation_preconditions,
            artifact_checks=artifact_checks,
            selected_artifact=selected_artifact,
            category=category,
            channel=channel,
            bounded_sample_caveat=dry_run._bounded_sample_caveat(probe_summary),
            api_read_smoke=api_read_smoke,
            post_write_dry_run=post_write_dry_run,
        )
    finally:
        lock.release()


def exit_code_for_status(status: str) -> int:
    """Return scheduler-friendly process exit code for a recurring status."""

    return dry_run.exit_code_for_status(status)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the guarded Chzzk recurring write-path command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-run-dir", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--lock-wait-sec", type=float, default=0.0)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Enable guarded DB writes; default is dry-run/no-write.",
    )
    parser.add_argument(
        "--api-smoke-url",
        default=None,
        help="Optional GET-only route reachability smoke against an already-running API",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for the guarded Chzzk recurring write-path command."""

    args = build_parser().parse_args(argv)
    result = run_recurring_with_evidence(
        probe_run_dir=args.probe_run_dir,
        base_dir=args.base_dir,
        run_id=args.run_id,
        lock_wait_seconds=args.lock_wait_sec,
        write_enabled=args.write,
        api_smoke_url=args.api_smoke_url,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    raise SystemExit(exit_code_for_status(str(result["status"])))


if __name__ == "__main__":
    main()
