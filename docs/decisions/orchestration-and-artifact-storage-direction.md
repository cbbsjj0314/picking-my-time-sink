# Orchestration and Artifact Storage Direction

Status: accepted target direction, docs-only
Date: 2026-04-19 (KST)

이 decision은 의도한 tooling target direction을 기록한다. 이 문서만으로 live Dagster runtime, Garage deployment, Docker Compose stack을 도입하거나 schema/API semantics를 변경하지 않는다.

## Decision

- 현재 thin scheduler/CLI operations baseline이 stable해진 이후 Dagster OSS를 target orchestration direction으로 채택한다.
- Garage를 target self-hosted object/artifact storage direction으로 채택한다.
- artifact/storage access는 S3-compatible contract를 우선하도록 설계한다.
- Dagster가 always-on orchestrator/service가 될 때 Docker Compose를 검토하되, 현재 Steam-only baseline의 immediate requirement로 두지 않는다.

## Context

현재 execution baseline은 여전히 Steam-only thin scheduler/CLI path다. cadence-aware jobs, no-overlap behavior, logs/results, smoke checks, runbook 기반 operation으로 구성된다. 이 baseline의 안정성이 검증되기 전에 무거운 DAG나 service deployment로 곧바로 넘어가서는 안 된다.

예상하는 operating topology는 여전히 작다. primary stateful storage는 desktop-hosted로 두고 desktop과 laptop 양쪽에서 compute를 실행할 수 있는 가능성을 열어 둔다. Host-specific operating detail은 local-only docs에 둔다.

## Why Dagster OSS Instead Of Airflow

다른 project에서 Airflow를 다룬 경험이 있다. Airflow의 DAG/task 중심 workflow model보다 Dagster의 asset-centric model이 이 project의 bronze/silver/gold data flow, lineage, materialization, freshness, partition, quality check 방향에 더 잘 맞는다고 판단했다. 따라서 current MVP는 단순한 operation path로 유지하면서, 다음 orchestration 단계에서는 Dagster OSS를 통해 새로운 걸 배우고 operator 경험을 얻는 방향을 선택한다.

Dagster는 의도한 promotion path에도 맞는다.

- 먼저 local development
- 다음으로 single-machine service operation
- service shape을 지속적으로 유지해야 할 때 Docker Compose deployment

Airflow는 여전히 known reference point지만, 이 repository의 다음 orchestration direction에서 더 이상 default target이 아니다.

## Why Garage Instead Of MinIO

프로젝트 초기 구상에서는 이전에 사용해 본 경험이 있고 무료로 self-hosting할 수 있다는 점 때문에 MinIO를 default object storage choice로 두었다. 이후 MinIO Community Edition의 update/maintenance 지속성 문제를 확인하면서 장기적인 target으로 적합한지 다시 검토했다.

Garage, SeaweedFS 같은 self-hosted alternative를 검토한 결과, 이 project에는 범용 distributed filesystem보다 작은 규모의 S3-compatible object/artifact store가 더 적합하다고 판단했다. Garage는 lightweight, self-contained, operator-friendly하며 일반 인터넷으로 연결된 multi-site operation을 주요 방향으로 삼으므로 현재 desktop-hosted primary storage와 dual-host compute assumption에 잘 맞는다.

SeaweedFS는 S3뿐 아니라 filesystem, filer, WebDAV, Hadoop integration, cloud tiering처럼 더 넓은 storage use case를 지원하지만, 현재 project가 필요한 object/artifact storage boundary에는 scope가 더 넓다고 판단했다.

MinIO와 SeaweedFS를 사용할 수 없는 제품으로 판단한 것은 아니다. 이 repository의 현재 요구와 운영 규모를 기준으로 Garage를 default object storage direction으로 선택한 것이다.

## Portability Rule

artifact/storage code는 S3-compatible contract를 우선해야 한다.

- bucket, prefix 기반 object layout
- standard object put/get/list behavior
- provider-specific feature 의존 최소화
- credentials는 environment/local configuration을 통해 주입하며 source file에는 절대 두지 않는다

이렇게 하면 artifact boundary를 다시 작성하지 않고도 향후 Amazon S3, SeaweedFS 같은 다른 S3-compatible storage로 migration하거나 XML API/HMAC interoperability를 통해 GCS로 옮길 가능성을 유지할 수 있다.

다만 S3-compatible하다는 사실만으로 migration이 자동으로 완료되는 것은 아니다. 실제 migration에서는 object copy와 검증뿐 아니라 credentials, permissions, bucket configuration을 target storage에 맞게 다시 구성해야 한다. 따라서 application code는 basic S3 object operation에만 의존하고 Garage-specific behavior에 대한 의존은 만들지 않는다.

## Docker Timing

현재 thin scheduler/CLI baseline에는 Docker가 필요하지 않다.

Dagster가 always-on orchestrator/service가 될 때 Docker Compose를 우선 검토한다. 특히 동일한 stack을 desktop, laptop environment에서 일관되게 실행해야 하는 경우다. Garage는 Docker 사용 여부와 관계없이 single-node service로 운영할 수 있다. 이 public decision에서는 해당 host-specific detail을 local operations notes에서 다루도록 한다.

## Adjacent Tool Boundaries

orchestration/storage decision은 좁은 범위를 유지해야 한다. Adjacent tools는 각각 다른 역할과 adoption trigger를 갖는다.

- Prometheus/Grafana는 현재 WSL2 scheduler activation이 완료된 뒤 다음으로 검토할 metrics observability candidate다. orchestration/storage를 대체하지 않는다.
- DuckDB는 우선 검토할 batch transform/rollup/recompute/backfill engine candidate다. Postgres serving/metadata state를 대체하지 않는다.
- dbt Core는 mart model, test, docs가 유용해질 만큼 fact/dim/mart SQL shape이 충분히 stable해질 때까지 기다려야 한다.
- Loki는 metrics observability 이후의 centralized logs observability candidate다. data governance layer가 아니다.
- historical OLAP query volume을 통해 Postgres가 bottleneck이라는 근거가 확인될 때까지 ClickHouse는 deferred 상태로 유지한다.

## Current Baseline Caveat

현재 runtime artifact flow는 local/private artifact 중심이며, Postgres는 Steam-only dashboard path에 필요한 facts/views를 serving한다. 이 decision은 Dagster, Garage, Docker Compose, S3-backed artifact, Parquet artifact exchange가 이미 live 상태라는 뜻이 아니다. Prometheus/Grafana, DuckDB, dbt Core, Loki, ClickHouse 역시 현재 live runtime dependency가 아니다.

## Explicitly Deferred

- Dagster project scaffold, jobs/assets, schedules, sensors, deployment service.
- Docker Compose를 이용한 서비스 구성/연동.
- Garage 설치, host-specific operating configuration.
- local/private runtime artifact에서 object storage로의 migration.
- cloud object storage 도입.
- Prometheus/Grafana, DuckDB, dbt Core, Loki, ClickHouse runtime wiring.
- schema/API/runtime behavior 변경 전반.
