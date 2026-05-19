# Category-To-Game Serving Contract Planning

Status: docs-only planning boundary
Ticket: PLAN-C2G-SERVING-CONTRACT-001
Date: 2026-05-19 (KST)

이 문서는 category-to-game candidate evidence가 serving boundary를 넘지 않도록 고정하는 planning contract다.
이 결정은 schema, SQL, migration, API, runtime, loader, scheduler, web behavior, DB write, backfill, reingest, trusted mapping usage, ranking/sorting/KPI, 또는 `Combined` semantics 구현 승인이 아니다.

현재 durable context는 `docs/source-inventory.md`, `docs/data-model-spec.md`, `docs/data-governance.md`, `docs/decisions/category-to-game-mapping-contract.md`, `docs/decisions/category-to-game-implementation-surface-review.md`, `docs/decisions/category-to-game-storage-contract-planning.md`, and `docs/decisions/combined-source-view-readiness-contract.md` 를 따른다.

## Current Boundary Summary

- Steam-only remains the current implemented runtime baseline.
- Chzzk remains category-level observed evidence plus read-only source API/source view.
- Current `/chzzk/categories/overview` remains category-only observed evidence.
- Chzzk category evidence is not canonical game identity.
- `categoryType=GAME` is provider category type evidence, not Steam or canonical mapping.
- `candidate`, `unresolved`, and `rejected` evidence cannot power trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, or `Combined`.
- `trusted` / `approved` remain future Human Gate / promotion gate terminology only. This document does not define them as persisted state, schema value, API field, UI field, runtime behavior, or serving behavior.
- `Combined` remains blocked/pending until trusted mapping, serving semantics, API response shape, regression tests, and Human Gate are separately approved.

## Candidate Serving Boundary

Candidate evidence may be useful for future review planning.
It is not a serving contract, trusted mapping contract, canonical identity contract, ranking contract, KPI contract, or `Combined` contract.

Candidate, unresolved, and rejected evidence must not be exposed through current source APIs, web source views, ranking/sorting/KPI, or `Combined` as trusted data.
They also must not be used to infer canonical game identity, create hidden joins, enrich current source views as game-level evidence, or substitute for a Human Gate.

If a future candidate review serving surface is needed, it requires a separate Human Gate and implementation ticket.
That future work must define its own approval scope, durable docs, regression expectations, and public/private evidence boundary before implementation.
This document does not define future endpoint paths, response fields, query params, UI fields, table grain, storage shape, operational workflow, schema, or runtime behavior.

## Explicit Non-Goals

This planning contract does not approve or implement:

- schema, SQL, migration, or DDL
- `game_external_id` modification
- DB write, backfill, reingest, bootstrap, loader behavior, or live fetch
- API endpoint implementation, API response shape, query params, or API fields
- web UI behavior, copy, table column, sort/filter/search behavior, UI fields, route, or source-view behavior
- runtime, scheduler, live fetch, guarded-write, or local/private operating behavior
- candidate storage implementation
- trusted mapping usage
- automatic matching
- promotion/demotion rule implementation
- `Combined` API, UI, data semantics, source-view semantics, ranking, sorting, or KPI interpretation
- ranking/sorting/KPI semantics from category-to-game candidate evidence
- generalized provider abstraction
- public/private boundary weakening

These items remain outside this ticket even if they appear adjacent to the serving boundary.

## Public / Private Safety Boundary

Public docs may describe durable planning constraints and sanitized categories only.
Public docs must not include raw provider payloads, real category/channel/display values, live titles, thumbnails, row-level UGC, screenshots, raw API responses, credentials, private runtime evidence, host/path details, scheduler XML/stdout, local docs, or private operating details.

If a concept is necessary but public-inappropriate, it must be abstracted or anonymized.
Raw/private material must stay outside public repo docs and PR text.

## Deferred Human Gate Items

The following remain future Human Gate items and are not approved by this planning contract:

- candidate review serving surface decision
- endpoint, response, query, UI, route, or presentation shape
- trusted mapping usage
- promotion/demotion rules
- serving semantics
- `Combined` semantics
- ranking/sorting/KPI behavior
- schema/storage implementation

Any future change that promotes candidate, unresolved, or rejected evidence into trusted mapping, canonical game identity, serving semantics, ranking/sorting/KPI, or `Combined` requires a separate approved implementation slice with Human Gate, related durable docs, and regression tests.
