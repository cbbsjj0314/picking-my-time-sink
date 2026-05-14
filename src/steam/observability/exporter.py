"""Small Prometheus exporter for local scheduler and DB freshness signals."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from steam.ingest.app_catalog_latest_summary import DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH
from steam.ingest.run_steam_cadence_job import (
    DEFAULT_JOBS_BASE_DIR,
    JOB_APP_CATALOG_WEEKLY,
    JOB_CCU_30M,
    JOB_DAILY,
    JOB_PRICE_1H,
)

KST = ZoneInfo("Asia/Seoul")
STATUS_LABELS = ("success", "partial_success", "lock_busy", "hard_failure", "missing", "unknown")
APP_CATALOG_STATUS_LABELS = ("completed", "missing", "invalid", "other")
CADENCES = (JOB_CCU_30M, JOB_PRICE_1H, JOB_DAILY, JOB_APP_CATALOG_WEEKLY)
CHZZK_GUARDED_WRITE_TASK_NAME = "ChzzkFetchLoadGuardedWrite30m"
CHZZK_GUARDED_WRITE_TASK_PATH = "\\PickingMyTimeSink\\"
CHZZK_GUARDED_WRITE_WRAPPER_DIR = Path("tmp/chzzk/guarded-write-scheduler-wrapper")
CHZZK_WRAPPER_STATUS_LABELS = ("success", "partial_success", "hard_failure", "missing", "unknown")
CHZZK_DB_DATASETS = {
    "category_30m": "fact_chzzk_category_30m",
    "category_channel_30m": "fact_chzzk_category_channel_30m",
}


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One Prometheus text-format sample."""

    name: str
    value: float
    labels: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DbFreshnessSource:
    """A DB relation and max-timestamp query exposed as a freshness dataset."""

    dataset: str
    sql: str


DB_FRESHNESS_SOURCES = (
    DbFreshnessSource(
        dataset="rank_daily",
        sql="SELECT MAX(snapshot_date) FROM fact_steam_rank_daily",
    ),
    DbFreshnessSource(
        dataset="reviews_daily",
        sql="SELECT MAX(snapshot_date) FROM fact_steam_reviews_daily",
    ),
    DbFreshnessSource(
        dataset="price_1h",
        sql="SELECT MAX(bucket_time) FROM fact_steam_price_1h",
    ),
    DbFreshnessSource(
        dataset="ccu_30m",
        sql="SELECT MAX(bucket_time) FROM fact_steam_ccu_30m",
    ),
    DbFreshnessSource(
        dataset="ccu_daily_rollup",
        sql="SELECT MAX(bucket_date) FROM agg_steam_ccu_daily",
    ),
)

PSQL_FRESHNESS_SQL = """
SELECT 'rank_daily', EXTRACT(EPOCH FROM (MAX(snapshot_date)::timestamp AT TIME ZONE 'Asia/Seoul'))
FROM fact_steam_rank_daily
UNION ALL
SELECT
    'reviews_daily',
    EXTRACT(EPOCH FROM (MAX(snapshot_date)::timestamp AT TIME ZONE 'Asia/Seoul'))
FROM fact_steam_reviews_daily
UNION ALL
SELECT 'price_1h', EXTRACT(EPOCH FROM MAX(bucket_time))
FROM fact_steam_price_1h
UNION ALL
SELECT 'ccu_30m', EXTRACT(EPOCH FROM MAX(bucket_time))
FROM fact_steam_ccu_30m
UNION ALL
SELECT
    'ccu_daily_rollup',
    EXTRACT(EPOCH FROM (MAX(bucket_date)::timestamp AT TIME ZONE 'Asia/Seoul'))
FROM agg_steam_ccu_daily
"""

