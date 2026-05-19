# Category-To-Game Storage Contract Planning

Status: docs-only planning boundary
Ticket: PLAN-C2G-STORAGE-CONTRACT-001
Date: 2026-05-19 (KST)

이 문서는 category-to-game 후보 evidence를 나중에 어디에 둘 수 있는지 비교하는 planning contract다.
이 결정은 schema, SQL, migration, API, runtime, loader, scheduler, web behavior, DB write, backfill, reingest, automatic matching, trusted mapping usage, 또는 `Combined` semantics 구현 승인이 아니다.

최종 storage shape는 아직 선택하지 않는다. 이 문서는 final table grain, column name, JSON shape, persisted status enum, API field, UI field, operational workflow를 정의하지 않는다.
최종 선택과 구현은 별도 Human Gate / implementation ticket으로 미룬다.

현재 durable context는 `docs/data-governance.md`, `docs/data-model-spec.md`, `docs/source-inventory.md`, `docs/decisions/category-to-game-mapping-contract.md`, `docs/decisions/category-to-game-implementation-surface-review.md`, `docs/decisions/combined-source-view-readiness-contract.md` 를 따른다.

## Current Boundary

- Steam-only remains the current implemented runtime baseline.
- Chzzk remains category-level observed evidence plus read-only source API/source view.
- Chzzk category evidence is not canonical game identity.
- `categoryType=GAME` is provider category type evidence, not Steam or canonical mapping evidence.
- `candidate`, `unresolved`, and `rejected` evidence cannot power trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, or `Combined`.
- `trusted` / `approved` remain future Human Gate / promotion gate terminology only. This document does not define them as persisted state, schema value, API field, UI field, or runtime behavior.
- `Combined` remains blocked/pending until separate trusted mapping and serving semantics gates are approved.

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
- Public/private boundary risk: public docs에는 durable meaning만 둘 수 있다. Raw provider payloads, actual category/channel/display values, live titles, thumbnails, row-level UGC, screenshots, raw API responses, credentials, private runtime evidence, host/path details, scheduler XML/stdout, local docs, and private operating details remain outside public repo.
- Future implementation/migration complexity: 새 storage surface, migration, loader/reviewer path, regression tests, docs update가 필요할 수 있다. 그 complexity는 별도 Human Gate에서 승인되어야 한다.

### Existing `game_external_id` Extension Direction

이 방향은 existing external identity boundary인 `game_external_id` 쪽을 확장할 수 있는지 검토하는 접근이다.
현재 repo에서 `game_external_id` 는 Steam-oriented runtime usage를 갖고 있으며, 이 문서는 existing schema를 바꾸지 않는다.

- Canonical identity fit: existing canonical mapping surface와 가까워 future trusted mapping으로 이어질 때 migration path가 단순해질 수 있다. 반대로 candidate evidence가 canonical external ID mapping과 같은 surface에 있으면 untrusted evidence가 trusted identity처럼 읽힐 위험이 더 크다.
- Reviewability: existing identity boundary를 재사용하면 review 대상과 canonical mapping 대상이 가까워질 수 있다. Future design은 candidate-only rows or metadata가 serving joins에 섞이지 않도록 명확한 separation rule을 먼저 가져야 한다.
- Candidate state support: `candidate`, `unresolved`, `rejected` support를 추가하려면 current external identity semantics와 충돌하지 않는 metadata boundary가 필요하다. 이 문서는 status enum, nullable policy, or persisted metadata field를 정의하지 않는다.
- Evidence metadata support: sanitized evidence categories를 담을 수 있는 확장 여지는 future planning에서 검토할 수 있다. 다만 raw evidence, real provider values, or private review material을 public/runtime surface에 섞으면 안 된다.
- Premature trusted semantics risk: 가장 큰 risk는 existing serving and ingest paths가 `game_external_id` 를 canonical mapping boundary로 읽는다는 점이다. Candidate evidence가 이 surface에 들어가면 trusted usage gate and regression tests 없이는 serving semantics를 열 수 없다.
- Public/private boundary risk: external identity surface가 public docs and runtime semantics와 가깝기 때문에 public/private evidence filtering이 더 중요하다. Candidate review evidence must stay sanitized and cannot expose raw/private provider material.
- Future implementation/migration complexity: existing schema, joins, ingest assumptions, service queries, and tests를 모두 검토해야 한다. Any change would require a separate implementation ticket, durable docs, regression tests, and Human Gate approval.

