from __future__ import annotations

from pathlib import Path

from steam.ingest import app_catalog_latest_summary, shared_artifact_contract


def test_build_latest_job_manifest_for_ccu_partial_success() -> None:
    manifest = shared_artifact_contract.build_latest_job_manifest(
        {
            "job_name": "ccu-30m",
            "run_id": "20260422T010203000000Z",
            "status": "partial_success",
            "finished_at_utc": "2026-04-22T01:32:03Z",
        }
    )

    assert manifest["boundary_mode"] == "desktop_write_macbook_read_only"
    assert manifest["manifest_key"] == "steam/authority/jobs/ccu-30m/latest/manifest.json"
    assert manifest["run_prefix"] == (
        "steam/authority/jobs/ccu-30m/runs/20260422T010203000000Z"
    )
    assert manifest["artifacts"] == [
        {
            "artifact_id": "job_result",
            "content_type": "application/json",
            "file_name": "result.json",
            "object_key": (
                "steam/authority/jobs/ccu-30m/runs/20260422T010203000000Z/result.json"
            ),
            "required_for": [
                "scheduler_latest",
                "observability",
                "retained_partial_success_probe",
            ],
        },
        {
            "artifact_id": "ccu_silver_evidence",
            "content_type": "application/x-ndjson",
            "file_name": "ccu.silver.jsonl",
            "object_key": (
                "steam/authority/jobs/ccu-30m/runs/20260422T010203000000Z/ccu.silver.jsonl"
            ),
            "required_for": ["retained_partial_success_probe"],
        },
    ]


def test_build_latest_job_manifest_for_daily_includes_reviews_evidence() -> None:
    manifest = shared_artifact_contract.build_latest_job_manifest(
        {
            "job_name": "daily",
            "run_id": "20260422T020304000000Z",
            "status": "success",
            "finished_at_utc": "2026-04-22T02:33:04Z",
        }
    )

    assert manifest["manifest_key"] == "steam/authority/jobs/daily/latest/manifest.json"
    assert manifest["artifacts"] == [
        {
            "artifact_id": "job_result",
            "content_type": "application/json",
            "file_name": "result.json",
            "object_key": (
                "steam/authority/jobs/daily/runs/20260422T020304000000Z/result.json"
            ),
            "required_for": [
                "scheduler_latest",
                "observability",
                "retained_partial_success_probe",
            ],
        },
        {
            "artifact_id": "reviews_silver_evidence",
            "content_type": "application/x-ndjson",
            "file_name": "reviews.silver.jsonl",
            "object_key": (
                "steam/authority/jobs/daily/runs/20260422T020304000000Z/reviews.silver.jsonl"
            ),
            "required_for": ["retained_partial_success_probe"],
        },
    ]


def test_build_app_catalog_latest_manifest_uses_existing_summary_shape() -> None:
    summary = app_catalog_latest_summary.build_latest_summary(
        job_name="fetch_app_catalog_weekly",
        started_at_utc="2026-04-22T03:00:00Z",
        finished_at_utc="2026-04-22T03:05:00Z",
        snapshot_path=Path(
            "tmp/steam/jobs/app-catalog-weekly/20260422T030000000000Z/app_catalog.snapshot.jsonl"
        ),
        rows=[
            {"appid": 10, "last_modified": 1, "name": "Ten", "price_change_number": None},
            {"appid": 20, "last_modified": 2, "name": "Twenty", "price_change_number": None},
        ],
    )

    manifest = shared_artifact_contract.build_app_catalog_latest_manifest(summary)

    assert manifest["job_name"] == "app-catalog-weekly"
    assert manifest["status"] == "completed"
    assert manifest["snapshot_complete"] is True
    assert manifest["artifacts"] == [
        {
            "artifact_id": "app_catalog_latest_summary",
            "content_type": "application/json",
            "object_key": "steam/authority/app_catalog/latest.summary.json",
            "required_for": ["tracked_universe_catalog_filter", "observability"],
        },
        {
            "artifact_id": "app_catalog_snapshot",
            "content_type": "application/x-ndjson",
            "object_key": (
                "steam/authority/jobs/app-catalog-weekly/runs/"
                "20260422T030000000000Z/app_catalog.snapshot.jsonl"
            ),
            "required_for": ["tracked_universe_catalog_filter"],
        },
    ]
