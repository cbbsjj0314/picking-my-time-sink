# Orchestration and Artifact Storage Direction

Status: accepted target direction, docs-only
Date: 2026-04-18 (KST)

This decision documents the intended tool direction. It does not introduce a live
Dagster runtime, a Garage deployment, a Docker Compose stack, or any schema/API
semantic change.

## Decision

- Adopt Dagster OSS as the target orchestration direction after the current thin
  scheduler/CLI operations baseline is stable.
- Adopt Garage as the target self-hosted object/artifact storage direction.
- Design artifact and storage access around an S3-compatible contract first.
- Review Docker Compose when Dagster becomes an always-on orchestrator/service,
  not as an immediate requirement for the current Steam-only baseline.

## Context

The current execution baseline is still the Steam-only thin scheduler/CLI path:
cadence-aware jobs, no-overlap behavior, logs/results, smoke checks, and
runbook-backed operations. The project should not jump straight to a heavy DAG
or service deployment before that baseline is reliable.

The expected operating topology remains small: desktop-hosted primary stateful
storage with the possibility that both a desktop and a laptop can run compute.
Host-specific operating details belong in local-only docs.

## Why Dagster OSS Instead Of Airflow

Airflow experience already exists in this project context. Choosing Dagster OSS
creates a better learning and operator-experience opportunity for the next
orchestration step while still leaving the current MVP on a simple operational
path.

Dagster also fits the desired promotion path:

- local development first
- single-machine service operation next
- Docker Compose deployment once the service shape needs to stay up consistently

Airflow remains a known reference point, but it is no longer the default target
for this repository's next orchestration direction.

## Why Garage Instead Of MinIO

Garage is the target self-hosted object/artifact store because it is lightweight,
operator-friendly, and S3-compatible. That better matches the current
desktop-hosted primary storage and dual-host compute assumption than keeping
MinIO as the default choice.

MinIO is no longer the default object storage direction for this project.

## Portability Rule

Artifact and storage code should prefer an S3-compatible contract:

- bucket and prefix based object layout
- standard object put/get/list behavior
- minimal dependence on provider-specific features
- credentials injected through environment or local configuration, never source
  files

This keeps a later move to Amazon S3 or to GCS through XML API/HMAC
interoperability plausible without rewriting the artifact boundary.

## Docker Timing

Docker is not required for the current thin scheduler/CLI baseline.

Docker Compose should be considered first when Dagster becomes an always-on
orchestrator/service, especially if the same stack needs to run consistently on
both desktop and laptop environments. Garage can be operated as a single-node
service with or without Docker; this public decision intentionally leaves that
host-specific detail to local operations notes.

## Current Baseline Caveat

The current runtime artifact flow remains local/private artifact oriented, with
Postgres serving facts/views for the Steam-only dashboard path. This decision
does not claim that Dagster, Garage, Docker Compose, S3-backed artifacts, or
Parquet artifact exchange are already live.

## Explicitly Deferred

- Dagster project scaffold, jobs/assets, schedules, sensors, or deployment
  service.
- Docker Compose files and service wiring.
- Garage installation and host-specific operating configuration.
- Migration from local/private runtime artifacts to object storage.
- Cloud object storage adoption.
- Any schema, API, or runtime behavior change.