METRIC_HELP = {
    "steam_observability_exporter_up": "Whether the Steam observability exporter rendered metrics.",
    "steam_observability_exporter_scrape_timestamp_seconds": (
        "Unix timestamp when the exporter rendered this scrape."
    ),
    "steam_scheduler_latest_run_present": (
        "Whether a latest scheduler result exists for the cadence."
    ),
    "steam_scheduler_latest_run_timestamp_seconds": (
        "Latest scheduler run finished_at timestamp by cadence."
    ),
    "steam_scheduler_latest_run_status": (
        "Latest scheduler run status by cadence. The active status label has value 1."
    ),
    "steam_scheduler_latest_run_duration_seconds": (
        "Latest scheduler run wall-clock duration in seconds by cadence."
    ),
    "steam_scheduler_latest_run_partial_success": (
        "Latest scheduler run partial-success flag by cadence."
    ),
    "steam_scheduler_latest_ccu_missing_evidence_records": (
        "Latest ccu-30m run per-app missing evidence record count."
    ),
    "steam_scheduler_latest_daily_reviews_skipped_records": (
        "Latest daily run reviews skipped evidence record count."
    ),
    "steam_db_freshness_query_success": (
        "Whether all configured DB freshness queries succeeded during this scrape."
    ),
    "steam_db_dataset_freshness_available": (
        "Whether a dataset latest timestamp was available during this scrape."
    ),
    "steam_db_dataset_latest_timestamp_seconds": (
        "Latest available dataset timestamp as Unix seconds."
    ),
    "steam_db_dataset_freshness_age_seconds": (
        "Age in seconds from scrape time to the dataset latest timestamp."
    ),
    "steam_app_catalog_latest_summary_exists": (
        "Whether the optional App Catalog latest summary artifact exists and is valid JSON."
    ),
    "steam_app_catalog_latest_summary_status": (
        "Optional App Catalog latest summary status. The active status label has value 1."
    ),
    "steam_app_catalog_latest_summary_finished_timestamp_seconds": (
        "Optional App Catalog latest summary finished_at timestamp."
    ),
    "steam_app_catalog_latest_summary_app_count": (
        "Optional App Catalog latest summary app count when present."
    ),
    "chzzk_guarded_write_scheduler_task_available": (
        "Whether the Chzzk guarded-write scheduler task was readable."
    ),
    "chzzk_guarded_write_scheduler_task_enabled": (
        "Whether the Chzzk guarded-write scheduler task is enabled."
    ),
    "chzzk_guarded_write_scheduler_last_result": (
        "Latest Windows Task Scheduler result code for the Chzzk guarded-write task."
    ),
    "chzzk_guarded_write_scheduler_latest_run_age_seconds": (
        "Age in seconds from scrape time to the scheduler latest run time."
    ),
    "chzzk_guarded_write_scheduler_recent_missing_intervals": (
        "Recent missed-run count reported by Task Scheduler for the guarded-write task."
    ),
    "chzzk_guarded_write_scheduler_recent_new_instance_ignored_events": (
        "Recent Task Scheduler Event ID 322/NewInstanceIgnored count for guarded-write."
    ),
    "chzzk_guarded_write_wrapper_latest_run_status": (
        "Latest guarded-write wrapper status. The active status label has value 1."
    ),
    "chzzk_guarded_write_wrapper_latest_run_age_seconds": (
        "Age in seconds from scrape time to the latest guarded-write wrapper evidence."
    ),
    "chzzk_guarded_write_wrapper_latest_committed_rows": (
        "Latest guarded-write sanitized committed row count by dataset."
    ),
    "chzzk_db_dataset_freshness_age_seconds": (
        "Age in seconds from scrape time to the Chzzk dataset latest bucket."
    ),
    "chzzk_db_latest_bucket_rows": (
        "Rows in each Chzzk dataset at its latest bucket_time."
    ),
}


def utc_now() -> dt.datetime:
    """Return the current aware UTC timestamp."""

    return dt.datetime.now(dt.UTC)


def parse_datetime_utc(value: object) -> dt.datetime | None:
    """Parse an ISO timestamp-like value into UTC."""

    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def timestamp_seconds(value: dt.datetime) -> float:
    """Return Unix timestamp seconds for an aware datetime."""

    return value.astimezone(dt.UTC).timestamp()


