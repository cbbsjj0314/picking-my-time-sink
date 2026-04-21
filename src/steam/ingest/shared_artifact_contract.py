"""Shared retained-artifact contract for desktop-authority writes and read-only reuse."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steam.ingest.app_catalog_latest_summary import extract_catalog_metadata
from steam.ingest.run_steam_cadence_job import (
    JOB_APP_CATALOG_WEEKLY,
    JOB_CCU_30M,
    JOB_DAILY,
    JOB_PRICE_1H,
)

SHARED_ARTIFACT_SCHEMA_VERSION = "1.0"
SHARED_ARTIFACT_PREFIX = "steam/authority"
SHARED_BOUNDARY_MODE = "desktop_write_macbook_read_only"


@dataclass(frozen=True, slots=True)
class SharedArtifactSpec:
    """One retained artifact intentionally exposed through the shared read-only seam."""

    artifact_id: str
    file_name: str
    content_type: str
    required_for: tuple[str, ...]


RUN_SHARED_ARTIFACTS: dict[str, tuple[SharedArtifactSpec, ...]] = {
    JOB_PRICE_1H: (
        SharedArtifactSpec(
            artifact_id="job_result",
            file_name="result.json",
            content_type="application/json",
            required_for=("scheduler_latest", "observability"),
        ),
    ),
    JOB_CCU_30M: (
        SharedArtifactSpec(
            artifact_id="job_result",
            file_name="result.json",
            content_type="application/json",
            required_for=(
                "scheduler_latest",
                "observability",
                "retained_partial_success_probe",
            ),
        ),
        SharedArtifactSpec(
            artifact_id="ccu_silver_evidence",
            file_name="ccu.silver.jsonl",
            content_type="application/x-ndjson",
            required_for=("retained_partial_success_probe",),
        ),
    ),
    JOB_DAILY: (
        SharedArtifactSpec(
            artifact_id="job_result",
            file_name="result.json",
            content_type="application/json",
            required_for=(
                "scheduler_latest",
                "observability",
                "retained_partial_success_probe",
            ),
        ),
        SharedArtifactSpec(
            artifact_id="reviews_silver_evidence",
            file_name="reviews.silver.jsonl",
            content_type="application/x-ndjson",
            required_for=("retained_partial_success_probe",),
        ),
    ),
    JOB_APP_CATALOG_WEEKLY: (
        SharedArtifactSpec(
            artifact_id="job_result",
            file_name="result.json",
            content_type="application/json",
            required_for=("scheduler_latest",),
        ),
        SharedArtifactSpec(
            artifact_id="app_catalog_snapshot",
            file_name="app_catalog.snapshot.jsonl",
            content_type="application/x-ndjson",
            required_for=("tracked_universe_catalog_filter",),
        ),
    ),
}


def _validate_segment(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is empty")
    if "/" in normalized:
        raise ValueError(f"{field_name} must not contain '/'")
    return normalized


def shared_artifacts_for_job(job_name: str) -> tuple[SharedArtifactSpec, ...]:
    """Return the retained shared-artifact subset for one supported cadence job."""

    try:
        return RUN_SHARED_ARTIFACTS[job_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported shared-artifact job: {job_name}") from exc


def build_run_object_prefix(*, job_name: str, run_id: str) -> str:
    """Return the shared object prefix for one cadence run."""

    normalized_job_name = _validate_segment(job_name, field_name="job_name")
    normalized_run_id = _validate_segment(run_id, field_name="run_id")
    return f"{SHARED_ARTIFACT_PREFIX}/jobs/{normalized_job_name}/runs/{normalized_run_id}"


def build_run_object_key(*, job_name: str, run_id: str, file_name: str) -> str:
    """Return the shared object key for one retained run artifact."""

    normalized_file_name = _validate_segment(file_name, field_name="file_name")
    return f"{build_run_object_prefix(job_name=job_name, run_id=run_id)}/{normalized_file_name}"


def build_latest_manifest_key(job_name: str) -> str:
    """Return the shared latest-manifest key for one cadence job."""

    normalized_job_name = _validate_segment(job_name, field_name="job_name")
    return f"{SHARED_ARTIFACT_PREFIX}/jobs/{normalized_job_name}/latest/manifest.json"


def build_app_catalog_latest_summary_key() -> str:
    """Return the shared latest-summary key for App Catalog consumers."""

    return f"{SHARED_ARTIFACT_PREFIX}/app_catalog/latest.summary.json"


def build_latest_job_manifest(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shared latest manifest from one cadence job result payload."""

    job_name = _validate_segment(str(result.get("job_name") or ""), field_name="job_name")
    run_id = _validate_segment(str(result.get("run_id") or ""), field_name="run_id")
    status = str(result.get("status") or "unknown")
    finished_at_utc = str(result.get("finished_at_utc") or "")
    if not finished_at_utc:
        raise ValueError("finished_at_utc is empty")

    artifacts = [
        {
            "artifact_id": spec.artifact_id,
            "content_type": spec.content_type,
            "file_name": spec.file_name,
            "object_key": build_run_object_key(
                job_name=job_name,
                run_id=run_id,
                file_name=spec.file_name,
            ),
            "required_for": list(spec.required_for),
        }
        for spec in shared_artifacts_for_job(job_name)
    ]

    return {
        "schema_version": SHARED_ARTIFACT_SCHEMA_VERSION,
        "boundary_mode": SHARED_BOUNDARY_MODE,
        "writer_role": "desktop_authority",
        "consumer_role": "macbook_read_only",
        "job_name": job_name,
        "run_id": run_id,
        "status": status,
        "finished_at_utc": finished_at_utc,
        "manifest_key": build_latest_manifest_key(job_name),
        "run_prefix": build_run_object_prefix(job_name=job_name, run_id=run_id),
        "artifacts": artifacts,
    }


