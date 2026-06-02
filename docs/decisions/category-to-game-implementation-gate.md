# Category-To-Game Implementation Gate

상태: docs-only decision checkpoint (문서 전용 결정 체크포인트)
티켓: CATEGORY-MAPPING-IMPLEMENTATION-GATE-001
날짜: 2026-05-23 (KST)

이 문서는 category-to-game mapping 구현을 시작하기 전에 필요한 decision gate를 고정한다.
이 결정은 schema, API, runtime, DB, web, storage, serving, trusted mapping, automatic matching, 또는 `Combined` semantics 구현 승인이 아니다.

## Current Boundary Summary

- 현재 구현 baseline은 Steam 중심이며, Chzzk는 category-level observed evidence와 read-only `/chzzk/categories/overview` boundary로 제한된다.
- `/chzzk/categories/overview` 는 category-only observed evidence surface다. Steam mapping, canonical game identity, trusted mapping state, 또는 `Combined` field를 노출하지 않는다.
- `categoryType=GAME` 은 Chzzk provider category type evidence일 뿐이며 canonical game identity나 Steam-Chzzk mapping 근거가 아니다.
- `candidate`, `unresolved`, `rejected` 는 decision-level review evidence 상태다. 이 상태만으로 trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, 또는 `Combined` 를 만들 수 없다.
- Historical note: 이 checkpoint 작성 당시 `trusted` / `approved` 는 future Human Gate / promotion gate 용어로만 뒀다. 이후 `trusted`는 `chzzk_category_game_mapping.mapping_status`에만 구현됐고, `approved`는 여전히 future terminology다.
- `Combined` 는 trusted mapping, serving semantics, API response shape, regression expectations, Human Gate가 별도 승인될 때까지 blocked/pending 상태로 남는다.

## Existing Docs Reviewed

- `README.md`
- `docs/source-inventory.md`
- `docs/data-model-spec.md`
- `docs/data-governance.md`
- `docs/metrics-definitions.md`
- `docs/decisions/category-to-game-mapping-contract.md`
- `docs/decisions/category-to-game-storage-contract-planning.md`
- `docs/decisions/category-to-game-serving-contract-planning.md`
- `docs/decisions/category-to-game-implementation-surface-review.md`
- `docs/decisions/combined-source-view-readiness-contract.md`
- `docs/runbook/agent-workflow.md`
- `docs/ticket-template.md`

## Decision

- 구현 준비 상태(Implementation readiness): `conditional`
- 사유(Reason):
  - 기존 문서들에서 이미 candidate-only, trusted mapping, serving 및 `Combined` boundary(경계)를 정의하고 있다.
  - 실제 관측 데이터(real observed data) 기반의 candidate 작업은 여전히 현재 Chzzk category의 coverage 및 freshness에 대한 신뢰도에 의존한다.
  - 따라서 실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 최초의 구현은 아래 제안된 향후 `audit`를 통해 필수 질문에 대한 답변이 확보되기 전까지 시작할 수 없다.
- 필수 선행 작업(Required prior action):
  - 실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 구현을 진행하기 전에 `CHZZK-COVERAGE-FRESHNESS-AUDIT-001`이 필수적으로 요구된다.
  - docs-only planning, synthetic/public-safe test guardrails, 또는 실제 관측된 category 데이터를 사용하지 않는 non-runtime review notes에는 `CHZZK-COVERAGE-FRESHNESS-AUDIT-001`이 요구되지 않는다.
  - 이번 체크포인트 동안 `CHZZK-COVERAGE-FRESHNESS-AUDIT-001`에 해당하는 tracked repo doc 또는 ticket이 발견되지 않았으므로, 본 문서에서는 이를 기존에 승인된 ticket이 아닌 proposed future prerequisite audit로 취급한다.
- 다음 승인된 방향(Next approved direction):
  - 실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 모든 구현을 진행하기 전에, 제안된 `audit`를 개시해야 한다.
  - Candidate-only storage/review 방향은 결정 경계(decision-boundary) 수준에서 계획될 수 있으나, 최종 storage 선택 및 구현은 향후 Human Gate의 승인 뒤로 보류(deferred)된다.

## Storage / Review Workflow Gate

실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 향후 구현은, scoped audit 및 Human Gate 조건이 충족된 이후에 오직 candidate-only review boundary에서만 시작할 수 있다.

- Candidate-only boundary (후보 전용 경계):
  - Candidate evidence는 오직 검토 논의(review discussion)를 지원하는 용도로만 사용되어야 한다.
  - Candidate evidence를 trusted relation, hidden join, canonical identity 또는 serving의 진실 공급원(source of serving truth)으로 취급해서는 안 된다.
