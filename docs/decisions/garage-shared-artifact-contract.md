# Garage-backed Shared Artifact Contract

Status: accepted target direction, narrow contract slice  
Date: 2026-04-22 (KST)

This decision fixes the minimum shared retained-artifact contract for the
current dual-host workflow. It does not migrate the live runtime to Garage, does
not open a shared Postgres boundary, and does not change the current scheduler
or serving path.

## Goal

Allow the desktop authority host to publish a small retained-artifact subset to
an S3-compatible object boundary so that a Macbook checkout can reuse the same
evidence in read-only mode.

## Role Boundary

- Desktop authority host:
  - current writer of retained local artifacts under `tmp/steam/jobs/**`
  - only host allowed to publish/update the shared object view
- Macbook checkout:
  - read-only consumer of published objects
  - may reuse retained evidence for review, triage, and optional catalog-driven
    filtering
  - does not write scheduler/job artifacts back to the shared boundary

## Shared Artifact Inventory

The shared subset stays narrower than the full local run directory.

- `ccu-30m`
  - required:
    - `result.json`
    - `ccu.silver.jsonl`
  - why:
    - `result.json` is the latest run/observability anchor
    - `ccu.silver.jsonl` is the current retained partial-success probe input
- `daily`
  - required:
    - `result.json`
    - `reviews.silver.jsonl`
  - why:
    - `result.json` is the latest run/observability anchor
    - `reviews.silver.jsonl` is the current retained partial-success probe input
- `price-1h`
  - required:
    - `result.json`
  - why:
    - current shared read-only consumers do not require price bronze/silver/gold
      JSONL
- `app-catalog-weekly`
  - required:
    - run-scoped `result.json`
    - run-scoped `app_catalog.snapshot.jsonl`
    - global `latest.summary.json`
  - why:
    - `latest.summary.json` is the current optional consumer entrypoint
    - `app_catalog.snapshot.jsonl` is required only when the summary is
      `completed` and `pagination.have_more_results = false`

Explicitly not part of this slice:

- Postgres facts/views or shared DB access
- scheduler logs, step meta, lock files
- ranking payload JSON files
- bronze/gold artifacts that current read-only consumers do not need

## Object Key Rules

Bucket naming stays deployment-local. The portable contract starts at the object
key prefix.

- run-scoped retained artifact:
  - `steam/authority/jobs/{job_name}/runs/{run_id}/{filename}`
- latest manifest per cadence job:
  - `steam/authority/jobs/{job_name}/latest/manifest.json`
- App Catalog latest summary:
  - `steam/authority/app_catalog/latest.summary.json`

Rules:

- `job_name`, `run_id`, and `filename` are literal path segments and must not
  contain `/`.
- consumers should read latest state through the documented latest manifest or
  latest summary key first, then follow referenced run-scoped keys.
- object keys are S3-compatible and avoid provider-specific metadata features.

## Latest Manifest Shape

Cadence jobs expose one latest manifest with stable pointer fields:

```json
{
  "schema_version": "1.0",
  "boundary_mode": "desktop_write_macbook_read_only",
  "writer_role": "desktop_authority",
  "consumer_role": "macbook_read_only",
  "job_name": "ccu-30m",
  "run_id": "20260422T010203000000Z",
  "status": "partial_success",
  "finished_at_utc": "2026-04-22T01:32:03Z",
  "manifest_key": "steam/authority/jobs/ccu-30m/latest/manifest.json",
  "run_prefix": "steam/authority/jobs/ccu-30m/runs/20260422T010203000000Z",
  "artifacts": [
    {
      "artifact_id": "job_result",
      "file_name": "result.json",
      "content_type": "application/json",
      "object_key": "steam/authority/jobs/ccu-30m/runs/20260422T010203000000Z/result.json",
      "required_for": ["scheduler_latest", "observability", "retained_partial_success_probe"]
    }
  ]
}
```

Current required artifact sets are intentionally fixed by cadence:

- `ccu-30m`: `result.json`, `ccu.silver.jsonl`
- `daily`: `result.json`, `reviews.silver.jsonl`
- `price-1h`: `result.json`
- `app-catalog-weekly`: `result.json`, `app_catalog.snapshot.jsonl`

## Latest Summary Shape

App Catalog already has a current runtime summary contract in
`src/steam/ingest/app_catalog_latest_summary.py`. This slice keeps that payload
shape unchanged and reuses it as the read-only entrypoint.

Shared summary rule:

- publish the existing summary payload to
  `steam/authority/app_catalog/latest.summary.json`
- when the summary points to a cadence-run snapshot path such as
  `tmp/steam/jobs/app-catalog-weekly/{run_id}/app_catalog.snapshot.jsonl`,
  the shared snapshot key is
  `steam/authority/jobs/app-catalog-weekly/runs/{run_id}/app_catalog.snapshot.jsonl`
- current consumer trust rule stays the same:
  - only `status = completed` and `pagination.have_more_results = false`
    summaries may drive read-only catalog filtering

## Explicitly Deferred

- Live Garage deployment and host operating procedures
- Upload/sync job wiring from local paths to shared objects
- Macbook live DB access, write paths, or local scheduler writes
- Scheduler/orchestrator replacement
- Serving replacement or broader artifact inventory expansion
