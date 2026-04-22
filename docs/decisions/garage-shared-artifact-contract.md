# Garage-backed Shared Artifact Contract

상태: accepted target direction, narrow contract slice  
날짜: 2026-04-22 (KST)

이 결정은 현재 dual-host workflow에서 필요한 최소 shared retained-artifact
contract를 고정한다. live runtime을 Garage로 옮기지 않고, shared Postgres
boundary를 열지 않으며, 현재 scheduler나 serving path도 바꾸지 않는다.

현재 local/operator 메모:

- 이번 slice의 current backing-store choice는 Cloudflare R2 Free다.
- 그래도 durable contract는 계속 S3-compatible이고, 이후 self-hosted
  fallback/migration 방향은 Garage로 유지한다.

## 목표

desktop authority host가 작은 retained-artifact subset을 S3-compatible object
boundary로 publish하고, Macbook checkout이 같은 evidence를 read-only로
재사용할 수 있게 한다.

## 역할 경계

- Desktop authority host:
  - `tmp/steam/jobs/**` 아래 current retained local artifacts의 writer
  - shared object view를 publish/update할 수 있는 유일한 host
- Macbook checkout:
  - published objects의 read-only consumer
  - review, triage, optional catalog-driven filtering 용도로 evidence 재사용 가능
  - scheduler/job artifacts를 shared boundary에 다시 쓰지 않음

## Shared Artifact Inventory

shared subset은 full local run directory보다 더 좁게 유지한다.

- `ccu-30m`
  - required:
    - `result.json`
    - `ccu.silver.jsonl`
  - 이유:
    - `result.json` 은 latest run/observability anchor다.
    - `ccu.silver.jsonl` 은 current retained partial-success probe input이다.
- `daily`
  - required:
    - `result.json`
    - `reviews.silver.jsonl`
  - 이유:
    - `result.json` 은 latest run/observability anchor다.
    - `reviews.silver.jsonl` 은 current retained partial-success probe input이다.
- `price-1h`
  - required:
    - `result.json`
  - 이유:
    - current shared read-only consumers는 price bronze/silver/gold JSONL이 필요 없다.
- `app-catalog-weekly`
  - required:
    - run-scoped `result.json`
    - run-scoped `app_catalog.snapshot.jsonl`
    - global `latest.summary.json`
  - 이유:
    - `latest.summary.json` 이 current optional consumer entrypoint다.
    - `app_catalog.snapshot.jsonl` 은 summary가 `completed` 이고
      `pagination.have_more_results = false` 일 때만 필요하다.

이번 slice에 명시적으로 포함하지 않는 것:

- Postgres facts/views 또는 shared DB access
- scheduler logs, step meta, lock files
- ranking payload JSON files
- current read-only consumers가 쓰지 않는 bronze/gold artifacts

## Object Key Rules

bucket naming은 deployment-local이다. portable contract는 object key prefix부터
시작한다.

- run-scoped retained artifact:
  - `steam/authority/jobs/{job_name}/runs/{run_id}/{filename}`
- latest manifest per cadence job:
  - `steam/authority/jobs/{job_name}/latest/manifest.json`
- App Catalog latest summary:
  - `steam/authority/app_catalog/latest.summary.json`

규칙:

- `job_name`, `run_id`, `filename` 은 literal path segment이며 `/` 를 포함하면 안 된다.
- consumer는 문서화된 latest manifest 또는 latest summary key를 먼저 읽고,
  그 다음 referenced run-scoped key를 따라간다.
- object key는 S3-compatible이어야 하며 provider-specific metadata 기능에 의존하지 않는다.
- bucket-local operator prefix는 portable `object_key` 바깥에 둘 수 있지만,
  published manifest/summary payload 안의 key shape는 위 규칙을 유지한다.

## Latest Manifest Shape

cadence job은 stable pointer field를 가진 latest manifest 1개를 노출한다:

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

현재 required artifact set은 cadence별로 의도적으로 고정한다:

- `ccu-30m`: `result.json`, `ccu.silver.jsonl`
- `daily`: `result.json`, `reviews.silver.jsonl`
- `price-1h`: `result.json`
- `app-catalog-weekly`: `result.json`, `app_catalog.snapshot.jsonl`

## Latest Summary Shape

App Catalog는 이미 `src/steam/ingest/app_catalog_latest_summary.py` 에 current
runtime summary contract가 있다. 이번 slice는 그 payload shape를 바꾸지 않고
read-only entrypoint로 그대로 재사용한다.

shared summary 규칙:

- existing summary payload를
  `steam/authority/app_catalog/latest.summary.json` 에 publish한다.
- summary가
  `tmp/steam/jobs/app-catalog-weekly/{run_id}/app_catalog.snapshot.jsonl`
  같은 cadence-run snapshot path를 가리키면, shared snapshot key는
  `steam/authority/jobs/app-catalog-weekly/runs/{run_id}/app_catalog.snapshot.jsonl`
  이다.
- current consumer trust rule은 그대로 유지한다:
  - `status = completed` 이고 `pagination.have_more_results = false` 인 summary만
    read-only catalog filtering에 쓸 수 있다.

## Explicitly Deferred

- Live Garage deployment와 host operating procedures
- local run completion 이후 scheduler-driven 또는 automatic publish wiring
- "latest few snapshots" 용 remote retention/pruning automation
- Macbook live DB access, write path, local scheduler write
- Scheduler/orchestrator replacement
- Serving replacement 또는 broader artifact inventory expansion
