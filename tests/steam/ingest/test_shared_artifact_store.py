from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

import pytest

from steam.ingest import app_catalog_latest_summary, shared_artifact_replay
from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
)
from steam.ingest.shared_artifact_store import (
    download_app_catalog_latest_summary_to_cache,
    download_latest_job_snapshot_to_cache,
    publish_app_catalog_latest_summary_to_object_store,
    publish_job_run_to_object_store,
)


class _FakeResponse:
    def __init__(self, body: bytes = b"") -> None:
        self.status = 200
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _build_fake_client(
    remote_objects: dict[str, bytes],
    seen_paths: list[str] | None = None,
) -> S3CompatibleObjectStoreClient:
    def fake_transport(request: Request, *, context: object) -> _FakeResponse:
        path = urlsplit(request.full_url).path.lstrip("/")
        if seen_paths is not None:
            seen_paths.append(path)
        if request.get_method() == "PUT":
            remote_objects[path] = request.data or b""
            return _FakeResponse()
        if request.get_method() == "GET":
            if path not in remote_objects:
                raise HTTPError(
                    request.full_url,
                    404,
                    "Not Found",
                    hdrs=None,
                    fp=None,
                )
            return _FakeResponse(remote_objects[path])
        raise AssertionError(f"Unexpected method: {request.get_method()}")

    return S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            endpoint_url="https://storage.example.test",
            bucket="portable-cache",
            region="test-region",
            access_key_id="test-access",
            secret_access_key="test-secret",
            key_prefix="operator/latest",
            use_path_style=True,
        ),
        transport=fake_transport,
    )


def test_publish_and_download_job_snapshot_round_trip(tmp_path: Path) -> None:
    remote_objects: dict[str, bytes] = {}
    client = _build_fake_client(remote_objects)

    shared_cache_root = tmp_path / "cache"
    run_dir = tmp_path / "authority" / "jobs" / "ccu-30m" / "20260422T010203000000Z"
    result = {
        "job_name": "ccu-30m",
        "run_id": "20260422T010203000000Z",
        "status": "partial_success",
        "finished_at_utc": "2026-04-22T01:32:03Z",
    }
    rows = [{"steam_appid": 730, "player_count": 123456}]
    _write_json(run_dir / "result.json", result)
    _write_jsonl(run_dir / "ccu.silver.jsonl", rows)

    manifest = publish_job_run_to_object_store(
        client=client,
        run_dir=run_dir,
        result=result,
    )
    cached_manifest = download_latest_job_snapshot_to_cache(
        client=client,
        cache_root=shared_cache_root,
        job_name="ccu-30m",
    )

    assert cached_manifest == manifest
    assert shared_artifact_replay.read_shared_latest_job_manifest(
        shared_root=shared_cache_root,
        job_name="ccu-30m",
    ) == manifest
    assert shared_artifact_replay.read_shared_json_object(
        shared_root=shared_cache_root,
        object_key=manifest["artifacts"][0]["object_key"],
    ) == result
    assert shared_artifact_replay.read_shared_jsonl_rows(
        shared_root=shared_cache_root,
        object_key=manifest["artifacts"][1]["object_key"],
    ) == rows


def test_publish_and_download_app_catalog_summary_round_trip(tmp_path: Path) -> None:
    remote_objects: dict[str, bytes] = {}
    client = _build_fake_client(remote_objects)
    shared_cache_root = tmp_path / "cache"

    snapshot_path = (
        tmp_path
        / "authority"
        / "jobs"
        / "app-catalog-weekly"
        / "20260422T030000000000Z"
        / "app_catalog.snapshot.jsonl"
    )
    rows = [
        {"appid": 10, "last_modified": 1, "name": "Ten", "price_change_number": None},
        {"appid": 20, "last_modified": 2, "name": "Twenty", "price_change_number": None},
    ]
    _write_jsonl(snapshot_path, rows)
    summary = app_catalog_latest_summary.build_latest_summary(
        job_name="fetch_app_catalog_weekly",
        started_at_utc="2026-04-22T03:00:00Z",
        finished_at_utc="2026-04-22T03:05:00Z",
        snapshot_path=snapshot_path,
        rows=rows,
    )

    publish_app_catalog_latest_summary_to_object_store(
        client=client,
        summary=summary,
    )
    cached_summary = download_app_catalog_latest_summary_to_cache(
        client=client,
        cache_root=shared_cache_root,
    )

    assert cached_summary == summary
    assert shared_artifact_replay.read_shared_app_catalog_latest_summary(
        shared_root=shared_cache_root,
    ) == summary
    snapshot_key = shared_artifact_replay.resolve_shared_app_catalog_snapshot_object_key(
        summary
    )
    assert snapshot_key is not None
    assert shared_artifact_replay.read_shared_jsonl_rows(
        shared_root=shared_cache_root,
        object_key=snapshot_key,
    ) == rows


def test_publish_job_run_to_object_store_requires_declared_artifact(tmp_path: Path) -> None:
    remote_objects: dict[str, bytes] = {}
    client = _build_fake_client(remote_objects)
    run_dir = tmp_path / "authority" / "jobs" / "daily" / "20260422T020304000000Z"
    result = {
        "job_name": "daily",
        "run_id": "20260422T020304000000Z",
        "status": "success",
        "finished_at_utc": "2026-04-22T02:33:04Z",
    }
    _write_json(run_dir / "result.json", result)

    with pytest.raises(ValueError, match="reviews.silver.jsonl"):
        publish_job_run_to_object_store(
            client=client,
            run_dir=run_dir,
            result=result,
        )


def test_remote_key_prefix_is_bucket_local_not_portable_manifest_shape(tmp_path: Path) -> None:
    remote_objects: dict[str, bytes] = {}
    seen_paths: list[str] = []
    client = _build_fake_client(remote_objects, seen_paths=seen_paths)

    run_dir = tmp_path / "authority" / "jobs" / "price-1h" / "20260422T040000000000Z"
    result = {
        "job_name": "price-1h",
        "run_id": "20260422T040000000000Z",
        "status": "success",
        "finished_at_utc": "2026-04-22T04:15:00Z",
    }
    _write_json(run_dir / "result.json", result)

    manifest = publish_job_run_to_object_store(
        client=client,
        run_dir=run_dir,
        result=result,
    )

    assert manifest["manifest_key"] == "steam/authority/jobs/price-1h/latest/manifest.json"
    assert manifest["artifacts"][0]["object_key"] == (
        "steam/authority/jobs/price-1h/runs/20260422T040000000000Z/result.json"
    )
    assert seen_paths == [
        "portable-cache/operator/latest/steam/authority/jobs/price-1h/runs/20260422T040000000000Z/result.json",
        "portable-cache/operator/latest/steam/authority/jobs/price-1h/latest/manifest.json",
    ]