- Trusted mapping 사용 금지:
  - `candidate`, `unresolved` 및 `rejected` evidence는 trusted mapping이나 canonical game semantics를 구동할 수 없다.
  - `trusted` / `approved` 승격(promotion)은 향후 Human Gate에서만 사용하는 용어로 남겨둔다.
- 자동 매칭(Automatic matching) 금지:
  - `categoryType=GAME`, 이름 유사도, 정규화된 힌트(normalized hints) 또는 category evidence를 바탕으로 mapping을 자동 승격(auto-promote)해서는 안 된다.
  - 모호한 에일리어스(Ambiguous alias), 변경된 카테고리 이름(renamed category), 지역별 타이틀(regional title), 프랜차이즈 충돌(franchise collision) 및 동일 이름 충돌(same-name collision)은 추측된 매핑(guessed mappings)으로 처리하지 않고 반드시 검토 질문(review questions)으로 남겨두어야 한다.
- Serving semantics 적용 금지:
  - Candidate evidence가 `/chzzk/categories/overview`, 현재의 source views, API 응답의 의미, UI 표현, ranking/sorting/KPI 또는 기타 serving 동작을 변경해서는 안 된다.
- Combined semantics 적용 금지:
  - Candidate evidence가 `Combined` row, KPI, ranking, sorting, game identity 또는 relationship semantics를 생성하거나 보강(enrich)해서는 안 된다.

## Status Lifecycle Boundary

이 용어들은 결정 수준의 의미론(decision-level semantics)일 뿐이다. 구체적인 영속화된 값(persisted values), API 필드(API fields), UI 필드(UI fields) 또는 운영 워크플로(operational workflow)가 아니다.

- `candidate`: review 가능한 mapping 가능성이다. Trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, 또는 `Combined` 에 사용할 수 없다.
- `unresolved`: 판단에 필요한 ambiguity가 남아 있다. Guessed mapping, automatic matching, auto-promotion을 허용하지 않는다.
- `rejected`: 검토 결과 수용하지 않은 후보다. Rejected evidence도 trusted mapping으로 되살리지 않는다.
- `trusted` / `approved`: Historical note 기준으로 future Human Gate / promotion gate 용어였다. 이후 `trusted`는 `chzzk_category_game_mapping.mapping_status`에만 구현됐고, 이 checkpoint는 candidate-to-trusted promotion이나 `approved` state를 승인하지 않는다.

## Evidence Boundary

공개 문서(Public docs) 및 PR 텍스트에는 오직 정제된 증거 카테고리(sanitized evidence categories)만 기술할 수 있다.

허용되는 공개 카테고리(Allowed public categories):

- provider category identity category
- candidate canonical game reference category
- normalized comparison hint category
- ambiguity reason category
- reviewer/operator note category
- timestamp category

공개 문서 및 PR 텍스트에서 제외되는 항목(Excluded from public docs and PR text):

- real category/channel/display values (실제 카테고리/채널/디스플레이 값)
- live titles (라이브 타이틀)
- thumbnails (썸네일)
- raw provider payloads (원시 제공자 페이로드)
- raw API responses (원시 API 응답)
- screenshots (스크린샷)
- credentials (자격 증명)
- `.env` values (`.env` 값)
- private paths (비공개 경로)
- scheduler XML/stdout (스케줄러 XML/표준 출력)
- local runtime logs (로컬 런타임 로그)
- raw Grafana/Prometheus responses (원시 Grafana/Prometheus 응답)
- row-level UGC (행 레벨 사용자 생성 콘텐츠)

## Proposed Audit Questions

`CHZZK-COVERAGE-FRESHNESS-AUDIT-001`은 실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 구현을 진행하기 전에 다음 질문들에 대해 답해야 한다.

- 커버리지/신선도 (Coverage/freshness):
  - candidate 검토를 위해 현재 Chzzk category의 coverage 및 freshness를 판단할 수 있는 tracked public-safe evidence가 충분한가?
  - coverage gaps, stale windows, missing category evidence, skipped evidence 및 bounded pagination caveat(제한된 페이지네이션 경고)들이 충분히 가시화되어 있어서, candidate 검토가 실제 존재하는 것보다 더 강력한 데이터 완전성(data completeness)을 내포하지 않도록 보장하는가?
- 카테고리 안정성 (Category stability):
  - 관측된 카테고리의 identity/type/name 시그널이 canonical game identity를 내포하지 않고 오직 candidate-only review를 수행하기에 충분히 안정적인가?
  - 제안된 모든 candidate-review 사용 사례에서 `categoryType=GAME`이 오직 provider category evidence로만 유지되는가?
