from __future__ import annotations

import json
from pathlib import Path

import pytest

from steam.ingest import app_catalog_latest_summary, shared_artifact_replay


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_publish_and_reread_shared_artifacts_local_smoke(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared-prefix"
    ccu_run_dir = tmp_path / "authority" / "jobs" / "ccu-30m" / "20260422T010203000000Z"
    job_result = {
        "job_name": "ccu-30m",
        "run_id": "20260422T010203000000Z",
        "status": "partial_success",
        "finished_at_utc": "2026-04-22T01:32:03Z",
        "paths": {"run_dir": str(ccu_run_dir)},
    }
    ccu_rows = [
        {
            "steam_appid": 730,
            "player_count": 123456,
        }
    ]
    _write_json(ccu_run_dir / "result.json", job_result)
    _write_jsonl(ccu_run_dir / "ccu.silver.jsonl", ccu_rows)

    job_manifest = shared_artifact_replay.publish_job_run_artifacts(
        shared_root=shared_root,
        run_dir=ccu_run_dir,
        result=job_result,
    )
    replayed_job_manifest = shared_artifact_replay.read_shared_latest_job_manifest(
        shared_root=shared_root,
        job_name="ccu-30m",
    )
    assert replayed_job_manifest == job_manifest

    replayed_result = shared_artifact_replay.read_shared_json_object(
        shared_root=shared_root,
        object_key=job_manifest["artifacts"][0]["object_key"],
    )
    replayed_ccu_rows = shared_artifact_replay.read_shared_jsonl_rows(
        shared_root=shared_root,
        object_key=job_manifest["artifacts"][1]["object_key"],
    )
    assert replayed_result == job_result
    assert replayed_ccu_rows == ccu_rows

    snapshot_path = (
        tmp_path
        / "authority"
        / "jobs"
        / "app-catalog-weekly"
        / "20260422T030000000000Z"
        / "app_catalog.snapshot.jsonl"
    )
    app_catalog_rows = [
        {"appid": 10, "last_modified": 1, "name": "Ten", "price_change_number": None},
        {"appid": 20, "last_modified": 2, "name": "Twenty", "price_change_number": None},
    ]
    _write_jsonl(snapshot_path, app_catalog_rows)

    latest_summary = app_catalog_latest_summary.build_latest_summary(
        job_name="fetch_app_catalog_weekly",
        started_at_utc="2026-04-22T03:00:00Z",
        finished_at_utc="2026-04-22T03:05:00Z",
        snapshot_path=snapshot_path,
        rows=app_catalog_rows,
    )
    catalog_manifest = shared_artifact_replay.publish_app_catalog_latest_summary(
        shared_root=shared_root,
        summary=latest_summary,
    )
    replayed_summary = shared_artifact_replay.read_shared_app_catalog_latest_summary(
        shared_root=shared_root
    )

    assert replayed_summary == latest_summary
    assert catalog_manifest["snapshot_complete"] is True

    snapshot_key = shared_artifact_replay.resolve_shared_app_catalog_snapshot_object_key(
        replayed_summary
    )
    assert snapshot_key == (
        "steam/authority/jobs/app-catalog-weekly/runs/"
        "20260422T030000000000Z/app_catalog.snapshot.jsonl"
    )
    assert (
        shared_artifact_replay.read_shared_jsonl_rows(
            shared_root=shared_root,
            object_key=snapshot_key,
        )
        == app_catalog_rows
    )


def test_publish_job_run_artifacts_requires_declared_run_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "authority" / "jobs" / "ccu-30m" / "20260422T010203000000Z"
    _write_json(
        run_dir / "result.json",
        {
            "job_name": "ccu-30m",
            "run_id": "20260422T010203000000Z",
            "status": "partial_success",
            "finished_at_utc": "2026-04-22T01:32:03Z",
        },
    )

    with pytest.raises(ValueError, match="ccu.silver.jsonl"):
        shared_artifact_replay.publish_job_run_artifacts(
            shared_root=tmp_path / "shared-prefix",
            run_dir=run_dir,
            result={
                "job_name": "ccu-30m",
                "run_id": "20260422T010203000000Z",
                "status": "partial_success",
                "finished_at_utc": "2026-04-22T01:32:03Z",
            },
        )
