# Category-To-Game Storage Contract Planning

Status: docs-only planning boundary with implemented candidate-only foundation note
Ticket: PLAN-C2G-STORAGE-CONTRACT-001
Date: 2026-05-23 (KST)

Updated by CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001: `trusted`는 `chzzk_category_game_mapping.mapping_status`에만 저장되는 값이다. `chzzk_category_game_candidate.status`, API/UI state, serving exposure에는 사용하지 않는다.

이 문서는 category-to-game 후보 evidence를 나중에 어디에 둘 수 있는지 비교하는 planning contract다.

이 결정은 schema, SQL, migration, API, runtime, loader, scheduler, web behavior, DB write, backfill, reingest, automatic matching, trusted mapping usage, 또는 `Combined` semantics 구현 승인이 아니다.

`CATEGORY-MAPPING-CANDIDATE-STORAGE-001` 이후 repo에는 `chzzk_category_game_candidate` candidate-only storage foundation이 있다.

이 foundation은 provider-specific review 후보 저장소이며 trusted mapping, automatic matching, API field, UI field, serving semantics, `Combined`, promotion/demotion workflow, or operational workflow를 정의하지 않는다.

Trusted mapping storage shape, promotion workflow, serving shape, API/UI exposure, and `Combined` semantics는 아직 선택하지 않는다.

이 문서는 JSON shape, trusted mapping metadata, API field, UI field, or operational workflow를 정의하지 않는다.

Historical note: 위 설명은 원래 2026-05-23 planning boundary를 설명한다. 이후 CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001은 trusted storage table shape만 `chzzk_category_game_mapping`으로 선택했다. promotion workflow, trusted insert, serving shape, API/UI exposure, `Combined` semantics는 계속 deferred 상태다.

현재 durable context는 `docs/data-governance.md`, `docs/data-model-spec.md`, `docs/source-inventory.md`, `docs/decisions/category-to-game-mapping-contract.md`, `docs/decisions/category-to-game-implementation-surface-review.md`, `docs/decisions/combined-source-view-readiness-contract.md` 를 따른다.

## Current Boundary

- Steam-only는 현재 구현된 runtime baseline이다.
- Chzzk는 category-level observed evidence와 read-only source API/source view 범위에 남아 있다.
- Chzzk category evidence는 canonical game identity가 아니다.
- `categoryType=GAME`은 provider category type evidence일 뿐이며, Steam 또는 canonical mapping evidence가 아니다.
- `candidate`, `unresolved`, `rejected`evidence는 trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, `Combined`에 사용할 수 없다.
- `trusted` / `approved` 는 후속 Human Gate / promotion gate 용어로만 남긴다. 이 문서는 이를 persisted state, schema value, API field, UI field, runtime behavior로 정의하지 않는다.
- Updated by CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001: `trusted`는 `chzzk_category_game_mapping.mapping_status`에만 저장되는 값이다. `chzzk_category_game_candidate.status`, API/UI state, serving exposure에는 사용하지 않는다. `approved`는 여전히 future terminology다.
- `Combined`는 별도 trusted mapping gate와 serving semantics gate가 승인될 때까지 blocked/pending 상태로 남긴다.
- `chzzk_category_game_candidate` stores only untrusted review candidates. `game_external_id`를 변경하지 않으며, 현재 API/web/source-view path에서도 읽지 않는다.

## Implemented Trusted Storage Contract

`CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001`은 trusted storage DDL/contract만 추가함:

- table: `chzzk_category_game_mapping`
- grain/key: `chzzk_category_id` 하나당 trusted mapping 1개
- `canonical_game_id`는 `dim_game(canonical_game_id)`를 참조한다.
- `mapping_status`는 `trusted`로 제한한다.
- `source_kind`는 필수이며 빈 값일 수 없다.
- provenance fields: `reviewed_by`, `reviewed_at`, `created_at`, `updated_at`

이 update는 trusted mapping을 insert하지 않고, 현재 local candidate를 promotion하지 않으며, API/web/product serving behavior 또는 `Combined` behavior를 노출하지 않는다.

## Implemented Internal DB Serving View Contract

`CATEGORY-MAPPING-TRUSTED-MAPPING-SERVING-VIEW-001`은 internal read-only SQL serving view / DB query contract만 추가함:

- view: `srv_chzzk_category_game_mapping`
- grain: trusted `chzzk_category_game_mapping.chzzk_category_id` 하나당 1 row
- trusted source: `mapping_status = 'trusted'` 로 filter한 `chzzk_category_game_mapping`
- canonical identity: `dim_game.canonical_game_id`, `dim_game.canonical_name`
- nullable observed context: `chzzk_category_id`별 `latest fact_chzzk_category_30m row`

