"""S3-compatible publish and local cache/replay helpers for latest shared snapshots."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from steam.ingest import (
    app_catalog_latest_summary,
    shared_artifact_contract,
    shared_artifact_replay,
)
from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
)

DEFAULT_CACHE_ROOT = Path("tmp/steam/shared_cache")
DEFAULT_APP_CATALOG_SUMMARY_PATH = (
    app_catalog_latest_summary.DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _local_object_path(*, root: Path, object_key: str) -> Path:
    normalized_key = object_key.strip()
    if not normalized_key:
        raise ValueError("object_key is empty")
    return root / Path(normalized_key)


def _write_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def publish_job_run_to_object_store(
    *,
    client: S3CompatibleObjectStoreClient,
    run_dir: Path,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish one cadence run and its latest manifest to the shared bucket."""

    manifest = shared_artifact_contract.build_latest_job_manifest(result)
    for artifact in manifest["artifacts"]:
        source_path = run_dir / str(artifact["file_name"])
        if not source_path.exists():
            raise ValueError(f"Required shared artifact missing: {source_path}")
        client.put_bytes(
            object_key=str(artifact["object_key"]),
            payload=source_path.read_bytes(),
            content_type=str(artifact["content_type"]),
        )

    client.put_json(object_key=str(manifest["manifest_key"]), payload=manifest)
    return manifest