- 경고 보존 (Caveat preservation):
  - 제안된 모든 candidate-review 입력 전반에서 bounded sample, bucket coverage, missing evidence 및 failure/skip caveat들이 유실 없이 보존되는가?
  - candidate 검토가 전체 live-list completeness, pagination exhaustion(페이지네이션 소진) 또는 caveat이 없는 1d/7d semantics를 보장한다고 잘못 주장할 위험이 있는가?
- 공개/비공개 안전성 (Public/private safety):
  - candidate review evidence가 오직 정제된 증거 카테고리(sanitized evidence categories)만을 사용하여 표현될 수 있는가?
  - 원시/비공개 자료(raw/private materials)가 공개 문서, PR 텍스트, fixture, API/UI semantics 및 영구적인 결정 기록(durable decision records)에 포함되지 않도록 차단되고 있는가?
- Serving 분리 (Serving separation):
  - `/chzzk/categories/overview`가 category-only observed evidence로 계속 유지되는가?
  - candidate evidence를 trusted mapping, canonical game semantics, ranking/sorting/KPI, serving semantics 또는 `Combined`에 실수로 사용하게 만들 우려가 있는 제안된 경로가 존재하는가?

본 체크포인트는 `audit`를 실행하지 않으며, 이러한 질문에 대한 답변을 주장하지 않는다.

## Later Implementation Ticket Boundary

향후의 구현 티켓(later implementation ticket)은 다음 작업을 수행할 수 있다 (may):

- 실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 경우, scoped audit 및 Human Gate 승인이 완료된 이후에 한하여 candidate-only review/storage 동작을 추가할 수 있다.
- candidate evidence를 신뢰할 수 없는 상태(untrusted)로 유지하고, 현재의 serving 및 `Combined` surface로부터 분리할 수 있다.
- 신뢰할 수 없는 category evidence가 canonical game identity나 trusted mapping으로 변질될 수 없음을 증명하는 regression test를 추가할 수 있다.
- 구현으로 인해 schema/API/data semantics가 변경되는 경우, 동일한 슬라이스(slice) 내에서 영구 문서(durable docs)를 업데이트할 수 있다.

향후의 구현 티켓은 별도의 Human Gate 승인 없이는 다음 항목들을 구현할 수 없다 (may not):

- trusted mapping 사용
- 자동 매칭(automatic matching)
- 승격/강등(promotion/demotion) 구현
- serving semantics
- API endpoint 또는 response shape 변경
- 웹 UI 동작, route, copy, table, sort/filter/search 또는 표현(presentation) 변경
- candidate evidence를 기반으로 한 ranking/sorting/KPI semantics
- `Combined` semantics, API, UI, KPI, ranking, sorting 또는 관계 해석(relationship interpretation)
- live fetch, 스케줄러 변경(scheduler mutation), runtime DB write, backfill, reingest 또는 bootstrap
- 일반화된 제공자 추상화(generalized provider abstraction)

## Regression / Test Expectations For Later Slices

향후의 모든 구현 슬라이스(implementation slice)는 다음을 증명하는 집중적인 regression coverage를 반드시 포함해야 한다:

- `categoryType=GAME`이 canonical game identity가 되지 않음.
- `candidate`, `unresolved` 및 `rejected`가 trusted mapping, canonical game semantics, ranking/sorting/KPI, serving semantics 또는 `Combined`를 구동하지 않음.
- Trusted mapping 사용에는 별도의 Human Gate가 필요하며 candidate evidence로부터 유추될 수 없음.
- 별도의 serving contract가 승인되지 않는 한, 현재의 `/chzzk/categories/overview`는 category-only로 유지됨.
- 공개/비공개 증거 경계(Public/private evidence boundaries)가 계속 강제됨.

## Explicit Deferred Human Gate Items

다음 항목들은 향후 Human Gate의 대상으로 남으며, 본 체크포인트에서는 승인되지 않는다:

- 최종 storage 선택
- 최종 schema/API/data semantics
- 실제 관측된 Chzzk category 데이터를 사용하는 candidate storage/review 구현
- 승격/강등(promotion/demotion) 규칙
- trusted mapping 사용
- 자동 매칭(automatic matching)
- serving semantics
- API/web 동작 변경
- `Combined` semantics
- runtime, scheduler, DB, backfill, reingest 또는 live fetch 동작

## Next-Step Recommendation

- 권장되는 후속 조치: 실제 관측된 Chzzk category 데이터를 사용하여 category-to-game candidate를 seed, store, prioritize 또는 review하는 구현을 진행하기 전에, 제안된 `CHZZK-COVERAGE-FRESHNESS-AUDIT-001`을 개시한다.
- 중단 조건(Stop condition): 본 체크포인트 단독으로는 mapping storage, trusted mapping, serving, API/web 또는 `Combined` 구현을 시작하지 않는다.
