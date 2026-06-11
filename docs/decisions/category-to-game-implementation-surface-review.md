# Category-To-Game Implementation Surface Review

Status: read-only review
Ticket: REVIEW-C2G-IMPLEMENTATION-SURFACE-001
Date: 2026-05-19 (KST)

Role: 구현 가능성이 있는 surface에 대한 historical read-only review. 이 문서는 current implemented contract source가 아니며, current public summary는 `docs/decisions/category-to-game-mapping-contract.md`를 사용한다.

이 문서는 category-to-game 후보 구현을 열기 전에, future slice가 검토할 가능성이 높은 repo surface를 정리하는 read-only review다.

이 문서는 schema, SQL, migration, API, runtime, DB write, web behavior, candidate-to-trusted promotion, product serving usage, 또는 `Combined` semantics를 승인하지 않는다.
목적은 current repo boundary를 기준으로 touchpoint와 Human Gate를 식별하는 데 한정한다.

## Current Durable Boundaries

- `README.md` 기준 current baseline은 Steam-only runtime이며, Chzzk는 category-level observed facts와 read-only `/chzzk/categories/overview` source API로 제한된다.
- `docs/source-inventory.md` 와 `docs/data-model-spec.md` 는 Chzzk category evidence를 category-only observed source-view로 해석한다. `categoryType=GAME` 은 Chzzk provider category type evidence이며 canonical game identity가 아니다.
- `docs/decisions/category-to-game-mapping-contract.md` 의 `Current Implemented Contract Summary` 는 canonical current public contract summary다. `candidate`, `unresolved`, `rejected` evidence는 trusted mapping, canonical game semantics, serving semantics, `Combined` KPI에 쓸 수 없다.
- `docs/decisions/combined-source-view-readiness-contract.md` 는 trusted mapping과 serving semantics가 별도 승인될 때까지 `Combined` 를 blocked/pending 상태로 유지한다.
- Public docs에는 durable contract만 남긴다. raw provider payload, credentials, private runtime detail, row-level UGC, raw API response는 public boundary 밖이다.

## Likely Future Storage / Schema Touchpoints

향후 implementation planning에서는 현재 canonical storage surface와 provider-specific storage surface를 검토해야 할 수 있다.

- `dim_game`: 현재 canonical game boundary다.
- `game_external_id`: 현재 external identity boundary다. 현재 runtime usage는 Steam 중심이며, 이 review는 `game_external_id`를 변경하지 않는다.
- `fact_chzzk_category_30m`: 현재 Chzzk category observed fact surface다.
- `fact_chzzk_category_channel_30m`: nullable channel-derived evidence를 위한 현재 optional observed category-channel fact surface다.
- 이 boundary를 설명하는 durable docs: `docs/data-model-spec.md`, `docs/source-inventory.md`, 위에서 언급한 두 decision contract다.

이들은 review surface일 뿐이다. 이 문서는 최종 table shape, table grain, column name, status value, metadata shape, DDL, migration 순서, storage policy, write-path behavior를 정의하지 않는다.

## Likely Future API / Serving Touchpoints

- `/chzzk/categories/overview`는 현재 read-only Chzzk category overview endpoint다.
- `src/api/routers/chzzk.py`와 `src/api/services/chzzk_service.py`는 현재 Chzzk serving touchpoint다.
- 현재 `/chzzk/categories/overview` serving은 category-only observed evidence다. 별도 `GET /chzzk/category-game-mappings` API는 trusted mapping identity row만 노출하며 product serving이나 `Combined` field를 열지 않는다.
- 향후 planning에서는 Human Gate 승인 후 새로운 serving contract가 필요한지 검토해야 할 수 있다.

이 review는 새로운 endpoint, response shape, query parameter, sorting rule, ranking rule, KPI formula, API compatibility policy를 정의하지 않는다.

## Likely Future Web / UI Touchpoints

