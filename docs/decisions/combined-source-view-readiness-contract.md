# Combined Source View Readiness Contract

Status: current Combined blocked/readiness guardrail
Date: 2026-05-19 (KST)

Role: current `Combined` blocked/readiness guardrail, not a `Combined` implementation contract.

이 문서는 `Combined` source view가 구현 전까지 blocked/pending 상태로 남아야 하는 조건을 고정한다.

이 결정은 schema, API, runtime, loader, scheduler, web behavior, DB write, category-to-game trusted mapping, 또는 `Combined` semantics 구현 승인이 아니다.

현재 durable context는 `README.md`, `docs/source-inventory.md`, `docs/data-model-spec.md`, `docs/decisions/category-to-game-mapping-contract.md` 를 따른다.

목적은 trusted mapping과 serving semantics가 별도 승인될 때까지 `Combined` 를 blocked/pending 상태로 유지하는 것이다.

Updated by CATEGORY-MAPPING-COMBINED-SOURCE-VIEW-CONTRACT-001:

이 update는 docs/tests-only planning contract다.

- `Combined` API route, SQL serving view, web data surface, web fetch/hook, mapping coverage panel, product ranking, KPI, score, or recommendation behavior를 구현하지 않는다.
- Proposed future `Combined` row grain은 one row per `dim_game.canonical_game_id` 이다. 이는 future implementation gate의 proposed contract일 뿐이며 현재 API, SQL, web, runtime behavior가 아니다.
- Current Steam contracts must be compared as candidate inputs only. `srv_game_explore_period_metrics`, `/games/explore/overview`, latest CCU, latest price, latest reviews, and latest rankings may be reviewed as a candidate Steam source contract, but none is selected or implemented as the `Combined` source by this update.
- `GET /chzzk/category-game-mappings` and `srv_chzzk_category_game_mapping` are current trusted identity surfaces and may be referenced only as future gated identity input candidates for `Combined`.
- Chzzk viewer metrics are not merged into a `Combined` product table by this update. Chzzk observed fields remain bounded/category evidence and must not imply full live-list population, current unbounded viewers, Steam-equivalent Chzzk baseline, recommendation quality, ranking readiness, KPI readiness, or score semantics.
- Candidate, unresolved, rejected, `categoryType=GAME`, inferred mapping, guessed mapping, hidden fallback mapping, and synthetic joins remain invalid as `Combined` identity.

## Current Context

- `Combined` 는 web source tab에 존재하지만, 현재는 pending/blocked UI shell이다.
- `PendingSourcePanel` 은 `Combined` 를 준비 중인 source로 표시한다.
- Steam source view와 Chzzk source view는 현재 분리되어 있다.
- Chzzk category evidence는 observed source evidence이며 canonical game identity가 아니다.
- Candidate category-to-game evidence는 trusted mapping이 아니다.
- `categoryType=GAME` 은 Chzzk provider category type evidence일 뿐이며 canonical game relationship을 만들지 않는다.

## Blocked-State Rule

`Combined` 는 아래 readiness gates가 모두 별도 승인될 때까지 blocked/pending 상태로 남아야 한다.

- `candidate`, `unresolved`, `rejected` category-to-game evidence는 `Combined` row, KPI, ranking, sorting, game identity를 만들거나 보강하는 데 사용할 수 없다.
- `categoryType=GAME` 만으로는 `Combined` row, canonical game relationship, Steam-Chzzk mapping을 만들 수 없다.
- hidden inferred mapping, synthetic join, fallback mapping, guessed mapping은 허용하지 않는다.
- Trusted mapping과 serving semantics가 승인되기 전까지 `Combined` data semantics는 없다.

`srv_chzzk_category_game_mapping` 같은 internal read-only DB serving view contract는 단독으로 `Combined` readiness gate를 충족하지 않는다.

`GET /chzzk/category-game-mappings` API response shape도 trusted mapping identity rows만 노출하며, 단독으로 `Combined` readiness gate를 충족하지 않는다.

Future backend `Combined` should not need to call `GET /chzzk/category-game-mappings` internally when `srv_chzzk_category_game_mapping` is available as the DB serving view.

Web exposure, product serving behavior, ranking/KPI semantics, and `Combined` semantics remain separate Human Gate items.

## Readiness Gates

나중에 `Combined` 를 blocked/pending 상태 밖으로 옮기려면 아래 조건을 checklist 수준에서 모두 만족해야 한다.

- Trusted category-to-game mapping contract와 promotion rules가 승인되어야 한다.
- Serving semantics가 별도 승인되어야 한다.
- API response shape가 별도 승인되어야 한다.
- Untrusted Chzzk category evidence가 canonical game identity로 취급되지 않음을 증명하는 regression tests가 있어야 한다.
- Public/private evidence boundary가 유지되어야 한다.
- Human Gate approval이 필요하다.
- Implementation ticket은 관련 durable docs와 tests를 같은 slice에서 갱신해야 한다.

## Allowed While Blocked

`Combined` 가 blocked/pending 상태인 동안 허용되는 작업은 planning boundary에 한정한다.

- Public pending/blocked explanation
- Durable readiness checklist
- Read-only review 또는 planning-contract follow-up
- Separate Steam and Chzzk source views
- No `Combined` data semantics

## Explicit Non-Goals

이 문서는 아래 작업을 승인하거나 구현하지 않는다.

- `Combined` UI implementation
- `Combined` API 또는 response shape
- Schema, SQL, migration, DDL
- DB write, backfill, reingest, bootstrap
- Live fetch
- Category-to-game mapping implementation
- Automatic matching
- Trusted mapping usage
- Generalized provider abstraction
- `gold_stream_game_30m`
- `PendingSourcePanel` copy 또는 behavior change
- KPI formula, ranking/sort semantics, table grain, storage shape, UI field behavior

## Public/Private Boundary

Public docs에는 durable blocked-state/readiness contract만 남긴다.

Public docs에는 raw provider payload, row-level UGC, live title, thumbnail, channel display value, credential, private runtime path, local scheduler evidence, screenshot, scheduler XML/stdout, host/path detail, raw API response를 포함하지 않는다.

이 boundary를 바꾸거나 `Combined` semantics를 구현하려면 별도 approved implementation slice에서 Human Gate를 거치고, 관련 durable docs와 regression tests를 함께 갱신한다.
