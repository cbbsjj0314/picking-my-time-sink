# Chzzk Coverage/Freshness Audit

상태: read-only audit
티켓: CHZZK-COVERAGE-FRESHNESS-AUDIT-001
날짜: 2026-05-23 (KST)

이 문서는 실제 관측된 Chzzk category 데이터를 category-to-game candidate 검토에 사용하기 전에, 현재 공개 가능하고 추적된 근거가 coverage/freshness 판단에 충분한지 점검한다.

이 audit는 raw/private 자료를 대상으로 실행하지 않았다. 또한 mapping implementation, candidate generation, mapping storage, trusted mapping, serving semantics, `Combined`, schema/API/runtime/DB/web 변경을 승인하지 않는다.

## 검토한 근거

확인한 tracked 문서와 test:

- `README.md`
- `docs/source-inventory.md`
- `docs/data-model-spec.md`
- `docs/data-governance.md`
- `docs/metrics-definitions.md`
- `docs/decisions/category-to-game-implementation-gate.md`
- `docs/decisions/category-to-game-mapping-contract.md`
- `docs/decisions/category-to-game-storage-contract-planning.md`
- `docs/decisions/category-to-game-serving-contract-planning.md`
- `docs/decisions/category-to-game-implementation-surface-review.md`
- `docs/decisions/combined-source-view-readiness-contract.md`
- `tests/api/test_chzzk_categories_overview.py`
- `tests/web/test_chzzk_source_view.py`
- `tests/docs/test_category_to_game_boundary_docs.py`

현재 checkout에 존재하는 것으로 확인된 local/sanitized 근거:

- `docs/local/NEXT.md`
- `docs/local/checkpoints/README.md`
- `docs/local/checkpoints/2026-05-14_chzzk-guarded-write-scheduler-24h-read-only-checkpoint.md`
- `docs/local/checkpoints/2026-05-15_chzzk-source-view-completion-boundary-refresh.md`
- `docs/local/checkpoints/2026-05-15_chzzk-api-aggregate-smoke-completion.md`
- `docs/local/checkpoints/2026-05-16_chzzk-guarded-write-scheduler-observation-rollup.md`

local evidence는 sanitized local/operator evidence category 수준으로만 사용했다. 이 audit 문서는 raw provider payload, raw API response, 실제 category/channel/display value, live title, thumbnail, credential, `.env` value, private path, scheduler XML/stdout, raw runtime log, screenshot, row-level UGC, 그리고 raw Grafana/Prometheus response를 공개 문서로 옮기지 않는다.

## Non-goals

이 audit는 아래 항목을 승인하거나 구현하지 않는다.

- schema, SQL, migration, DDL, `game_external_id` 변경, storage 구조
- category-to-game mapping implementation, candidate generation, automatic matching, promotion/demotion, trusted mapping, 그리고 `trusted` / `approved` runtime state
- API endpoint, response 구조, API field, UI field, route, table column, sort/filter/search, web behavior, serving semantics
- `Combined` semantics, API, UI, KPI, ranking, sorting, relationship interpretation, 그리고 trusted `Combined` usage
- live Chzzk fetch, Chzzk category search API probe, scheduler mutation, service start/stop/restart, DB write, backfill, reingest, bootstrap, 그리고 runtime loader 변경
- fixture/example 생성, raw/private evidence promotion, generalized provider abstraction, 그리고 broader platform/tooling adoption

## Audit Results

- 결과(Result): `unknown / insufficient evidence`
- 사유(Reason):
  - 확인한 tracked 문서와 test는 현재 category-only observed evidence boundary, bounded sample caveat, bucket coverage caveat, public/private safety boundary, `Combined` blocked 상태를 보존한다.
  - 사용 가능한 local checkpoint summary는 오래된 local/operator evidence이다. sanitized historical context로는 유용하지만, 이 audit는 이를 2026-05-23 현재의 live scheduler health, current DB freshness, current API freshness, full live-list completeness, pagination exhaustion, full 1d/7d semantics의 근거로 취급하지 않는다.
  - 실제 관측된 Chzzk category 데이터를 category-to-game candidate의 seed 설정, 저장, 우선순위 지정, review에 사용할 준비가 되었는지 판단할 만큼 충분한 tracked public-safe current coverage/freshness aggregate를 찾지 못했다.
- 필수 blocker:
  - 현재 공개 가능한 Chzzk category coverage/freshness evidence가 tracked durable docs에 없다.
  - current coverage gap, stale window, skipped evidence, pagination state는 live fetch, DB read/write, scheduler check, raw/private log, service runtime evidence 없이는 현재 상태로 검증할 수 없다.
  - 현재 관측된 category set의 identity/name stability는 public-safe tracked evidence만으로는 `Unknown`이다.
- 권장되는 다음 조치:
  - observed data 기반 candidate implementation 전에, raw/private evidence를 공개하지 않는 current sanitized aggregate summary를 read-only 방식으로 추가 수집한다.

## Coverage/Freshness

확인된 근거:

- tracked docs는 Chzzk를 bounded category observed evidence로 정의하며, Steam-equivalent baseline으로 보지 않는다.
- `/chzzk/categories/overview`는 category-only observed evidence로 문서화되어 있고, tests도 이 boundary를 확인한다.
- 기존 문서와 test는 bucket coverage와 bounded live-list completeness를 분리한다. `bounded_sample_caveat="bounded_sample"`은 bounded pagination/live-list completeness caveat이고, `coverage_status`는 bucket coverage evidence이다.
- 기존 문서는 Chzzk의 full 1d/7d semantics에 category-level distinct KST half-hour bucket coverage가 필요하다고 설명한다. bounded sample은 full live-list population 또는 pagination exhaustion으로 표현할 수 없다.

