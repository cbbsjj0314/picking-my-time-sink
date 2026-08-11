# Cloud Runtime Authority and Off-host Recovery Boundary

## Status

Status: proposed
Ticket / Spec: `CLOUD-RUNTIME-AUTHORITY-RECOVERY-ADR-001`

Fresh-context review and the Human Gate remain pending. This document does not
authorize runtime changes.

## Date

2026-08-12 (KST)

## Context

PMTS recurring collection currently depends on a personal Windows workstation,
its WSL2 environment, and Windows Task Scheduler. That arrangement has supported
the MVP, but it couples operational authority, persistent state, local evidence,
and workstation availability.

The project already has a narrow S3-compatible contract for selected retained
Steam artifacts. It does not cover PostgreSQL recovery, the full local run
directory, or a general remote filesystem. The proposed decision separates the
long-term operational authority from personal workstations while preserving that
portable object boundary.

Three states must remain distinct:

- Current runtime authority: Windows 11 Pro, Ubuntu WSL2, x86_64, and Windows
  Task Scheduler.
- Proposed target authority: a provider-portable x86_64 Linux cloud host.
- Cutover status: not performed.

## Current Runtime Evidence

The 2026-08-12 read-only audit is load-bearing evidence for this proposal:

- Task Scheduler has six PMTS tasks, four active. The active set includes the
  Steam 30-minute CCU, hourly price, and daily jobs, plus the recurring
  `ChzzkFetchLoadGuardedWrite30m` guarded-write job. Chzzk regular collection and
  guarded writes are therefore already an operational path, not an unopened
  future path.
- Active tasks use interactive logon, do not catch up missed schedules, do not
  retry failed jobs automatically, and ignore overlapping new instances. One
  missed `SteamDaily` run was observed. This evidence does not establish the
  cause of any broader low-collection interval.
- PostgreSQL is currently about 344 MB for 202 active Steam tracked games. The
  audit's roughly 3.27 MB/day growth and 1.54 GB one-year projection are simple
  estimates, not direct byte history; they exclude WAL, vacuum/bloat, schema
  changes, and tracked-universe growth.
- Historical jobs complete within minutes, but job-level peak CPU and RAM
  telemetry is unknown. No VM CPU, RAM, or disk figure is an accepted production
  requirement; pilot sizing remains to be measured.
- Local `tmp/` evidence is about 9.22 GB and was estimated to grow by about
  112 MB/day, materially faster than the database estimate. No automatic local
  retention or pruning was found.
- There is no automated PostgreSQL backup, restore test, confirmed current
  off-host database backup, Chzzk full off-host copy, or remote retention
  automation. Historical evidence includes one manual encrypted backup command
  validation, but that is not a recovery contract or restore validation.

The collectors and loaders can use remote PostgreSQL and run-local scratch, but
the runtime is not yet stateless or clean-ephemeral. Historical observability,
App Catalog resume/latest state, and same-host `fcntl`/`flock` overlap protection
remain local-state dependencies. ARM compatibility is not proven.

## Decision Drivers

- Remove personal workstation availability from the long-term operational
  authority boundary.
- Keep the first topology small enough for the current recurring workload while
  measuring resource requirements rather than inventing them.
- Preserve provider portability across x86_64 Linux compute choices.
- Put recovery responsibilities and deliberately retained evidence off-host
  without mirroring all scratch data.
- Keep current PMTS entrypoints usable during authority migration.
- Avoid coupling authority migration to an orchestration rewrite or hypothetical
  public-serving topology.

## Proposed Target Direction

Subject to review and Human Gate approval, PMTS should separate workstation use
from operational authority as follows:

- Personal Windows and Mac workstations serve development, review, SSH, and
  administration roles.
- A provider-portable x86_64 Linux cloud host serves as operational authority.
- The initial topology may colocate PostgreSQL, the existing PMTS
  collection/load runtime, and a thin Linux-native scheduler such as `systemd`
  timers on one small host.