def _date_or_datetime_to_utc(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min, tzinfo=KST).astimezone(dt.UTC)
    return None


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    return default


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _load_json_mapping(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_latest_job_result(jobs_dir: Path, cadence: str) -> Mapping[str, Any] | None:
    """Load the newest readable scheduler result for one cadence."""

    cadence_dir = jobs_dir / cadence
    if not cadence_dir.is_dir():
        return None

    latest_result: Mapping[str, Any] | None = None
    latest_key: tuple[float, str] | None = None
    for result_path in cadence_dir.glob("*/result.json"):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        finished_at = parse_datetime_utc(payload.get("finished_at_utc"))
        sort_timestamp = timestamp_seconds(finished_at) if finished_at else 0.0
        sort_key = (sort_timestamp, result_path.parent.name)
        if latest_key is None or sort_key > latest_key:
            latest_key = sort_key
            latest_result = payload

    return latest_result


def collect_scheduler_metrics(jobs_dir: Path) -> list[MetricSample]:
    """Collect scheduler metrics from local result.json evidence."""

    samples: list[MetricSample] = []

    for cadence in CADENCES:
        result = load_latest_job_result(jobs_dir, cadence)
        if result is None:
            samples.append(
                MetricSample("steam_scheduler_latest_run_present", 0.0, {"cadence": cadence})
            )
            samples.extend(
                MetricSample(
                    "steam_scheduler_latest_run_status",
                    1.0 if status == "missing" else 0.0,
                    {"cadence": cadence, "status": status},
                )
                for status in STATUS_LABELS
            )
            continue

        status = str(result.get("status") or "unknown")
        if status not in STATUS_LABELS:
            status = "unknown"

        samples.append(
            MetricSample("steam_scheduler_latest_run_present", 1.0, {"cadence": cadence})
        )
        samples.extend(
            MetricSample(
                "steam_scheduler_latest_run_status",
                1.0 if label == status else 0.0,
                {"cadence": cadence, "status": label},
            )
            for label in STATUS_LABELS
        )

        finished_at = parse_datetime_utc(result.get("finished_at_utc"))
        if finished_at is not None:
            samples.append(
                MetricSample(
                    "steam_scheduler_latest_run_timestamp_seconds",
                    timestamp_seconds(finished_at),
                    {"cadence": cadence},
                )
            )

        samples.append(
            MetricSample(
                "steam_scheduler_latest_run_duration_seconds",
                _number(result.get("duration_ms")) / 1000.0,
                {"cadence": cadence},
            )
        )
        samples.append(
            MetricSample(
                "steam_scheduler_latest_run_partial_success",
                _number(result.get("partial_success")),
                {"cadence": cadence},
            )
        )

        triage = result.get("triage")
        triage_mapping = triage if isinstance(triage, dict) else {}
        if cadence == JOB_CCU_30M:
            samples.append(
                MetricSample(
                    "steam_scheduler_latest_ccu_missing_evidence_records",
                    _number(triage_mapping.get("missing_evidence_records")),
                    {"cadence": cadence},
                )
            )
        if cadence == JOB_DAILY:
            samples.append(
                MetricSample(
                    "steam_scheduler_latest_daily_reviews_skipped_records",
                    _number(triage_mapping.get("reviews_skipped_records")),
                    {"cadence": cadence},
                )
            )

    return samples


def build_pg_conninfo_from_env() -> str:
    """Build a psycopg conninfo from POSTGRES_* environment variables."""

    required_names = ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [name for name in required_names if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")

    try:
        from psycopg.conninfo import make_conninfo
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency is locked for runtime.
        raise RuntimeError("psycopg is required for DB freshness metrics") from exc

    return make_conninfo(
        host=os.environ["POSTGRES_HOST"],
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def _default_pg_connect(conninfo: str) -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency is locked for runtime.
        raise RuntimeError("psycopg is required for DB freshness metrics") from exc

    return psycopg.connect(conninfo=conninfo)


def _fetch_db_latest_values_with_psycopg(
    connect: Callable[[str], Any],
) -> dict[str, object]:
    conninfo = build_pg_conninfo_from_env()
    latest_values: dict[str, object] = {}
    with connect(conninfo) as conn:
        with conn.cursor() as cursor:
            for source in DB_FRESHNESS_SOURCES:
                cursor.execute(source.sql)
                row = cursor.fetchone()
                latest_values[source.dataset] = row[0] if row else None
    return latest_values


def _fetch_db_latest_values_with_psql() -> dict[str, object]:
    required_names = ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [name for name in required_names if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")

    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ["POSTGRES_PASSWORD"]
    command = [
        "psql",
        "-h",
        os.environ["POSTGRES_HOST"],
        "-p",
        os.getenv("POSTGRES_PORT", "5432"),
        "-U",
        os.environ["POSTGRES_USER"],
        "-d",
        os.environ["POSTGRES_DB"],
        "-qAt",
        "-F",
        "|",
        "-c",
        PSQL_FRESHNESS_SQL,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        check=True,
        env=env,
        text=True,
        timeout=10,
    )

    latest_values: dict[str, object] = {}
    for line in completed.stdout.splitlines():
        dataset, separator, epoch_text = line.partition("|")
        if not separator or not dataset:
            continue
        latest_values[dataset] = (
            dt.datetime.fromtimestamp(float(epoch_text), dt.UTC) if epoch_text else None
        )
    return latest_values


def collect_db_freshness_metrics(
    *,
    now: dt.datetime,
    connect: Callable[[str], Any] = _default_pg_connect,
) -> list[MetricSample]:
    """Collect latest-timestamp freshness metrics from Postgres."""

    samples: list[MetricSample] = []
    failed_datasets: set[str] = set()
    query_success = True

    try:
        latest_values = _fetch_db_latest_values_with_psycopg(connect)
    except Exception:
        try:
            latest_values = _fetch_db_latest_values_with_psql()
        except Exception:
            latest_values = {}
            query_success = False
            failed_datasets.update(source.dataset for source in DB_FRESHNESS_SOURCES)

    samples.append(
        MetricSample("steam_db_freshness_query_success", 1.0 if query_success else 0.0)
    )

    now_utc = now.astimezone(dt.UTC)
    for source in DB_FRESHNESS_SOURCES:
        labels = {"dataset": source.dataset}
        latest_value = latest_values.get(source.dataset)
        latest_at = _date_or_datetime_to_utc(latest_value)
        available = latest_at is not None and source.dataset not in failed_datasets
        samples.append(
            MetricSample(
                "steam_db_dataset_freshness_available",
                1.0 if available else 0.0,
                labels,
            )
        )
        if latest_at is None:
            continue

        latest_timestamp = timestamp_seconds(latest_at)
        age_seconds = max((now_utc - latest_at).total_seconds(), 0.0)
        samples.append(
            MetricSample("steam_db_dataset_latest_timestamp_seconds", latest_timestamp, labels)
        )
        samples.append(MetricSample("steam_db_dataset_freshness_age_seconds", age_seconds, labels))

    return samples


def _default_chzzk_scheduler_command() -> list[str]:
    script = rf"""
$taskName = '{CHZZK_GUARDED_WRITE_TASK_NAME}'
$taskPath = '{CHZZK_GUARDED_WRITE_TASK_PATH}'
$windowStart = (Get-Date).AddHours(-24)
try {{
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $eventCount = 0
    try {{
        $filter = @{{
            LogName='Microsoft-Windows-TaskScheduler/Operational'
            Id=322
            StartTime=$windowStart
        }}
        $events = Get-WinEvent -FilterHashtable $filter -ErrorAction SilentlyContinue
        $eventCount = @($events | Where-Object {{ $_.Message -like "*$taskName*" }}).Count
    }} catch {{
        $eventCount = 0
    }}
    [pscustomobject]@{{
        task_available = $true
        task_enabled = ($task.State -ne 'Disabled')
        last_result = $info.LastTaskResult
        latest_run_time = $info.LastRunTime.ToUniversalTime().ToString('o')
        missed_runs = $info.NumberOfMissedRuns
        new_instance_ignored_events = $eventCount
    }} | ConvertTo-Json -Compress
}} catch {{
    [pscustomobject]@{{
        task_available = $false
        task_enabled = $false
        last_result = $null
        latest_run_time = $null
        missed_runs = 0
        new_instance_ignored_events = 0
    }} | ConvertTo-Json -Compress
}}
"""
    return ["powershell.exe", "-NoProfile", "-Command", script]


def _run_chzzk_scheduler_query(command: list[str] | None = None) -> str:
    completed = subprocess.run(
        command or _default_chzzk_scheduler_command(),
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


def parse_chzzk_scheduler_payload(payload_text: str) -> Mapping[str, Any] | None:
    """Parse sanitized scheduler JSON output."""

    try:
        loaded = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def collect_chzzk_scheduler_metrics(
    *,
    now: dt.datetime,
    runner: Callable[[], str] = _run_chzzk_scheduler_query,
) -> list[MetricSample]:
    """Collect read-only Chzzk guarded-write scheduler metrics."""

    try:
        payload = parse_chzzk_scheduler_payload(runner())
    except Exception:
        payload = None

    available = bool(payload and payload.get("task_available") is True)
    enabled = bool(payload and payload.get("task_enabled") is True)
    samples = [
        MetricSample("chzzk_guarded_write_scheduler_task_available", 1.0 if available else 0.0),
        MetricSample("chzzk_guarded_write_scheduler_task_enabled", 1.0 if enabled else 0.0),
    ]
    if payload is None:
        samples.extend(
            [
                MetricSample("chzzk_guarded_write_scheduler_last_result", -1.0),
                MetricSample("chzzk_guarded_write_scheduler_recent_missing_intervals", 0.0),
                MetricSample(
                    "chzzk_guarded_write_scheduler_recent_new_instance_ignored_events",
                    0.0,
                ),
            ]
        )
        return samples

    last_result = _int_or_none(payload.get("last_result"))
    samples.append(
        MetricSample(
            "chzzk_guarded_write_scheduler_last_result",
            float(last_result) if last_result is not None else -1.0,
        )
    )
    latest_run_time = parse_datetime_utc(payload.get("latest_run_time"))
    if latest_run_time is not None:
        age_seconds = max(
            (now.astimezone(dt.UTC) - latest_run_time).total_seconds(),
            0.0,
        )
        samples.append(
            MetricSample("chzzk_guarded_write_scheduler_latest_run_age_seconds", age_seconds)
        )
    samples.append(
        MetricSample(
            "chzzk_guarded_write_scheduler_recent_missing_intervals",
            _number(payload.get("missed_runs")),
        )
    )
    samples.append(
        MetricSample(
            "chzzk_guarded_write_scheduler_recent_new_instance_ignored_events",
            _number(payload.get("new_instance_ignored_events")),
        )
    )
    return samples


def _latest_child_dir(base_dir: Path) -> Path | None:
    if not base_dir.is_dir():
        return None
    dirs = [path for path in base_dir.iterdir() if path.is_dir()]
    return max(dirs, key=lambda path: path.name, default=None)


def _wrapper_status(run_dir: Path | None) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    if run_dir is None:
        return "missing", {}, {}
    trace_end = _load_json_mapping(run_dir / "trace" / "end.json")
    guarded = _load_json_mapping(run_dir / "guarded-write-result.json")
    no_write = _load_json_mapping(run_dir / "no-write-result.json")
    if guarded is None:
        return "missing", {}, no_write or {}
    status = str(guarded.get("status") or "unknown")
    if status not in CHZZK_WRAPPER_STATUS_LABELS:
        status = "unknown"
    exit_code = _int_or_none((trace_end or {}).get("exit_code"))
    if exit_code is not None and exit_code != 0 and status == "success":
        status = "unknown"
    return status, guarded, no_write or {}


def _parse_wrapper_boundary_timestamp(run_dir: Path) -> dt.datetime | None:
    try:
        parsed = dt.datetime.strptime(run_dir.name, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.UTC)


def _wrapper_latest_timestamp(
    *,
    run_dir: Path | None,
    guarded: Mapping[str, Any],
    no_write: Mapping[str, Any],
) -> dt.datetime | None:
    if run_dir is None:
        return None
    trace_end = _load_json_mapping(run_dir / "trace" / "end.json") or {}
    candidates = (
        guarded.get("finished_at_utc"),
        trace_end.get("recorded_at_utc"),
        no_write.get("finished_at_utc"),
    )
    for candidate in candidates:
        parsed = parse_datetime_utc(candidate)
        if parsed is not None:
            return parsed
    return _parse_wrapper_boundary_timestamp(run_dir)


def collect_chzzk_wrapper_metrics(*, now: dt.datetime, wrapper_dir: Path) -> list[MetricSample]:
    """Collect metrics from sanitized guarded-write wrapper evidence."""

    run_dir = _latest_child_dir(wrapper_dir)
    status, guarded, no_write = _wrapper_status(run_dir)
    samples = [
        MetricSample(
            "chzzk_guarded_write_wrapper_latest_run_status",
            1.0 if label == status else 0.0,
            {"status": label},
        )
        for label in CHZZK_WRAPPER_STATUS_LABELS
    ]
    latest_at = _wrapper_latest_timestamp(run_dir=run_dir, guarded=guarded, no_write=no_write)
    if latest_at is not None:
        samples.append(
            MetricSample(
                "chzzk_guarded_write_wrapper_latest_run_age_seconds",
                max((now.astimezone(dt.UTC) - latest_at).total_seconds(), 0.0),
            )
        )
    guarded_write = guarded.get("guarded_write") if isinstance(guarded, Mapping) else None
    guarded_mapping = guarded_write if isinstance(guarded_write, Mapping) else {}
    for dataset, key in (("category", "category"), ("channel", "channel")):
        summary = guarded_mapping.get(key)
        summary_mapping = summary if isinstance(summary, Mapping) else {}
        samples.append(
            MetricSample(
                "chzzk_guarded_write_wrapper_latest_committed_rows",
                _number(summary_mapping.get("committed_row_count")),
                {"dataset": dataset},
            )
        )
    return samples


def _fetch_chzzk_db_values_with_psycopg(connect: Callable[[str], Any]) -> dict[str, object]:
    conninfo = build_pg_conninfo_from_env()
    values: dict[str, object] = {}
    with connect(conninfo) as conn:
        with conn.cursor() as cursor:
            for dataset, relation in CHZZK_DB_DATASETS.items():
                cursor.execute(f"SELECT MAX(bucket_time) FROM {relation}")
                row = cursor.fetchone()
                latest_bucket = row[0] if row else None
                values[f"{dataset}:latest_bucket"] = latest_bucket
                if latest_bucket is None:
                    values[f"{dataset}:latest_rows"] = None
                    continue
                cursor.execute(
                    f"SELECT COUNT(*) FROM {relation} WHERE bucket_time = %s",
                    (latest_bucket,),
                )
                row = cursor.fetchone()
                values[f"{dataset}:latest_rows"] = row[0] if row else None
    return values


def collect_chzzk_db_metrics(
    *,
    now: dt.datetime,
    connect: Callable[[str], Any] = _default_pg_connect,
) -> list[MetricSample]:
    """Collect read-only Chzzk DB freshness and latest bucket row metrics."""

    try:
        values = _fetch_chzzk_db_values_with_psycopg(connect)
    except Exception:
        values = {}

    samples: list[MetricSample] = []
    now_utc = now.astimezone(dt.UTC)
    for dataset in CHZZK_DB_DATASETS:
        labels = {"dataset": dataset}
        latest_at = _date_or_datetime_to_utc(values.get(f"{dataset}:latest_bucket"))
        if latest_at is not None:
            samples.append(
                MetricSample(
                    "chzzk_db_dataset_freshness_age_seconds",
                    max((now_utc - latest_at).total_seconds(), 0.0),
                    labels,
                )
            )
        samples.append(
            MetricSample(
                "chzzk_db_latest_bucket_rows",
                _number(values.get(f"{dataset}:latest_rows")),
                labels,
            )
        )
    return samples


def collect_chzzk_metrics(
    *,
    now: dt.datetime,
    wrapper_dir: Path = CHZZK_GUARDED_WRITE_WRAPPER_DIR,
    scheduler_runner: Callable[[], str] = _run_chzzk_scheduler_query,
    connect: Callable[[str], Any] = _default_pg_connect,
) -> list[MetricSample]:
    """Collect all Chzzk guarded-write read-only metrics for one scrape."""

    samples: list[MetricSample] = []
    samples.extend(collect_chzzk_scheduler_metrics(now=now, runner=scheduler_runner))
    samples.extend(collect_chzzk_wrapper_metrics(now=now, wrapper_dir=wrapper_dir))
    samples.extend(collect_chzzk_db_metrics(now=now, connect=connect))
    return samples


def collect_app_catalog_summary_metrics(summary_path: Path) -> list[MetricSample]:
    """Collect optional App Catalog latest summary existence and status metrics."""

    samples: list[MetricSample] = []
    exists = False
    active_status = "missing"
    payload: Mapping[str, Any] = {}

    if summary_path.exists():
        try:
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                exists = True
                payload = loaded
                loaded_status = str(loaded.get("status") or "other")
                active_status = loaded_status if loaded_status == "completed" else "other"
            else:
                active_status = "invalid"
        except (OSError, json.JSONDecodeError):
            active_status = "invalid"

    samples.append(MetricSample("steam_app_catalog_latest_summary_exists", 1.0 if exists else 0.0))
    samples.extend(
        MetricSample(
            "steam_app_catalog_latest_summary_status",
            1.0 if status == active_status else 0.0,
            {"status": status},
        )
        for status in APP_CATALOG_STATUS_LABELS
    )

    finished_at = parse_datetime_utc(payload.get("finished_at_utc"))
    if finished_at is not None:
        samples.append(
            MetricSample(
                "steam_app_catalog_latest_summary_finished_timestamp_seconds",
                timestamp_seconds(finished_at),
            )
        )

    response = payload.get("response")
    excerpt = response.get("payload_excerpt_or_json") if isinstance(response, dict) else None
    app_count = excerpt.get("app_count") if isinstance(excerpt, dict) else None
    if isinstance(app_count, int):
        samples.append(MetricSample("steam_app_catalog_latest_summary_app_count", float(app_count)))

    return samples


def collect_metrics(
    *,
    jobs_dir: Path,
    app_catalog_summary_path: Path,
    now: dt.datetime | None = None,
) -> list[MetricSample]:
    """Collect all exporter metrics for one scrape."""

    scrape_time = now or utc_now()
    samples = [
        MetricSample("steam_observability_exporter_up", 1.0),
        MetricSample(
            "steam_observability_exporter_scrape_timestamp_seconds",
            timestamp_seconds(scrape_time),
        ),
    ]
    samples.extend(collect_scheduler_metrics(jobs_dir))
    samples.extend(collect_db_freshness_metrics(now=scrape_time))
    samples.extend(collect_app_catalog_summary_metrics(app_catalog_summary_path))
    samples.extend(collect_chzzk_metrics(now=scrape_time))
    return samples


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_sample(sample: MetricSample) -> str:
    label_text = ""
    if sample.labels:
        labels = ",".join(
            f'{name}="{_escape_label_value(value)}"'
            for name, value in sorted(sample.labels.items())
        )
        label_text = f"{{{labels}}}"
    return f"{sample.name}{label_text} {sample.value:.17g}"


def render_prometheus_text(samples: list[MetricSample]) -> str:
    """Render samples as Prometheus text exposition format."""

    lines: list[str] = []
    sample_names = {sample.name for sample in samples}
    for name in sorted(sample_names):
        help_text = METRIC_HELP.get(name)
        if help_text is not None:
            lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for sample in sorted(
            (sample for sample in samples if sample.name == name),
            key=lambda item: tuple(sorted(item.labels.items())),
        ):
            lines.append(_format_sample(sample))
    return "\n".join(lines) + "\n"


def make_metrics_handler(
    *,
    jobs_dir: Path,
    app_catalog_summary_path: Path,
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to the configured local paths."""

    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                self.send_response(HTTPStatus.OK)
                self.end_headers()
                self.wfile.write(b"ok\n")
                return
            if self.path != "/metrics":
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                self.wfile.write(b"not found\n")
                return

            body = render_prometheus_text(
                collect_metrics(
                    jobs_dir=jobs_dir,
                    app_catalog_summary_path=app_catalog_summary_path,
                )
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return MetricsHandler


def serve_metrics(
    *,
    host: str,
    port: int,
    jobs_dir: Path,
    app_catalog_summary_path: Path,
) -> None:
    """Serve /metrics until the process receives a termination signal."""

    handler = make_metrics_handler(
        jobs_dir=jobs_dir,
        app_catalog_summary_path=app_catalog_summary_path,
    )
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the local Steam observability exporter."""

    parser = argparse.ArgumentParser(
        description="Expose local Steam scheduler and DB freshness metrics for Prometheus"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9308)
    parser.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS_BASE_DIR)
    parser.add_argument(
        "--app-catalog-summary-path",
        type=Path,
        default=DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Render one metrics payload to stdout instead of serving HTTP",
    )
    return parser


def main() -> None:
    """CLI entrypoint for the local Steam observability exporter."""

    args = build_parser().parse_args()
    if args.once:
        print(
            render_prometheus_text(
                collect_metrics(
                    jobs_dir=args.jobs_dir,
                    app_catalog_summary_path=args.app_catalog_summary_path,
                )
            ),
            end="",
        )
        return

    serve_metrics(
        host=args.host,
        port=args.port,
        jobs_dir=args.jobs_dir,
        app_catalog_summary_path=args.app_catalog_summary_path,
    )


if __name__ == "__main__":
    main()