이 PR은 internal read-only DB serving view contract만 추가한다.

API exposure, web exposure, product serving behavior, `Combined` semantics는 추가하지 않는다.

이 view는 `chzzk_category_game_candidate`, `game_external_id`, `tracked_game`, tracked_universe, App Catalog surface를 읽지 않는다.

`reviewed_by`, raw manual-hint evidence, candidate status, row-level private evidence도 노출하지 않는다.

## Candidate Storage Directions

아래 방향들은 future implementation ticket이 검토할 수 있는 storage candidates다.

이 문서는 어떤 방향도 final choice로 선택하거나 순위를 매기지 않는다.

### New Provider-Specific Candidate Table Direction

이 방향은 provider category evidence와 canonical game 후보 relation을 별도 candidate storage surface에 두는 접근이다.

이 문서는 새 table의 이름, grain, key, columns, status values, evidence shape, migration order를 정의하지 않는다.

- Canonical identity fit: canonical identity boundary와 candidate evidence boundary를 분리하기 쉽다. 다만 future implementation이 이 분리를 명확히 유지하지 않으면 candidate relation이 trusted mapping처럼 읽힐 위험이 있다.
- Reviewability: category evidence와 후보 판단 context를 review 대상으로 모으기 쉽다. Review surface가 생기더라도 그 자체는 approval, promotion, or trusted usage를 뜻하지 않아야 한다.
- Candidate state support: `candidate`, `unresolved`, `rejected` 같은 planning evidence states를 담는 방향을 검토하기 쉽다. 이 states는 trusted mapping이나 serving semantics에 사용할 수 없다.
- Evidence metadata support: provider category identity fields, candidate canonical game reference, normalized comparison hints, ambiguity reason category, reviewer/operator note category, timestamp category 같은 sanitized evidence categories를 분리해 검토하기 쉽다.
- Premature trusted semantics risk: 별도 storage가 생기면 downstream에서 join 가능한 mapping처럼 오해할 수 있다. Future implementation은 serving/query boundaries and tests로 candidate-only semantics를 막아야 한다.
- Public/private boundary risk: public docs에는 durable meaning만 둘 수 있다. Raw provider payload, actual category/channel/display value, live title, thumbnail, row-level UGC, screenshot, raw API response, credential, private runtime evidence, host/path detail, scheduler XML/stdout, local docs, private operating detail은 public repo 밖에 둔다.
- Future implementation/migration complexity: 새 storage surface, migration, loader/reviewer path, regression tests, docs update가 필요할 수 있다. 그 complexity는 별도 Human Gate에서 승인되어야 한다.

### Existing `game_external_id` Extension Direction

이 방향은 existing external identity boundary인 `game_external_id` 쪽을 확장할 수 있는지 검토하는 접근이다.

현재 repo에서 `game_external_id` 는 Steam-oriented runtime usage를 갖고 있으며, 이 문서는 existing schema를 바꾸지 않는다.

- Canonical identity fit: existing canonical mapping surface와 가까워 future trusted mapping으로 이어질 때 migration path가 단순해질 수 있다. 반대로 candidate evidence가 canonical external ID mapping과 같은 surface에 있으면 untrusted evidence가 trusted identity처럼 읽힐 위험이 더 크다.
- Reviewability: existing identity boundary를 재사용하면 review 대상과 canonical mapping 대상이 가까워질 수 있다. Future design은 candidate-only rows or metadata가 serving joins에 섞이지 않도록 명확한 separation rule을 먼저 가져야 한다.
- Candidate state support: `candidate`, `unresolved`, `rejected` support를 추가하려면 current external identity semantics와 충돌하지 않는 metadata boundary가 필요하다. 이 문서는 status enum, nullable policy, or persisted metadata field를 정의하지 않는다.
- Evidence metadata support: sanitized evidence categories를 담을 수 있는 확장 여지는 future planning에서 검토할 수 있다. 다만 raw evidence, real provider values, or private review material을 public/runtime surface에 섞으면 안 된다.
- Premature trusted semantics risk: 가장 큰 risk는 existing serving/ingest paths가 `game_external_id` 를 canonical mapping boundary로 읽는다는 점이다. Candidate evidence가 이 surface에 들어가면 trusted usage gate and regression tests 없이는 serving semantics를 열 수 없다.
- Public/private boundary risk: external identity surface가 public docs and runtime semantics와 가깝기 때문에 public/private evidence filtering이 더 중요하다. Candidate review evidence는 sanitized 상태로 유지해야 하며, raw/private provider material을 노출하면 안 된다.
- Future implementation/migration complexity: existing schema, joins, ingest assumptions, service queries, and tests를 모두 검토해야 한다. 어떤 변경이든 별도 implementation ticket, durable docs, regression tests, Human Gate approval이 필요하다.