### Docs/File-Based Review Queue Comparison Baseline

Docs/file-based review queue는 runtime storage direction이 아니라 비교 baseline으로만 언급한다.
이 문서는 이 방향을 recommended path로 제안하지 않고, file paths, file formats, operational workflow, queue mechanics, local/private process를 정의하지 않는다.

- Fit: runtime identity boundary를 건드리지 않는 대신, durable runtime contract와 멀리 떨어져 implementation-ready storage가 되지 않는다.
- Reviewability: low-risk comparison aid로 생각할 수 있지만, review mechanics or operator process를 이 문서에서 열지 않는다.
- Candidate state support: `candidate`, `unresolved`, `rejected` wording을 planning discussion에서 비교할 수는 있으나 persisted runtime state로 정의하지 않는다.
- Evidence metadata support: sanitized evidence categories를 논의하는 데는 도움이 될 수 있지만, raw/private evidence를 public repo로 옮기는 근거가 될 수 없다.
- Premature trusted semantics risk: runtime joins가 없다는 점은 risk를 낮출 수 있으나, docs에 적힌 후보가 approval처럼 읽히지 않도록 주의해야 한다.
- Future implementation/migration complexity: later implementation still needs a real Human Gate decision for storage, migration, tests, and serving boundaries.

## Sanitized Evidence Categories

Future planning may need the following evidence categories. These are categories only, not column names, JSON keys, table grain, API fields, UI fields, or examples.

- provider category identity fields
- candidate canonical game reference
- normalized comparison hints
- ambiguity reason category
- reviewer/operator note category
- timestamp category

These categories cannot include raw provider payloads, actual category/channel/display values, live titles, thumbnails, row-level UGC, screenshots, raw API responses, credentials, private runtime evidence, host/path details, scheduler XML/stdout, local docs, or private operating details in public docs.

## Deferred Human Gate Items

The following remain future Human Gate items and are not approved by this planning contract:

- final storage selection
- final schema, table grain, column names, JSON shape, persisted status values, API fields, or UI fields
- promotion and demotion rules
- rejected/unresolved reconsideration rules
- trusted mapping usage
- automatic matching
- serving semantics
- `Combined` serving semantics, ranking, sorting, KPI interpretation, or API/UI behavior
- migration, loader, backfill, reingest, scheduler, runtime, or DB write behavior

## Explicit Non-Goals

이번 slice에서는 아래 작업을 하지 않는다.

- schema, SQL, migration, DDL
- modification of actual `game_external_id` schema
- model, loader, runtime, scheduler, DB write, backfill, reingest, bootstrap, live fetch
- API endpoint or API response shape
- web UI behavior, table column, sort, filter, copy, or view behavior
- automatic matching
- trusted mapping usage
- `trusted` / `approved` persisted state, schema value, API field, or UI field
- `Combined` semantics, `Combined` API, `Combined` UI, ranking, sorting, or KPI interpretation
- generalized provider abstraction
- local docs/checkpoint/NEXT cleanup

## Public Boundary

Public docs may describe durable planning constraints and sanitized evidence categories only.

Public docs must not include raw provider payloads, real category/channel/display values, live titles, thumbnails, row-level UGC, screenshots, raw API responses, credentials, private runtime evidence, host/path details, scheduler XML/stdout, local docs, or private operating details.

Any future change that promotes category evidence into trusted mapping, canonical game semantics, serving semantics, or `Combined` semantics requires a separate approved implementation slice with Human Gate, related durable docs, and regression tests.