- Local operational artifacts use bounded local retention once a separate
  retention contract defines it.
- PostgreSQL recovery backups and the existing selected retained-artifact subset
  may use an S3-compatible off-host boundary. Cloudflare R2 remains the current
  backing-store direction for that boundary.
- Compute, scheduler, database, and object access should avoid unnecessary
  provider-proprietary contracts.

This is a conceptual proposal. No cloud VM, migrated database, Linux scheduler,
backup automation, or authority cutover currently exists.

## Authority Boundary

The authority host owns recurring execution, scheduler state, overlap control,
write-capable database access, and authoritative operational health evidence.
Workstations may administer and inspect that host but are not concurrent
operational writers by default.

Authority migration must preserve the existing command entrypoints and job
semantics before any orchestration-engine change. Overlap protection, missed-run
behavior, retry behavior, credentials, observability evidence, and local state
dependencies require explicit Linux pilot verification; installing a timer is
not sufficient evidence of cutover readiness.

## Persistent / Bounded / Off-host State Boundary

| State class | Proposed responsibility |
| --- | --- |
| Persistent operational state | PostgreSQL facts, dimensions, mappings, and serving views remain authoritative database state. |
| Bounded local operational evidence | Run results, logs, silver evidence, Chzzk raw/derived/results, and observability evidence are retention candidates, not an indefinite local archive. Some point-in-time provider evidence cannot be fetched identically again. |
| Rebuildable state | Aggregate/serving projections that are demonstrably reproducible from retained authoritative inputs need not become independent recovery artifacts. |
| Disposable state | Locks, caches, and triage scratch remain local and disposable unless a later contract identifies a specific exception. |
| Off-host recovery state | PostgreSQL recovery backups become a separate responsibility to define in the backup/restore contract. |
| Off-host retained artifacts | Only the selected retained-artifact inventory governed by the existing S3-compatible contract is published. |

The proposal does not copy all of `tmp/` to object storage. Backup cadence,
format, RPO, RTO, retention periods, and restore procedures remain undefined
until the recovery and retention follow-up contracts pass their gates.

## Relationship to `garage-shared-artifact-contract.md`

This proposal does not replace
[`garage-shared-artifact-contract.md`](./garage-shared-artifact-contract.md).
Their relationship is explicit:

- Preserve:
  - the portable S3-compatible object boundary;
  - Cloudflare R2 as the current backing-store direction;
  - publication of a narrow selected retained-artifact subset instead of a full
    local run-directory mirror.
- Extend:
  - a later PostgreSQL recovery contract may add database backup responsibility
    to the off-host boundary;
  - this ADR does not define its format, cadence, RPO, RTO, retention, or restore
    procedure.
- Supersede for the proposed long-term topology:
  - the assumption that the desktop authority must remain the operational writer.
- Do not silently supersede:
  - the existing Steam selected-artifact inventory;
  - object key shapes, consumer semantics, or the narrow publish contract's
    retention semantics;
  - the deferral of automatic scheduler publish and remote retention automation.

PostgreSQL facts/views remain outside the shared retained-artifact inventory.
Future recovery backups are a distinct responsibility, not a reclassification
of the database as a shared consumer artifact.

## Considered Alternatives

1. Keep the current Windows workstation authority.
   - Lowest immediate migration effort, but retains interactive logon,
     workstation availability, no catch-up/retry baseline, and recovery coupling.
2. Move authority to a spare personal PC.
   - Can separate daily workstation use from execution, but still leaves power,
     network, physical-site, and off-host recovery concerns within a personal
     environment.
3. Use a provider-portable x86_64 Linux cloud authority.
   - Adds migration and operating responsibility, but directly separates
     authority from workstations and allows a small, measurable single-host
     pilot without making one compute provider a durable contract. This is the
     proposed direction.
4. Start with a managed-service-heavy cloud topology.
   - Could provide managed operational features, but introduces more services,
     cost, provider coupling, and migration surfaces than the current evidence
     requires. No current traffic, SLO, or measured capacity need justifies it.