해석:

- 현재 public contract는 docs/API/web boundary 표현이 completeness를 과장하지 못하게 막는 데 충분하다.
- 그러나 current observed category evidence가 candidate review에 활용할 만큼 충분한 freshness와 범위를 갖췄는지 입증하기에는 부족하다.

Unknown:

- 2026-05-23 현재 Chzzk category coverage/freshness
- 현재의 stale window, skipped evidence의 유형별 발생 현황, missing category evidence, bucket coverage 수준, pagination state
- 현재 관측된 category가 candidate-only category-to-game review에 충분한 대표성을 갖는지 여부

## 카테고리 안정성

확인된 근거:

- `categoryType=GAME`은 Chzzk provider category type evidence이며, canonical game identity가 아니다.
- tracked 문서와 test는 `categoryType=GAME`이 Steam mapping, canonical game semantics, `Combined` row, ranking/sorting/KPI, 또는 trusted mapping을 만들 수 없다고 고정한다.
- 기존 boundary 문서는 category evidence를 `dim_game`, `game_external_id`, trusted mapping, `Combined`와 분리한다.

Unknown:

- 현재 관측된 Chzzk category identity/type/name signal이 candidate-only review에 충분히 stable한지 여부
- 현재 관측된 category name에 renamed category, ambiguous alias, regional title, same-name collision, franchise collision 같은 review ambiguity가 얼마나 포함되어 있는지 여부

## 한계 조건 유지 (Caveat Preservation)

확인된 근거:

- tracked 문서는 bounded sample, bucket coverage, missing evidence, skipped evidence, failure, pagination caveat를 보존한다.
- 기존 API/web test는 Chzzk source-view 문구가 observed evidence를 완전한 1d/7d product metric처럼 표현하지 않고, 실제 관측 범위를 드러내는 표현을 유지하는지 확인한다.
- 기존 boundary 문서는 `candidate`, `unresolved`, `rejected`를 untrusted review evidence state로 유지한다.

위험:

- 향후 candidate review가 실제 관측 category data를 가져오면서 동일한 caveat를 함께 보존하지 않으면, review 결과가 실제보다 더 강한 completeness를 암시할 수 있다.
- 향후 workflow가 skipped evidence 또는 pagination caveat를 숨기면, reviewer가 candidate evidence를 full live-list coverage처럼 오해할 수 있다.

Unknown:

- candidate review input이 될 정확한 category set에 대해 모든 caveat를 보존한 current sanitized evidence package가 존재하는지 여부

## Public/Private Safety

확인된 근거:

- public docs에는 durable contract와 sanitized evidence category만 남길 수 있다.
- raw provider payload, raw API response, row-level UGC, credential, `.env` value, private path, scheduler XML/stdout, raw runtime log, screenshot, 실제 category/channel/display value, live title, thumbnail, raw Grafana/Prometheus response는 public docs와 PR text에 포함하지 않는다.
- candidate review evidence는 provider category identity, candidate canonical game reference, normalized comparison hint, ambiguity reason, reviewer/operator note, timestamp 같은 sanitized evidence category로만 다룰 수 있다.

Unknown:

- 현재 실제 관측된 Chzzk category evidence가 review에 충분한 public-safe aggregate로 이미 변환되어 있는지 여부

## Serving 분리

확인된 근거:

- `/chzzk/categories/overview`는 category-only observed evidence로 남아 있다.
- 기존 test는 endpoint/model/web path가 Steam mapping, canonical game identity, mapping status, `trusted`/`approved` field, raw provider field, 또는 private evidence field를 노출하지 않음을 확인한다.
- current docs는 candidate evidence를 trusted mapping, canonical game semantics, ranking/sorting/KPI, serving semantics, 또는 `Combined`에 사용하지 못하게 한다.
- `Combined`는 trusted mapping, serving semantics, API response 구조, regression expectation, Human Gate가 별도 승인될 때까지 blocked/pending 상태로 남는다.

Unknown:

- 이 ticket은 read-only audit이며 candidate implementation이 scope 외부이므로, 현재 candidate implementation path는 검토하지 않았다.

## Mapping Implementation 영향

이 audit는 real observed-data category-to-game candidate implementation을 승인하지 않는다.

실제 관측된 Chzzk category data를 category-to-game candidate의 seed 설정, 저장, 우선순위 지정, review에 사용하려면, 향후 ticket에서 최소한 아래 질문에 답할 수 있는 current public-safe evidence가 필요하다.

- current category coverage/freshness 및 stale-window 상태
- current bucket coverage distribution 및 missing evidence boundary
- pagination exhaustion을 주장하지 않는 current pagination caveat state
- sanitized category 수준에서의 current category identity/type/name stability
- skipped/failure evidence가 candidate review input에 함께 보존되는 방식
- raw/private evidence가 public docs, fixture, PR text, API/UI semantics, 그리고 durable decision record에 들어가지 않는 방식

그 전까지는 candidate-only implementation planning에서 boundary를 논의할 수는 있지만, real observed category data를 사용하는 implementation은 current evidence 부족으로 인해 blocked 상태로 둔다.

## 보류 항목 (Deferred Items)

- current sanitized evidence가 확보된 뒤 real observed-data candidate implementation planning
- 향후 승인된 implementation ticket이 열릴 경우 candidate evidence test-only guardrail
- 향후 evidence가 current coverage/freshness 판단을 바꿀 경우 docs-only guardrail update
- trusted mapping, `approved` / `trusted` promotion, serving semantics, `Combined` readiness는 모두 향후 Human Gate 대상으로 유지한다.