def _snapshot_object_key_from_summary(snapshot_path: str | None) -> str | None:
    if not snapshot_path:
        return None

    path = Path(snapshot_path)
    parts = path.parts
    try:
        jobs_index = parts.index("jobs")
    except ValueError:
        return None

    if len(parts) <= jobs_index + 3:
        return None

    job_name = parts[jobs_index + 1]
    run_id = parts[jobs_index + 2]
    file_name = parts[jobs_index + 3]
    if job_name != JOB_APP_CATALOG_WEEKLY:
        return None
    return build_run_object_key(job_name=job_name, run_id=run_id, file_name=file_name)


def build_app_catalog_latest_manifest(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shared latest-summary manifest for App Catalog read-only reuse."""

    metadata = extract_catalog_metadata(dict(summary))
    status = str(summary.get("status") or "unknown")
    finished_at_utc = str(summary.get("finished_at_utc") or "")
    if not finished_at_utc:
        raise ValueError("finished_at_utc is empty")

    snapshot_object_key = _snapshot_object_key_from_summary(metadata["snapshot_path"])
    pagination = metadata["pagination"]
    summary_required_for = ["tracked_universe_catalog_filter", "observability"]
    snapshot_required_for = (
        ["tracked_universe_catalog_filter"]
        if status == "completed"
        and pagination.get("have_more_results") is False
        and snapshot_object_key is not None
        else []
    )

    return {
        "schema_version": SHARED_ARTIFACT_SCHEMA_VERSION,
        "boundary_mode": SHARED_BOUNDARY_MODE,
        "writer_role": "desktop_authority",
        "consumer_role": "macbook_read_only",
        "job_name": JOB_APP_CATALOG_WEEKLY,
        "status": status,
        "finished_at_utc": finished_at_utc,
        "summary_schema_version": str(summary.get("schema_version") or ""),
        "artifacts": [
            {
                "artifact_id": "app_catalog_latest_summary",
                "content_type": "application/json",
                "object_key": build_app_catalog_latest_summary_key(),
                "required_for": summary_required_for,
            },
            {
                "artifact_id": "app_catalog_snapshot",
                "content_type": "application/x-ndjson",
                "object_key": snapshot_object_key,
                "required_for": snapshot_required_for,
            },
        ],
        "snapshot_complete": (
            status == "completed" and pagination.get("have_more_results") is False
        ),
    }
