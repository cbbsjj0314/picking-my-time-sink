# Category-To-Game Serving Contract Planning

Status: docs-only planning boundary
Ticket: PLAN-C2G-SERVING-CONTRACT-001
Date: 2026-05-19 (KST)

Role: historical candidate-serving guardrail이다. 이 문서는 canonical current trusted mapping API/view contract가 아니며, 현재 public summary는 `docs/decisions/category-to-game-mapping-contract.md`를 따른다.

이 문서는 category-to-game candidate evidence가 serving boundary를 넘지 않도록 고정하는 planning contract다. 이 결정은 schema, SQL, migration, API, runtime, loader, scheduler, web behavior, DB write, backfill, reingest, candidate-to-trusted promotion, product serving usage, ranking/sorting/KPI, 또는 `Combined` semantics 구현 승인이 아니다.

현재 durable context는 `docs/source-inventory.md`, `docs/data-model-spec.md`, `docs/data-governance.md`, `docs/decisions/category-to-game-mapping-contract.md`, `docs/decisions/category-to-game-implementation-surface-review.md`, `docs/decisions/category-to-game-storage-contract-planning.md`, `docs/decisions/combined-source-view-readiness-contract.md`를 따른다.

## Current Boundary Summary

- Steam-only은 현재 구현된 runtime baseline으로 유지된다.
- Chzzk는 category-level observed evidence와 read-only source API/source view로 유지된다.
- 현재 `/chzzk/categories/overview`는 category-only observed evidence로 유지된다.
- Chzzk category evidence는 canonical game identity가 아니다.
- `categoryType=GAME`은 provider category type evidence이며, Steam 또는 canonical mapping이 아니다.
- `candidate`, `unresolved`, `rejected` evidence는 trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI 또는 `Combined`의 근거로 사용할 수 없다.
- 당시 기록: 최초 planning에서는 `trusted` / `approved`를 향후 Human Gate / promotion gate terminology로만 두었다. 이후 storage work에서 `trusted`만 `chzzk_category_game_mapping.mapping_status`로 구현했으며, `approved`는 future terminology로 유지된다.
- trusted mapping, serving semantics, API response 구조, regression tests 및 Human Gate가 각각 별도로 승인될 때까지 `Combined`는 blocked/pending 상태로 유지된다.

## Candidate Serving Boundary

Candidate evidence는 향후 review planning에 활용할 수 있다. 이는 serving contract, trusted mapping contract, canonical identity contract, ranking contract, KPI contract 또는 `Combined` contract가 아니다.

candidate, unresolved, rejected evidence를 현재 source API, web source view, ranking/sorting/KPI 또는 `Combined`를 통해 trusted data로 노출해서는 안 된다. 또한 canonical game identity를 추론하거나, hidden join을 생성하거나, 현재 source view를 game-level evidence로 보강하거나, Human Gate를 대체하는 데 사용해서는 안 된다.

향후 candidate review serving surface가 필요하다면 별도의 Human Gate와 implementation ticket이 필요하다. 그 향후 작업은 구현 전에 자체 approval scope, durable docs, regression expectations, public/private evidence boundary를 정의해야 한다. 이 문서는 향후 endpoint path, response field, query params, UI fields, table grain, storage 구조, operational workflow, schema, runtime 동작을 정의하지 않는다.

## Explicit Non-Goals

이 planning contract는 다음을 승인하거나 구현하지 않는다:

- schema, SQL, migration, DDL
- `game_external_id` 변경
- DB write, backfill, reingest, bootstrap, loader 동작, live fetch
- API endpoint 구현, API response 구조, query params, API fields
- web UI 동작, 문구, table column, sort/filter/search 동작, UI fields, route, source-view 동작
- runtime, scheduler, live fetch, guarded-write, local/private 운영 동작
- candidate storage 구현
- trusted mapping의 product serving, `Combined` 사용
- 자동 matching
- promotion/demotion rule 구현
- `Combined` API, UI, data semantics, source-view semantics, ranking, sorting, KPI 해석
- category-to-game candidate evidence 기반 ranking/sorting/KPI semantics
- 일반화된 provider abstraction
- public/private boundary 약화

이 항목들은 serving boundary와 인접해 보이더라도 이 ticket의 범위 밖에 유지된다.

## Public / Private Safety Boundary

Public docs에는 durable planning constraints와 sanitized categories만 기술할 수 있다. Public docs에는 raw provider payloads, 실제 category/channel/display values, live titles, thumbnails, row-level UGC, screenshots, raw API responses, credentials, private runtime evidence, host/path 세부사항, scheduler XML/stdout, local docs, private 운영 세부사항을 포함해서는 안 된다.

개념이 필요하지만 public에 부적절하다면 추상화하거나 익명화해야 한다. Raw/private 자료는 public repo docs와 PR text 외부에 유지해야 한다.

## Deferred Human Gate Items

다음 항목은 향후 Human Gate item으로 유지되며 이 planning contract에서 승인되지 않았다:

- candidate review serving surface 결정
- endpoint, response, query, UI, route, presentation 구조
- trusted mapping의 product serving, `Combined` 사용
- promotion/demotion 규칙
- serving semantics
- `Combined` semantics
- ranking/sorting/KPI 동작
- schema/storage 구현

candidate, unresolved, rejected evidence를 trusted mapping, canonical game identity, serving semantics, ranking/sorting/KPI, `Combined`로 승격하는 향후 모든 변경에는 Human Gate, 관련 durable docs, regression tests를 포함한 별도의 approved implementation slice가 필요하다.

CATEGORY-MAPPING-PUBLIC-DOCS-CURRENT-CONTRACT-CLEANUP-001에 따라 update됨: `srv_chzzk_category_game_mapping`와 `GET /chzzk/category-game-mappings`는 현재 trusted identity surface다. 이 두 surface만으로 `Combined`를 개방하기에는 충분하지 않으며, DB serving view를 사용할 수 있는 경우 향후 backend `Combined`는 내부적으로 read-only API를 호출할 필요가 없어야 한다.
