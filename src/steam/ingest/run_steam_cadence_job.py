"""Run one cadence-scoped Steam job for external schedulers."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steam.common.execution_meta import build_execution_meta, utc_now_iso
from steam.ingest import (
    fetch_app_catalog_weekly,
    fetch_ccu_30m,
    fetch_price_1h,
    fetch_reviews_daily,
    run_tracked_universe_scheduled,
)
from steam.normalize import (
    bronze_to_silver_ccu,
    bronze_to_silver_price,
    bronze_to_silver_reviews,
    gold_to_agg_ccu_daily,
    payload_to_gold_rankings,
    silver_to_gold_ccu,
    silver_to_gold_price,
    silver_to_gold_reviews,
)

LOGGER = logging.getLogger(__name__)

JOB_CCU_30M = "ccu-30m"
JOB_PRICE_1H = "price-1h"
JOB_DAILY = "daily"
JOB_APP_CATALOG_WEEKLY = "app-catalog-weekly"
JOB_CHOICES = (JOB_CCU_30M, JOB_PRICE_1H, JOB_DAILY, JOB_APP_CATALOG_WEEKLY)
DEFAULT_JOBS_BASE_DIR = Path("tmp/steam/jobs")
LOCK_BUSY_EXIT_CODE = 75


@dataclass(frozen=True, slots=True)
class JobPaths:
    """Resolved local/private artifact paths for one scheduler job run."""

    job_name: str
    run_id: str
    run_dir: Path
    lock_path: Path
    log_path: Path
    result_path: Path
    job_meta_path: Path
    step_meta_dir: Path

    def artifact(self, name: str) -> Path:
        return self.run_dir / name

    def step_meta(self, step_name: str) -> Path:
        return self.step_meta_dir / f"{step_name}.meta.json"


class NoOverlapLock:
    """Small fcntl-based lock for single-host cron/systemd scheduler calls."""

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
        owner = {
            "locked_at_utc": utc_now_iso(),
            "pid": os.getpid(),
        }
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(json.dumps(owner, ensure_ascii=False, sort_keys=True))
        self._handle.write("\n")
        self._handle.flush()


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


def _run_id_from_clock() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def build_job_paths(
    *,
    job_name: str,
    base_dir: Path = DEFAULT_JOBS_BASE_DIR,
    run_id: str | None = None,
    lock_dir: Path | None = None,
) -> JobPaths:
    """Resolve all job-scoped local artifact paths for one scheduler run."""

    resolved_run_id = run_id or _run_id_from_clock()
    run_dir = base_dir / job_name / resolved_run_id
    resolved_lock_dir = lock_dir or base_dir / "locks"
    return JobPaths(
        job_name=job_name,
        run_id=resolved_run_id,
        run_dir=run_dir,
        lock_path=resolved_lock_dir / f"{job_name}.lock",
        log_path=run_dir / f"{job_name}.log",
        result_path=run_dir / "result.json",
        job_meta_path=run_dir / "meta" / "job.meta.json",
        step_meta_dir=run_dir / "meta" / "steps",
    )


def configure_job_logging(log_path: Path) -> logging.Handler:
    """Attach a per-run log file handler while preserving existing console behavior."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger.addHandler(handler)
    return handler


def _detach_logging_handler(handler: logging.Handler) -> None:
    root_logger = logging.getLogger()
    root_logger.removeHandler(handler)
    handler.close()


def _fetch_run_kwargs(module: Any, *, output_path: Path, meta_path: Path) -> dict[str, Any]:
    args = module.build_parser().parse_args(
        ["--output-path", str(output_path), "--meta-path", str(meta_path)]
    )
    return {
        "output_path": args.output_path,
        "timeout_seconds": args.timeout_sec,
        "max_attempts": args.max_attempts,
        "backoff_base_seconds": args.backoff_base_sec,
        "jitter_max_seconds": args.jitter_max_sec,
        "max_backoff_seconds": args.max_backoff_sec,
        "meta_path": args.meta_path,
    }


def _step_result(
    *,
    name: str,
    rows: list[dict[str, Any]],
    paths: dict[str, Path],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "paths": {key: str(value) for key, value in sorted(paths.items())},
        "records_out": len(rows),
    }
    if extra:
        result.update(extra)
    return result