- `Combined`는 source tab으로 존재하지만, current durable contract는 이를 blocked/pending 상태로 유지한다.
- `PendingSourcePanel`은 현재 pending `Combined` 상태를 나타낸다.
- `ChzzkCategoryTable`은 현재 Chzzk category overview API의 category-only observed evidence를 렌더링한다.
- `web/src/api/chzzk.ts`, `web/src/hooks/useChzzkCategoryOverview.ts`, `web/src/lib/chzzkCategoryViewModel.ts`는 current Chzzk source view에 인접한 web data-flow surface다.

이들은 review surface일 뿐이다. 이 문서는 copy 변경, route 변경, UI behavior, table column, sort behavior, row identity, `Combined` view behavior, 최종 presentation detail을 제안하지 않는다.

## Likely Future Tests And Durable Docs

향후 implementation planning에는 trusted semantics를 사용하기 전에 regression coverage와 durable docs가 포함되어야 한다.
검토할 가능성이 높은 test category는 다음과 같다.

- `categoryType=GAME`은 canonical game identity로 취급하지 않는다.
- `candidate`, `unresolved`, `rejected` evidence는 `Combined`, canonical game semantics, ranking, sorting, trusted mapping에 사용할 수 없다.
- Product serving이나 `Combined`에서 trusted mapping을 사용하는 것은 별도 gate가 승인된 후에만 가능하다.
- Chzzk category serving은 별도 serving contract가 승인될 때까지 category-only로 유지된다.
- Public/private evidence boundary를 계속 강제한다.

현재 관련 test surface에는 `/chzzk/categories/overview` API test, Chzzk fact boundary 관련 SQL test, Chzzk source view와 `Combined` pending 상태 관련 web test가 포함된다.
이 PR은 test를 추가하거나 수정하지 않는다.

## Human Gate / Risk

이 영역은 high-risk semantics와 맞닿아 있으므로 향후 implementation work에는 Human Gate가 필요하다.

- canonical game identity와 external identity mapping에 관련된 schema/API/data semantics
- category-to-game trusted mapping과 promotion rule
- `Combined` semantics, ranking, sorting, KPI 해석
- public/private evidence 처리

이 review는 docs-only이고 read-only이므로 execution risk가 낮다. 이 문서는 implementation semantics를 승인하지 않는다.

## Recommended Future Atomic Slices

다음 항목은 proposal일 뿐 approval이 아니다.

- Storage contract planning: schema를 변경하지 않고 category-to-game candidate와 trusted semantics가 어디에 위치할 수 있는지 검토한다.
- API/serving semantics contract: endpoint나 response shape를 구현하지 않고 serving surface가 존재해야 하는지 정의한다.
- Test guardrail planning: untrusted evidence, `categoryType=GAME`, trusted mapping gate, blocked `Combined` behavior에 대한 regression tests를 명시한다.
- Public docs contract update: semantics가 승인된 후에만 durable docs를 업데이트한다.
- Implementation slice: Human Gate 승인 후 관련 contract와 regression 기대 사항이 명확해진 경우에만 연다.

각 proposal은 atomic하게 유지해야 한다. 어떤 항목도 이 review의 implementation instruction으로 취급해서는 안 된다.

## Explicit Non-Goals

- schema/SQL/migration/DDL 변경 없음.
- `game_external_id` 수정 없음.
- DB write/backfill/reingest/bootstrap 없음.
- API response shape 변경 없음.
- web behavior 변경 없음.
- category-to-game mapping 구현 없음.
- Product serving이나 `Combined`에서 trusted mapping 사용 없음.
- automatic matching 없음.
- `Combined` source view 구현 없음.
- generalized provider abstraction 없음.
- runtime/scheduler/write-path 변경 없음.
- local docs/checkpoint/NEXT cleanup 없음.

## Public / Private Boundary

Public docs는 보존해야 할 review 결과와 high-level future touchpoint를 설명할 수 있다.

Public docs에는 raw provider payload, credentials, private runtime detail, host/path detail, scheduler XML/stdout, row-level UGC, live title, thumbnail, channel display value, screenshot, raw API response를 포함해서는 안 된다.

Category evidence를 trusted mapping, canonical game semantics, API serving semantics, `Combined` semantics로 승격하는 모든 향후 변경에는 Human Gate를 거친 별도의 approved implementation slice가 필요하다.
