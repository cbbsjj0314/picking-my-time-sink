"""Local/mock shared-artifact publish and replay helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from shutil import copy2
from typing import Any

from steam.ingest import shared_artifact_contract


def _shared_object_path(*, shared_root: Path, object_key: str) -> Path:
    normalized_key = object_key.strip()
    if not normalized_key:
        raise ValueError("object_key is empty")
    return shared_root / Path(normalized_key)


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _copy_required_artifact(
    *,
    shared_root: Path,
    source_path: Path,
    object_key: str,
) -> Path:
    if not source_path.exists():
        raise ValueError(f"Required shared artifact missing: {source_path}")

    target_path = _shared_object_path(shared_root=shared_root, object_key=object_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    copy2(source_path, target_path)
    return target_path


def publish_job_run_artifacts(
    *,
    shared_root: Path,
    run_dir: Path,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish one cadence run into a local/mock shared prefix."""

    manifest = shared_artifact_contract.build_latest_job_manifest(result)
    for artifact in manifest["artifacts"]:
        _copy_required_artifact(
            shared_root=shared_root,
            source_path=run_dir / str(artifact["file_name"]),
            object_key=str(artifact["object_key"]),
        )

    _write_json(
        _shared_object_path(shared_root=shared_root, object_key=str(manifest["manifest_key"])),
        manifest,
    )
    return manifest


def publish_app_catalog_latest_summary(
    *,
    shared_root: Path,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish the App Catalog latest-summary entrypoint into a local/shared prefix."""

    manifest = shared_artifact_contract.build_app_catalog_latest_manifest(summary)
    _write_json(
        _shared_object_path(
            shared_root=shared_root,
            object_key=shared_artifact_contract.build_app_catalog_latest_summary_key(),
        ),
        summary,
    )

    snapshot_key = resolve_shared_app_catalog_snapshot_object_key(summary)
    snapshot_path_value = summary.get("snapshot_path")
    if snapshot_key is not None and isinstance(snapshot_path_value, str):
        _copy_required_artifact(
            shared_root=shared_root,
            source_path=Path(snapshot_path_value),
            object_key=snapshot_key,
        )

    return manifest


def read_shared_latest_job_manifest(*, shared_root: Path, job_name: str) -> dict[str, Any]:
    """Read one published latest manifest from a local/mock shared prefix."""

    return _read_json(
        _shared_object_path(
            shared_root=shared_root,
            object_key=shared_artifact_contract.build_latest_manifest_key(job_name),
        )
    )


def read_shared_app_catalog_latest_summary(*, shared_root: Path) -> dict[str, Any]:
    """Read the published App Catalog latest-summary entrypoint."""

    return _read_json(
        _shared_object_path(
            shared_root=shared_root,
            object_key=shared_artifact_contract.build_app_catalog_latest_summary_key(),
        )
    )


def read_shared_json_object(*, shared_root: Path, object_key: str) -> dict[str, Any]:
    """Read one shared JSON object by object key."""

    return _read_json(_shared_object_path(shared_root=shared_root, object_key=object_key))


def read_shared_jsonl_rows(*, shared_root: Path, object_key: str) -> list[dict[str, Any]]:
    """Read one shared JSONL object by object key."""

    path = _shared_object_path(shared_root=shared_root, object_key=object_key)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            row = json.loads(payload)
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object at line {line_number} in {path}")
            rows.append(row)
    return rows


def resolve_shared_app_catalog_snapshot_object_key(summary: Mapping[str, Any]) -> str | None:
    """Resolve the shared snapshot key from the latest-summary entrypoint."""

    manifest = shared_artifact_contract.build_app_catalog_latest_manifest(summary)
    for artifact in manifest["artifacts"]:
        if artifact["artifact_id"] != "app_catalog_snapshot":
            continue
        if artifact["required_for"]:
            return str(artifact["object_key"])
        return None
    return None