def run_price_job(paths: JobPaths) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the hourly Steam price boundary."""

    bronze_path = paths.artifact("price.bronze.jsonl")
    silver_path = paths.artifact("price.silver.jsonl")
    gold_result_path = paths.artifact("price.gold-result.jsonl")
    fetch_meta_path = paths.step_meta("fetch_price_1h")
    gold_meta_path = paths.step_meta("silver_to_gold_price")

    bronze_rows = fetch_price_1h.run(
        **_fetch_run_kwargs(
            fetch_price_1h,
            output_path=bronze_path,
            meta_path=fetch_meta_path,
        )
    )
    silver_rows = bronze_to_silver_price.run(
        input_path=bronze_path,
        output_path=silver_path,
    )
    gold_rows = silver_to_gold_price.run(
        input_path=silver_path,
        result_path=gold_result_path,
        meta_path=gold_meta_path,
    )

    steps = [
        _step_result(
            name="fetch_price_1h",
            rows=bronze_rows,
            paths={"output": bronze_path, "meta": fetch_meta_path},
        ),
        _step_result(
            name="bronze_to_silver_price",
            rows=silver_rows,
            paths={"input": bronze_path, "output": silver_path},
        ),
        _step_result(
            name="silver_to_gold_price",
            rows=gold_rows,
            paths={"input": silver_path, "result": gold_result_path, "meta": gold_meta_path},
        ),
    ]
    triage = {
        "bronze_records": len(bronze_rows),
        "gold_records": len(gold_rows),
        "silver_records": len(silver_rows),
    }
    return steps, triage


def run_ccu_job(paths: JobPaths) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the 30m Steam CCU boundary, including daily rollup maintenance."""

    bronze_path = paths.artifact("ccu.bronze.jsonl")
    silver_path = paths.artifact("ccu.silver.jsonl")
    gold_result_path = paths.artifact("ccu.gold-result.jsonl")
    rollup_result_path = paths.artifact("ccu.daily-rollup-result.jsonl")
    fetch_meta_path = paths.step_meta("fetch_ccu_30m")
    gold_meta_path = paths.step_meta("silver_to_gold_ccu")
    rollup_meta_path = paths.step_meta("gold_to_agg_ccu_daily")

    bronze_rows = fetch_ccu_30m.run(
        **_fetch_run_kwargs(
            fetch_ccu_30m,
            output_path=bronze_path,
            meta_path=fetch_meta_path,
        )
    )
    silver_rows = bronze_to_silver_ccu.run(
        input_path=bronze_path,
        output_path=silver_path,
    )
    gold_rows = silver_to_gold_ccu.run(
        input_path=silver_path,
        result_path=gold_result_path,
        meta_path=gold_meta_path,
    )
    rollup_rows = gold_to_agg_ccu_daily.run(
        result_path=rollup_result_path,
        meta_path=rollup_meta_path,
    )

    missing_evidence_count = sum(
        1 for row in silver_rows if row.get("missing_reason") is not None
    )
    skipped_gold_count = sum(1 for row in gold_rows if row.get("skipped") is True)
    loaded_gold_count = sum(1 for row in gold_rows if row.get("skipped") is not True)
    steps = [
        _step_result(
            name="fetch_ccu_30m",
            rows=bronze_rows,
            paths={"output": bronze_path, "meta": fetch_meta_path},
            extra={
                "missing_evidence_records": sum(
                    1 for row in bronze_rows if row.get("missing_reason") is not None
                ),
            },
        ),
        _step_result(
            name="bronze_to_silver_ccu",
            rows=silver_rows,
            paths={"input": bronze_path, "output": silver_path},
            extra={"missing_evidence_records": missing_evidence_count},
        ),
        _step_result(
            name="silver_to_gold_ccu",
            rows=gold_rows,
            paths={"input": silver_path, "result": gold_result_path, "meta": gold_meta_path},
            extra={
                "loaded_records": loaded_gold_count,
                "skipped_records": skipped_gold_count,
            },
        ),
        _step_result(
            name="gold_to_agg_ccu_daily",
            rows=rollup_rows,
            paths={"result": rollup_result_path, "meta": rollup_meta_path},
        ),
    ]
    triage = {
        "gold_loaded_records": loaded_gold_count,
        "gold_skipped_records": skipped_gold_count,
        "missing_evidence_records": missing_evidence_count,
        "partial_reason": (
            "per_app_missing_evidence" if missing_evidence_count > 0 else None
        ),
        "rollup_records": len(rollup_rows),
    }
    return steps, triage


