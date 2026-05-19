# Category-To-Game Implementation Surface Review

Status: read-only review
Ticket: REVIEW-C2G-IMPLEMENTATION-SURFACE-001
Date: 2026-05-19 (KST)

이 문서는 category-to-game 후보 구현을 열기 전에, future slice가 검토할 가능성이 높은 repo surface를 정리하는 read-only review다.

이 문서는 schema, SQL, migration, API, runtime, DB write, web behavior, category-to-game mapping implementation, trusted mapping usage, 또는 `Combined` semantics를 승인하지 않는다.
목적은 current repo boundary를 기준으로 touchpoint와 Human Gate를 식별하는 데 한정한다.

## Current Durable Boundaries

- `README.md` 기준 current baseline은 Steam-only runtime이며, Chzzk는 category-level observed facts와 read-only `/chzzk/categories/overview` source API로 제한된다.
- `docs/source-inventory.md` 와 `docs/data-model-spec.md` 는 Chzzk category evidence를 category-only observed source-view로 해석한다. `categoryType=GAME` 은 Chzzk provider category type evidence이며 canonical game identity가 아니다.
- `docs/decisions/category-to-game-mapping-contract.md` 는 category-to-game mapping을 planning boundary로만 둔다. `candidate`, `unresolved`, `rejected` evidence는 trusted mapping, canonical game semantics, serving semantics, `Combined` KPI에 쓸 수 없다.
- `docs/decisions/combined-source-view-readiness-contract.md` 는 trusted mapping과 serving semantics가 별도 승인될 때까지 `Combined` 를 blocked/pending 상태로 유지한다.
- Public docs에는 durable contract만 남긴다. raw provider payload, credentials, private runtime detail, row-level UGC, raw API response는 public boundary 밖이다.

## Likely Future Storage / Schema Touchpoints

Future implementation planning may need to review the current canonical and provider-specific storage surfaces:

- `dim_game`: current canonical game boundary.
- `game_external_id`: current external identity boundary. Current runtime usage is Steam-oriented, and this review does not change `game_external_id`.
- `fact_chzzk_category_30m`: current Chzzk category observed fact surface.
- `fact_chzzk_category_channel_30m`: current optional observed category-channel fact surface for nullable channel-derived evidence.
- Durable docs that describe these boundaries: `docs/data-model-spec.md`, `docs/source-inventory.md`, and the two decision contracts named above.

These are review surfaces only. This document does not define final table shape, table grain, column names, status values, metadata shape, DDL, migration order, storage policy, or write-path behavior.

## Likely Future API / Serving Touchpoints

- `/chzzk/categories/overview` is the current read-only Chzzk category overview endpoint.
- `src/api/routers/chzzk.py` and `src/api/services/chzzk_service.py` are the current Chzzk serving touchpoints.
- Current Chzzk serving is category-only observed evidence. It does not expose Steam mapping, canonical game identity, trusted mapping state, or `Combined` fields.
- Future planning may need to review whether any new serving contract is required after Human Gate approval.

This review does not define a new endpoint, response shape, query parameter, sorting rule, ranking rule, KPI formula, or API compatibility policy.

## Likely Future Web / UI Touchpoints

- `Combined` exists as a source tab, but current durable contract keeps it blocked/pending.
- `PendingSourcePanel` currently represents the pending `Combined` state.
- `ChzzkCategoryTable` currently renders category-only observed evidence from the Chzzk category overview API.
- `web/src/api/chzzk.ts`, `web/src/hooks/useChzzkCategoryOverview.ts`, and `web/src/lib/chzzkCategoryViewModel.ts` are adjacent web data-flow surfaces for the current Chzzk source view.

These are review surfaces only. This document does not propose copy changes, route changes, UI behavior, table columns, sort behavior, row identity, `Combined` view behavior, or final presentation details.

## Likely Future Tests And Durable Docs

Future implementation planning should include regression coverage and durable docs before any trusted semantics are used.
Likely test categories include:

- `categoryType=GAME` is not treated as canonical game identity.
- `candidate`, `unresolved`, and `rejected` evidence cannot power `Combined`, canonical game semantics, ranking, sorting, or trusted mapping.
- Trusted mapping usage occurs only after a separately approved gate.
- Chzzk category serving remains category-only until a separate serving contract is approved.
- Public/private evidence boundary remains enforced.

Current relevant test surfaces include API tests for `/chzzk/categories/overview`, SQL tests around Chzzk fact boundaries, and web tests around Chzzk source view and `Combined` pending state.
This PR does not add or modify tests.

## Human Gate / Risk

Human Gate is required for future implementation work because this area touches high-risk semantics:

- schema/API/data semantics around canonical game identity and external identity mapping
- category-to-game trusted mapping and promotion rules
- `Combined` semantics, ranking, sorting, and KPI interpretation
- public/private evidence handling

This review has low execution risk because it is docs-only and read-only. It does not approve implementation semantics.

## Recommended Future Atomic Slices

The following are proposals only, not approvals:

- Storage contract planning: review where category-to-game candidate and trusted semantics could live, without changing schema.
- API/serving semantics contract: define whether any serving surface should exist, without implementing an endpoint or response shape.
- Test guardrail planning: specify regression tests for untrusted evidence, `categoryType=GAME`, trusted mapping gate, and blocked `Combined` behavior.
- Public docs contract update: update durable docs only after the semantics are approved.
- Implementation slice: open only after Human Gate approval and after the relevant contract and regression expectations are explicit.

Each proposal should remain atomic. None of these items should be treated as implementation instruction from this review.

## Explicit Non-Goals

- No schema / SQL / migration / DDL changes.
- No `game_external_id` modification.
- No DB write / backfill / reingest / bootstrap.
- No API response shape change.
- No web behavior change.
- No category-to-game mapping implementation.
- No trusted mapping usage.
- No automatic matching.
- No `Combined` source view implementation.
- No generalized provider abstraction.
- No runtime/scheduler/write-path changes.
- No local docs/checkpoint/NEXT cleanup.

## Public / Private Boundary

Public docs may describe durable review findings and high-level future touchpoints.

Public docs must not include raw provider payload, credentials, private runtime detail, host/path detail, scheduler XML/stdout, row-level UGC, live title, thumbnail, channel display values, screenshots, or raw API responses.

Any future change that promotes category evidence into trusted mapping, canonical game semantics, API serving semantics, or `Combined` semantics requires a separate approved implementation slice with Human Gate.