def publish_job_run_from_result_path(
    *,
    client: S3CompatibleObjectStoreClient,
    run_dir: Path,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Publish one cadence run from its existing local retained-artifact directory."""

    resolved_result_path = result_path or run_dir / "result.json"
    return publish_job_run_to_object_store(
        client=client,
        run_dir=run_dir,
        result=_read_json(resolved_result_path),
    )


def publish_app_catalog_latest_summary_to_object_store(
    *,
    client: S3CompatibleObjectStoreClient,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish the existing App Catalog latest-summary entrypoint and snapshot."""

    manifest = shared_artifact_contract.build_app_catalog_latest_manifest(summary)
    client.put_json(
        object_key=shared_artifact_contract.build_app_catalog_latest_summary_key(),
        payload=summary,
    )
    snapshot_key = shared_artifact_replay.resolve_shared_app_catalog_snapshot_object_key(summary)
    snapshot_path_value = summary.get("snapshot_path")
    if snapshot_key is not None and isinstance(snapshot_path_value, str):
        snapshot_path = Path(snapshot_path_value)
        if not snapshot_path.exists():
            raise ValueError(f"Required shared artifact missing: {snapshot_path}")
        client.put_bytes(
            object_key=snapshot_key,
            payload=snapshot_path.read_bytes(),
            content_type="application/x-ndjson",
        )
    return manifest


def publish_app_catalog_latest_summary_from_path(
    *,
    client: S3CompatibleObjectStoreClient,
    summary_path: Path = DEFAULT_APP_CATALOG_SUMMARY_PATH,
) -> dict[str, Any]:
    """Publish the current App Catalog latest summary from disk."""

    return publish_app_catalog_latest_summary_to_object_store(
        client=client,
        summary=_read_json(summary_path),
    )


def download_latest_job_snapshot_to_cache(
    *,
    client: S3CompatibleObjectStoreClient,
    cache_root: Path,
    job_name: str,
) -> dict[str, Any]:
    """Download one cadence latest manifest and its declared artifacts into cache."""

    manifest_key = shared_artifact_contract.build_latest_manifest_key(job_name)
    manifest_bytes = client.get_bytes(object_key=manifest_key)
    manifest_path = _write_bytes(
        _local_object_path(root=cache_root, object_key=manifest_key),
        manifest_bytes,
    )
    manifest = _read_json(manifest_path)
    for artifact in manifest["artifacts"]:
        object_key = str(artifact["object_key"])
        payload = client.get_bytes(object_key=object_key)
        _write_bytes(_local_object_path(root=cache_root, object_key=object_key), payload)
    return manifest


def download_app_catalog_latest_summary_to_cache(
    *,
    client: S3CompatibleObjectStoreClient,
    cache_root: Path,
) -> dict[str, Any]:
    """Download the existing App Catalog latest-summary entrypoint into cache."""

    summary_key = shared_artifact_contract.build_app_catalog_latest_summary_key()
    summary_bytes = client.get_bytes(object_key=summary_key)
    summary_path = _write_bytes(
        _local_object_path(root=cache_root, object_key=summary_key),
        summary_bytes,
    )
    summary = _read_json(summary_path)
    snapshot_key = shared_artifact_replay.resolve_shared_app_catalog_snapshot_object_key(summary)
    if snapshot_key is not None:
        payload = client.get_bytes(object_key=snapshot_key)
        _write_bytes(_local_object_path(root=cache_root, object_key=snapshot_key), payload)
    return summary


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for portable latest-snapshot publish/download."""

    parser = argparse.ArgumentParser(
        description=(
            "Publish or download portable latest evidence snapshots via "
            "S3-compatible storage"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish_job = subparsers.add_parser(
        "publish-job-run",
        help="Desktop authority: upload one cadence run plus latest manifest",
    )
    publish_job.add_argument("--run-dir", type=Path, required=True)
    publish_job.add_argument("--result-path", type=Path, default=None)

    publish_app_catalog = subparsers.add_parser(
        "publish-app-catalog-summary",
        help="Desktop authority: upload the App Catalog latest summary and snapshot",
    )
    publish_app_catalog.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_APP_CATALOG_SUMMARY_PATH,
    )

    download_job = subparsers.add_parser(
        "download-job-latest",
        help="Macbook read-only: download one cadence latest manifest and artifacts into cache",
    )
    download_job.add_argument("job_name")
    download_job.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)

    download_app_catalog = subparsers.add_parser(
        "download-app-catalog-summary",
        help="Macbook read-only: download the App Catalog latest summary and snapshot into cache",
    )
    download_app_catalog.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    return parser


def run(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """Execute one CLI command and return its stable summary payload."""

    args = build_parser().parse_args(argv)
    client = S3CompatibleObjectStoreClient(S3CompatibleObjectStoreConfig.from_env())

    if args.command == "publish-job-run":
        manifest = publish_job_run_from_result_path(
            client=client,
            run_dir=args.run_dir,
            result_path=args.result_path,
        )
        return {
            "command": args.command,
            "job_name": manifest["job_name"],
            "manifest_key": manifest["manifest_key"],
            "artifact_count": len(manifest["artifacts"]),
        }

    if args.command == "publish-app-catalog-summary":
        manifest = publish_app_catalog_latest_summary_from_path(
            client=client,
            summary_path=args.summary_path,
        )
        snapshot_key = shared_artifact_replay.resolve_shared_app_catalog_snapshot_object_key(
            _read_json(args.summary_path)
        )
        return {
            "command": args.command,
            "job_name": manifest["job_name"],
            "summary_key": shared_artifact_contract.build_app_catalog_latest_summary_key(),
            "snapshot_key": snapshot_key,
        }

    if args.command == "download-job-latest":
        manifest = download_latest_job_snapshot_to_cache(
            client=client,
            cache_root=args.cache_root,
            job_name=args.job_name,
        )
        return {
            "command": args.command,
            "job_name": manifest["job_name"],
            "cache_root": str(args.cache_root),
            "artifact_count": len(manifest["artifacts"]),
        }

    summary = download_app_catalog_latest_summary_to_cache(
        client=client,
        cache_root=args.cache_root,
    )
    return {
        "command": args.command,
        "job_name": str(summary.get("job_name") or ""),
        "cache_root": str(args.cache_root),
        "snapshot_key": (
            shared_artifact_replay.resolve_shared_app_catalog_snapshot_object_key(summary)
        ),
    }


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for portable latest-snapshot publish/download."""

    result = run(argv)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