def run_daily_job(
    paths: JobPaths,
    *,
    app_catalog_path: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the daily tracked universe, ranking gold, and reviews boundary."""

    rankings_dir = paths.run_dir / "rankings"
    topsellers_global_path = rankings_dir / "topsellers_global.payload.json"
    topsellers_kr_path = rankings_dir / "topsellers_kr.payload.json"
    mostplayed_global_path = rankings_dir / "mostplayed_global.payload.json"
    mostplayed_kr_path = rankings_dir / "mostplayed_kr.payload.json"
    tracked_result_path = paths.artifact("tracked_universe.update-result.jsonl")
    rankings_result_path = paths.artifact("rankings.payload-to-gold-result.jsonl")
    rankings_meta_path = paths.step_meta("payload_to_gold_rankings")
    reviews_bronze_path = paths.artifact("reviews.bronze.jsonl")
    reviews_silver_path = paths.artifact("reviews.silver.jsonl")
    reviews_gold_result_path = paths.artifact("reviews.gold-result.jsonl")
    reviews_fetch_meta_path = paths.step_meta("fetch_reviews_daily")
    reviews_gold_meta_path = paths.step_meta("silver_to_gold_reviews")

    tracked_rows = run_tracked_universe_scheduled.run(
        topsellers_global_path=topsellers_global_path,
        topsellers_kr_path=topsellers_kr_path,
        mostplayed_global_path=mostplayed_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
        app_catalog_path=app_catalog_path,
        result_path=tracked_result_path,
    )
    ranking_rows = payload_to_gold_rankings.run(
        topsellers_kr_path=topsellers_kr_path,
        topsellers_global_path=topsellers_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
        mostplayed_global_path=mostplayed_global_path,
        result_path=rankings_result_path,
        meta_path=rankings_meta_path,
    )
    reviews_bronze_rows = fetch_reviews_daily.run(
        **_fetch_run_kwargs(
            fetch_reviews_daily,
            output_path=reviews_bronze_path,
            meta_path=reviews_fetch_meta_path,
        )
    )
    reviews_silver_rows = bronze_to_silver_reviews.run(
        input_path=reviews_bronze_path,
        output_path=reviews_silver_path,
    )
    reviews_gold_rows = silver_to_gold_reviews.run(
        input_path=reviews_silver_path,
        result_path=reviews_gold_result_path,
        meta_path=reviews_gold_meta_path,
    )

    reviews_skipped_count = sum(
        1 for row in reviews_gold_rows if row.get("skipped") is True
    )
    steps = [
        _step_result(
            name="run_tracked_universe_scheduled",
            rows=tracked_rows,
            paths={
                "app_catalog": app_catalog_path
                or run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_APP_CATALOG_PATH,
                "mostplayed_global": mostplayed_global_path,
                "mostplayed_kr": mostplayed_kr_path,
                "result": tracked_result_path,
                "topsellers_global": topsellers_global_path,
                "topsellers_kr": topsellers_kr_path,
            },
        ),
        _step_result(
            name="payload_to_gold_rankings",
            rows=ranking_rows,
            paths={"result": rankings_result_path, "meta": rankings_meta_path},
        ),
        _step_result(
            name="fetch_reviews_daily",
            rows=reviews_bronze_rows,
            paths={"output": reviews_bronze_path, "meta": reviews_fetch_meta_path},
        ),
        _step_result(
            name="bronze_to_silver_reviews",
            rows=reviews_silver_rows,
            paths={"input": reviews_bronze_path, "output": reviews_silver_path},
        ),
        _step_result(
            name="silver_to_gold_reviews",
            rows=reviews_gold_rows,
            paths={
                "input": reviews_silver_path,
                "result": reviews_gold_result_path,
                "meta": reviews_gold_meta_path,
            },
            extra={"skipped_records": reviews_skipped_count},
        ),
    ]
    triage = {
        "ranking_gold_records": len(ranking_rows),
        "reviews_gold_records": len(reviews_gold_rows),
        "reviews_skipped_records": reviews_skipped_count,
        "tracked_universe_records": len(tracked_rows),
    }
    if reviews_skipped_count > 0:
        triage["partial_reason"] = "reviews_skipped_evidence"
    return steps, triage


def run_app_catalog_job(
    paths: JobPaths,
    *,
    max_results: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the optional weekly/ad hoc App Catalog boundary."""

    snapshot_path = paths.artifact("app_catalog.snapshot.jsonl")
    checkpoint_path = paths.artifact("app_catalog.checkpoint.json")
    latest_summary_path = fetch_app_catalog_weekly.DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH
    meta_path = paths.step_meta("fetch_app_catalog_weekly")

    rows = fetch_app_catalog_weekly.run(
        output_path=snapshot_path,
        checkpoint_path=checkpoint_path,
        latest_summary_path=latest_summary_path,
        timeout_seconds=10.0,
        max_attempts=4,
        backoff_base_seconds=0.5,
        jitter_max_seconds=0.3,
        max_backoff_seconds=8.0,
        max_results=max_results,
        meta_path=meta_path,
    )
    steps = [
        _step_result(
            name="fetch_app_catalog_weekly",
            rows=rows,
            paths={
                "checkpoint": checkpoint_path,
                "latest_summary": latest_summary_path,
                "meta": meta_path,
                "output": snapshot_path,
            },
        )
    ]
    triage = {
        "catalog_records": len(rows),
        "latest_summary_path": str(latest_summary_path),
    }
    return steps, triage


def _status_from_triage(job_name: str, triage: dict[str, Any]) -> str:
    if job_name == JOB_CCU_30M and triage.get("missing_evidence_records", 0) > 0:
        return "partial_success"
    if job_name == JOB_DAILY and triage.get("reviews_skipped_records", 0) > 0:
        return "partial_success"
    return "success"


def build_job_result(
    *,
    paths: JobPaths,
    started_at_utc: str,
    finished_at_utc: str,
    status: str,
    steps: list[dict[str, Any]],
    triage: dict[str, Any],
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build scheduler-facing job result evidence."""

    return {
        "duration_ms": _duration_ms(started_at_utc, finished_at_utc),
        "error_message": error_message,
        "error_type": error_type,
        "finished_at_utc": finished_at_utc,
        "hard_failure": status == "hard_failure",
        "job_name": paths.job_name,
        "lock_busy": status == "lock_busy",
        "partial_success": status == "partial_success",
        "paths": {
            "job_meta": str(paths.job_meta_path),
            "lock": str(paths.lock_path),
            "log": str(paths.log_path),
            "result": str(paths.result_path),
            "run_dir": str(paths.run_dir),
        },
        "run_id": paths.run_id,
        "started_at_utc": started_at_utc,
        "status": status,
        "steps": steps,
        "success": status in {"success", "partial_success"},
        "triage": triage,
    }


def write_job_evidence(result: dict[str, Any], paths: JobPaths) -> None:
    """Write result and job-level meta evidence for operators."""

    _write_json(paths.result_path, result)
    meta = build_execution_meta(
        job_name=f"steam_{paths.job_name.replace('-', '_')}",
        started_at_utc=str(result["started_at_utc"]),
        finished_at_utc=str(result["finished_at_utc"]),
        success=bool(result["success"]),
        http_status=None,
        retry_count=0,
        timeout_count=0,
        rate_limit_count=0,
        records_in=len(result["steps"]),
        records_out=sum(int(step.get("records_out", 0)) for step in result["steps"]),
        error_type=result["error_type"],
        error_message=result["error_message"],
    )
    meta.update(
        {
            "hard_failure": result["hard_failure"],
            "lock_busy": result["lock_busy"],
            "partial_success": result["partial_success"],
            "result_path": str(paths.result_path),
            "run_id": paths.run_id,
            "status": result["status"],
        }
    )
    _write_json(paths.job_meta_path, meta)


def run_job(
    job_name: str,
    *,
    base_dir: Path = DEFAULT_JOBS_BASE_DIR,
    run_id: str | None = None,
    lock_dir: Path | None = None,
    lock_wait_seconds: float = 0.0,
    app_catalog_path: Path
    | None = run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_APP_CATALOG_PATH,
    app_catalog_max_results: int | None = None,
) -> dict[str, Any]:
    """Run one scheduler job and return scheduler-facing result evidence."""

    if job_name not in JOB_CHOICES:
        raise ValueError(f"unsupported Steam cadence job: {job_name}")

    started_at_utc = utc_now_iso()
    paths = build_job_paths(
        job_name=job_name,
        base_dir=base_dir,
        run_id=run_id,
        lock_dir=lock_dir,
    )
    log_handler = configure_job_logging(paths.log_path)
    lock = NoOverlapLock(paths.lock_path)
    steps: list[dict[str, Any]] = []
    triage: dict[str, Any] = {}
    status = "hard_failure"
    error_type: str | None = None
    error_message: str | None = None

    try:
        LOGGER.info("Starting Steam cadence job %s run_id=%s", job_name, paths.run_id)
        if not lock.acquire(wait_seconds=lock_wait_seconds):
            status = "lock_busy"
            triage = {"reason": "same_job_already_running"}
            LOGGER.warning("Skipping Steam cadence job %s because lock is busy", job_name)
            return build_job_result(
                paths=paths,
                started_at_utc=started_at_utc,
                finished_at_utc=utc_now_iso(),
                status=status,
                steps=steps,
                triage=triage,
            )

        if job_name == JOB_PRICE_1H:
            steps, triage = run_price_job(paths)
        elif job_name == JOB_CCU_30M:
            steps, triage = run_ccu_job(paths)
        elif job_name == JOB_DAILY:
            steps, triage = run_daily_job(paths, app_catalog_path=app_catalog_path)
        elif job_name == JOB_APP_CATALOG_WEEKLY:
            steps, triage = run_app_catalog_job(
                paths,
                max_results=app_catalog_max_results,
            )

        status = _status_from_triage(job_name, triage)
        LOGGER.info("Finished Steam cadence job %s with status=%s", job_name, status)
        return build_job_result(
            paths=paths,
            started_at_utc=started_at_utc,
            finished_at_utc=utc_now_iso(),
            status=status,
            steps=steps,
            triage=triage,
        )
    except Exception as exc:  # pragma: no cover - defensive scheduler guard
        error_type = type(exc).__name__
        error_message = str(exc)
        LOGGER.exception("Steam cadence job %s failed", job_name)
        return build_job_result(
            paths=paths,
            started_at_utc=started_at_utc,
            finished_at_utc=utc_now_iso(),
            status="hard_failure",
            steps=steps,
            triage=triage,
            error_type=error_type,
            error_message=error_message,
        )
    finally:
        lock.release()
        _detach_logging_handler(log_handler)


def run_job_with_evidence(
    job_name: str,
    *,
    base_dir: Path = DEFAULT_JOBS_BASE_DIR,
    run_id: str | None = None,
    lock_dir: Path | None = None,
    lock_wait_seconds: float = 0.0,
    app_catalog_path: Path
    | None = run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_APP_CATALOG_PATH,
    app_catalog_max_results: int | None = None,
) -> dict[str, Any]:
    """Run one job and persist its scheduler-facing evidence files."""

    result = run_job(
        job_name,
        base_dir=base_dir,
        run_id=run_id,
        lock_dir=lock_dir,
        lock_wait_seconds=lock_wait_seconds,
        app_catalog_path=app_catalog_path,
        app_catalog_max_results=app_catalog_max_results,
    )
    paths = build_job_paths(
        job_name=job_name,
        base_dir=base_dir,
        run_id=str(result["run_id"]),
        lock_dir=lock_dir,
    )
    write_job_evidence(result, paths)
    return result


def exit_code_for_status(status: str) -> int:
    """Return process exit code for scheduler integration."""

    if status in {"success", "partial_success"}:
        return 0
    if status == "lock_busy":
        return LOCK_BUSY_EXIT_CODE
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for cadence-scoped Steam scheduler jobs."""

    parser = argparse.ArgumentParser(
        description="Run one cadence-scoped Steam job with scoped artifacts and locking"
    )
    parser.add_argument("job", choices=JOB_CHOICES)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_JOBS_BASE_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--lock-dir", type=Path, default=None)
    parser.add_argument("--lock-wait-sec", type=float, default=0.0)
    parser.add_argument(
        "--app-catalog-path",
        type=Path,
        default=run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_APP_CATALOG_PATH,
        help="Optional App Catalog latest summary consumed by the daily tracked universe job",
    )
    parser.add_argument(
        "--app-catalog-max-results",
        type=int,
        default=None,
        help="Optional max_results passthrough for app-catalog-weekly smoke runs",
    )
    return parser


def main() -> None:
    """CLI entrypoint for one cadence-scoped scheduler job."""

    args = build_parser().parse_args()
    result = run_job_with_evidence(
        args.job,
        base_dir=args.base_dir,
        run_id=args.run_id,
        lock_dir=args.lock_dir,
        lock_wait_seconds=args.lock_wait_sec,
        app_catalog_path=args.app_catalog_path,
        app_catalog_max_results=args.app_catalog_max_results,
    )
    raise SystemExit(exit_code_for_status(str(result["status"])))


if __name__ == "__main__":
    main()