### Docs/File-Based Review Queue Comparison Baseline

Docs/file-based review queue는 runtime storage direction이 아니라 비교 baseline으로만 언급한다.

이 문서는 이 방향을 recommended path로 제안하지 않고, file paths, file formats, operational workflow, queue mechanics, local/private process를 정의하지 않는다.

- Fit: runtime identity boundary를 건드리지 않는 대신, durable runtime contract와 멀리 떨어져 implementation-ready storage가 되지 않는다.
- Reviewability: low-risk comparison aid로 생각할 수 있지만, review mechanics or operator process를 이 문서에서 열지 않는다.
- Candidate state support: `candidate`, `unresolved`, `rejected` wording을 planning discussion에서 비교할 수는 있으나 persisted runtime state로 정의하지 않는다.
- Evidence metadata support: sanitized evidence categories를 논의하는 데는 도움이 될 수 있지만, raw/private evidence를 public repo로 옮기는 근거가 될 수 없다.
- Premature trusted semantics risk: runtime joins가 없다는 점은 risk를 낮출 수 있으나, docs에 적힌 후보가 approval처럼 읽히지 않도록 주의해야 한다.
- Future implementation/migration complexity: 후속 implementation에서도 storage, migration, test, serving boundary에 대한 실제 Human Gate decision이 필요하다.

## Sanitized Evidence Categories

후속 planning에서 아래 evidence category가 필요할 수 있다.

아래 항목은 category일 뿐이며, column name, JSON key, table grain, API field, UI field, example을 확정하지 않는다.

- provider category identity fields
- candidate canonical game reference
- normalized comparison hints
- ambiguity reason category
- reviewer/operator note category
- timestamp category

이 category들은 public docs에서 raw provider payload, actual category/channel/display value, live title, thumbnail, row-level UGC, screenshot, raw API response, credential, private runtime evidence, host/path detail, scheduler XML/stdout, local docs, private operating detail을 포함할 수 없다.

## Deferred Human Gate Items

아래 항목은 future Human Gate item으로 남기며, 이 planning contract에서 승인하지 않는다.

- trusted insert, promotion/demotion rules
- rejected/unresolved 재검토 rules
- non-empty storage validation을 넘는 source_kind allowed-value policy
- API fields, UI fields
- internal read-only DB serving view contract 밖에서의 trusted mapping usage
- automatic matching
- internal DB view contract 밖의 product serving semantics
- `Combined` serving semantics, ranking, sorting, KPI interpretation, API/UI behavior
- 추가 migration, loader, backfill, reingest, scheduler, runtime, DB write behavior

## Explicit Non-Goals

Historical note: 아래 original planning non-goals는 CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001 이전에 작성됐다. 그 이후 ticket은 chzzk_category_game_mapping SQL/DDL storage contract만 supersede한다. Trusted insert, promotion, API/web exposure, product serving behavior, Combined는 여전히 non-goal이다.

이번 slice에서는 아래 작업을 하지 않는다.

- schema, SQL, migration, DDL
- actual `game_external_id` schema 변경
- model, loader, runtime, scheduler, DB write, backfill, reingest, bootstrap, live fetch
- API endpoint, API response shape
- web UI behavior, table column, sort, filter, copy, view behavior
- automatic matching
- trusted mapping usage
- `trusted` / `approved` persisted state, schema value, API field, UI field
- `Combined` semantics, `Combined` API, `Combined` UI, ranking, sorting, KPI interpretation
- generalized provider abstraction
- local docs/checkpoint/NEXT cleanup

## Public Boundary

Public docs에는 durable planning constraint와 sanitized evidence category만 설명할 수 있다.

Public docs에는 raw provider payload, real category/channel/display value, live title, thumbnail, row-level UGC, screenshot, raw API response, credential, private runtime evidence, host/path detail, scheduler XML/stdout, local docs, private operating detail을 포함하지 않는다.

Category evidence를 trusted mapping, canonical game semantics, serving semantics, `Combined` semantics로 승격하는 모든 변경은 별도 승인된 implementation slice가 필요하다. 해당 slice에는 Human Gate, 관련 durable docs, regression tests가 함께 필요하다.