## Consequences / Trade-offs

- Workstation outages would no longer be intended authority outages after a
  successful cutover.
- A single-host pilot remains a single-host failure domain; the off-host recovery
  contract and tested restore path are therefore prerequisites for cutover, not
  optional polish.
- Linux-native scheduling removes the Windows scheduler dependency only after
  behavior and operational evidence are reproduced and observed.
- Colocation keeps the initial topology small but couples database and collector
  resource contention. Pilot telemetry must validate or change the topology.
- S3 compatibility limits storage coupling, but does not eliminate provider
  credentials, permissions, bucket configuration, copy, and verification work.
- Local retention reduces uncontrolled artifact growth but requires a separate
  contract that protects irreplaceable evidence.

## Explicit Non-goals

- Creating cloud resources, migrating PostgreSQL, changing scheduler tasks, or
  implementing backup, restore, retention, or pruning automation.
- Selecting production VM sizing or claiming ARM compatibility.
- Mirroring all of `tmp/` or expanding the existing selected Steam artifact
  inventory, key shape, or consumer contract.
- Implementing Dagster or approving its adoption timing in this ticket;
  installing Dagster or Airflow; rewriting existing collectors or pipelines;
  or combining authority cutover with orchestration migration.
- Introducing managed PostgreSQL, Kubernetes, load balancers, queues,
  autoscaling, CDN, authentication, public deployment, or traffic sizing.
- Changing schema, API, product semantics, CI, credentials, or current runtime.

The existing
[`orchestration-and-artifact-storage-direction.md`](./orchestration-and-artifact-storage-direction.md)
decision remains in force: Dagster OSS is the accepted target orchestration
direction after a stable thin scheduler/CLI baseline, while Airflow is not the
current default target. This ADR does not supersede that decision or authorize
Dagster adoption timing or implementation. The initial Linux authority must
first validate the existing PMTS entrypoints with a thin Linux-native scheduler.
After a stable Linux authority baseline, a separate review should assess
readiness to adopt Dagster as the operational orchestration layer. Reopening
Airflow as the default would require a separate decision that explicitly
supersedes the existing orchestration decision.

## Migration / Rollout Boundary

A first pilot may use a small Google Cloud Compute Engine class Linux VM. After
the pilot, long-term compute may be reevaluated; an x86_64 Linux provider such as
Hetzner Cloud can be a candidate if later cost and operating evidence support it.
These are rollout examples, not architecture dependencies. The R2-backed
S3-compatible boundary can remain independent of the compute provider.

No production cutover opens before the pilot, recovery contract, and migration
rehearsal gates. Public Web/API serving is not a completion condition for the
authority migration.

## Follow-up Gates

The current evidence suggests this dependency order; it is not a permanent
roadmap:

1. PostgreSQL backup/restore and recovery contract.
2. Operational artifact retention contract.
3. PostgreSQL bootstrap and Linux reproducibility audit.
4. GCP/Linux authority pilot.
5. Database migration rehearsal plus backup/restore validation.
6. Operational authority cutover under a separate Human Gate.
7. Stable Linux authority observation.
8. Dagster adoption readiness review.
9. Public Web/API serving planning, only when explicitly opened.

Cutover and orchestration migration must remain separate. No scheduler, cloud,
database, or recovery implementation is authorized by this ADR.

## Revisit Triggers

Revisit this proposal when one of the following becomes concrete:

- pilot telemetry disproves a practical single-host topology;
- restore validation or recovery requirements require a different state layout;
- selected-artifact consumers require a reviewed inventory or semantics change;
- ARM compatibility is demonstrated and there is a reason to expand the target;
- stable Linux operation creates a grounded trigger for Dagster adoption
  readiness review;
- explicit public Web/API traffic, security, or SLO requirements require a
  separate serving architecture decision;
- provider constraints force a material dependency that conflicts with the
  portability boundary.
