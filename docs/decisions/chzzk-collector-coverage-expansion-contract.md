# Chzzk Collector Coverage Expansion Planning Contract

Status: docs-only planning contract
Ticket: `CHZZK-COLLECTOR-COVERAGE-EXPANSION-001`
Type: Planning-contract ticket
Date: 2026-10-05 (KST)

이 문서는 Chzzk live-list collector의 coverage를 현재 fixed bounded pagination에서 exhaustion-oriented traversal로 확장하기 위한 future implementation authority를 정의한다.

이 문서 자체는 collector/runtime behavior, scheduler configuration, DB data, API/Web behavior, trusted mapping, `Combined` semantics를 변경하지 않는다.

## User Decision

- Problem: 현재 live-list fetch는 `size=20`, `pages=3` 기본값을 사용하며 provider `next` cursor가 남아 있어도 configured page bound에 도달하면 정상 fetch를 종료한다. 이 때문에 정상 recurring collection이 provider pagination exhaustion이 아니라 fixed page sample에 머물 수 있다.
- Why now: 현재 Chzzk/Combined public semantics는 `bounded_sample` caveat를 유지하고 있으며, 더 넓은 collection evidence가 필요하다. Collector coverage expansion은 mapping expansion이나 broader `Combined` semantics보다 먼저 별도 boundary로 설계할 필요가 있다.
- Observable success: future repository implementation이 provider pagination exhaustion을 normal success로 추구하되 finite safety budgets와 deterministic termination evidence를 갖추고, 별도 Human Gate 전에는 authority runtime의 recurring breadth를 바꾸거나 live activation하지 않는다.
- Must not change: current `bounded_sample` product/API semantics, category evidence와 trusted mapping의 분리, current no-overlap coordination boundary, existing public/private evidence boundary.

## Current Repository Evidence

Current `main @ 8827014e4efd8e8c64fd7c443c1001405408ad26`에서 확인한 구현 기준은 다음과 같다.

- `src/chzzk/ingest/run_chzzk_fetch_load_manual_orchestration.py`의 current defaults는 `DEFAULT_FETCH_SIZE = 20`, `DEFAULT_FETCH_PAGES = 3`이다.
- `live_list_temporal_probe.fetch_pages(...)`는 provider `next` cursor를 순차적으로 따라가지만 configured `pages` bound에서 멈추고, usable next cursor가 없으면 더 일찍 종료한다.
- current sanitized pagination evidence는 `pages_fetched`, `pages_requested`, `last_page_next_present`, `bounded_page_cutoff`를 포함한다. Configured bound에 도달하면서 next cursor가 남으면 `bounded_page_cutoff=true`로 식별할 수 있다.
- current fetch failure는 `quota_http_error`(`429`), 다른 `http_error`, `request_error`, `invalid_json`, `malformed_page`를 구분한다.
- fetch failure가 있으면 이미 받은 raw pages는 local/private evidence로 남길 수 있지만 derived `category-result.jsonl` / `channel-result.jsonl`은 생성하지 않는다.
- fetched pages는 category/channel aggregation 전에 `merge_pages(...)`로 단순 연결된다. Current code는 cross-page live-item dedupe를 수행하지 않는다.
- current default fetcher는 page traversal이 끝난 뒤 한 번 `collected_at=utc_now()`를 정하고, merged category/channel rows 전체에 같은 `collected_at`을 전달한다. `bucket_time`은 이 run-level `collected_at`의 KST 30-minute floor다.
- manual orchestration은 fetch/load boundary 전체를 `NoOverlapLock`으로 보호한다. Collector expansion은 이 coordination/no-overlap contract를 약화하면 안 된다.
- current durable product/data contracts는 `bounded_sample`을 bucket coverage와 분리된 live-list population-completeness caveat로 유지하며, bounded cutoff/next cursor evidence가 있으면 pagination exhaustion 또는 full live-list population을 주장하지 못하게 한다.

## Human-provided Sanitized Diagnostic Evidence

다음 one-off diagnostic은 point-in-time aggregate evidence로만 사용한다.

- 한 run은 30 pages / 600 live items를 순회했고 모든 request가 HTTP 200이었으며, 30 pages 이후에도 next cursor가 남아 있었다.
- 별도 run은 60 pages / 1,200 live items를 순회했고 모든 request가 HTTP 200이었으며, 60 pages 이후에도 next cursor가 남아 있었다.
- 정상 HTTP 200 response headers에서 confirmed numeric rate-limit/quota value는 확인되지 않았다.
- `/open/v1/lives`의 numeric provider quota는 현재 public/runtime contract로 확정되지 않았다.

따라서 numeric provider quota는 **unknown**이다.

이 evidence는 production-wide behavior, peak-time behavior, provider quota, full-population completeness, transactionally frozen snapshot, safe truly-unbounded traversal을 증명하지 않는다.

## Target Collection Semantics

### Normal success

Future collector의 normal successful termination은 fixed page target이 아니라:

```text
provider pagination exhaustion
```

이어야 한다.

여기서 pagination exhaustion은 valid page를 처리한 뒤 usable next cursor가 더 이상 없음을 관측한 상태를 뜻한다.

Pagination exhaustion은 다음을 뜻하지 않는다.

- transactionally frozen provider snapshot
- duplicate-free traversal
- traversal 중 provider list mutation이 없었다는 보장
- complete point-in-time provider universe
- product-level full population completeness

### Finite safety boundary

Exhaustion-oriented traversal은 truly unbounded loop가 아니다.

Phase 1 implementation은 반드시 다음 repository-controlled safety mechanisms를 제공해야 한다.

- finite hard page/request ceiling
- finite overall traversal deadline/time budget
- repeated-cursor pagination-loop guard
- existing per-request timeout/failure handling과의 deterministic integration

Hard ceiling과 deadline은 normal target breadth가 아니라 runaway-protection circuit breaker다.

이 planning contract는 production numeric quota를 invent하지 않으며, authority runtime에서 사용할 exact hard ceiling/deadline numeric values도 승인하지 않는다. Phase 1은 finite configurable mechanism과 tests를 구현할 수 있지만, authority runtime의 exact values와 activation은 Phase 2 Human Gate에서 승인한다.

### Sequential traversal and no-overlap

Cursor pagination은 sequential traversal로 유지한다. Cursor-dependent pages를 speculative parallel fan-out으로 바꾸지 않는다.

Existing manual/recurring coordination과 no-overlap lock scope를 약화하거나 fetch를 lock 밖으로 이동하지 않는다.

## Termination and Failure Contract

Phase 1은 적어도 다음 termination reasons를 deterministic하게 구분해야 한다.

- `pagination_exhausted`
- `hard_page_limit_reached`
- `deadline_exceeded`
- `repeated_cursor`
- `quota_http_error`
- `http_error`
- `request_error`
- `invalid_json`
- `malformed_page`

`pagination_exhausted`만 exhaustion-oriented successful collection termination이다.

`hard_page_limit_reached`, `deadline_exceeded`, `repeated_cursor`는 safety termination이며 successful exhaustion으로 취급하지 않는다. Provider/request/response failures 역시 successful exhaustion이 아니다.

Safety/failure termination에서 이미 fetched raw pages는 current public/private boundary에 따라 local/private evidence로 남길 수 있다. 그러나 current failure behavior와 같은 fail-closed data path를 유지하여 derived category/channel result artifacts를 successful collection 결과처럼 생성하거나 gold write 대상으로 승격하지 않는다.

Empty first/terminal page가 valid response이고 usable next cursor가 없다면 collection termination은 `pagination_exhausted`일 수 있다. Derived result는 current empty-success semantics를 따른다.

## Pagination Evidence Contract

Current evidence compatibility를 유지하면서 termination meaning을 더 명확히 한다.

Required sanitized evidence:

- `pages_fetched`: 실제 valid page count
- `pages_requested`: compatibility field로 유지한다. Exhaustion mode에서는 configured hard page ceiling과 같은 finite upper bound를 나타내며 ordinary target breadth로 해석하지 않는다.
- `last_page_next_present`: 마지막 valid fetched page에 usable next cursor가 있었는지
- `bounded_page_cutoff`: hard page ceiling에 도달했고 next cursor가 남아 있어 traversal이 잘린 경우에만 `true`
- new explicit termination evidence: implementation은 `termination_reason` 또는 동등하게 명확한 sanitized field로 위 termination reason을 노출한다.
- new explicit exhaustion evidence: `pagination_exhausted` 또는 동등한 boolean/equivalent evidence로 normal exhaustion success를 다른 success-like states와 구분한다.
- configured hard page ceiling과 deadline은 secrets/private runtime detail을 노출하지 않는 범위에서 sanitized numeric/config evidence로 기록할 수 있다.

`bounded_page_cutoff=false`만으로 pagination exhaustion을 추론하면 안 된다. Deadline, repeated cursor, provider failure도 false일 수 있으므로 explicit termination evidence가 authority다.

기존 consumers/tests가 `pages_fetched`, `pages_requested`, `last_page_next_present`, `bounded_page_cutoff`를 읽는 경우 Phase 1은 abrupt removal 없이 compatibility를 유지하거나 명시적인 migration regression을 함께 제공해야 한다.

## Timestamp and 30-minute Bucket Semantics

Current implementation은 fetch traversal이 끝난 뒤 run-level `collected_at`을 한 번 정하고, merged category/channel rows 전체에 같은 timestamp를 사용한다.

Phase 1은 이 deterministic single-bucket behavior를 유지한다.

- successful traversal 전체에 page별 `collected_at` / `bucket_time`을 만들지 않는다.
- derived rows는 하나의 run-level `collected_at`을 공유한다.
- `bucket_time`은 그 `collected_at`의 KST half-hour floor다.
- traversal이 30-minute boundary를 넘더라도 한 logical collection을 여러 bucket으로 찢지 않는다.
- 현재 capture point를 silently start-time 또는 per-page time으로 바꾸지 않는다.
- 별도 timing evidence가 필요하면 `started_at`, duration/deadline evidence를 추가할 수 있지만 `collected_at` 의미를 재사용하지 않는다.
- safety/failure termination은 derived result를 생성하지 않으므로 successful collection bucket을 만들지 않는다.

따라서 long traversal의 successful bucket은 current semantics와 같이 traversal 완료 후 정한 run-level collection timestamp에 대응한다. 이는 frozen snapshot timestamp가 아니다.

## Provider-list Mutation and Duplicate Handling

Provider list는 pagination traversal 동안 변할 수 있다.

따라서 `pagination_exhausted`는 “cursor chain의 terminal page를 관측했다”는 collection evidence이지, 시작 시점의 provider universe를 atomic하게 snapshot했다는 뜻이 아니다. Traversal 중 item이 page 사이에서 이동하면 miss 또는 repeated appearance 가능성을 배제할 수 없다.

Current code는 pages를 concatenate한 뒤 aggregation하며 cross-page dedupe를 하지 않는다.

현재 repository/provider evidence는 `channelId` 또는 다른 field를 live-session-level stable dedupe identity로 확정하지 않는다. Phase 1은 이를 임의로 dedupe key로 승격하지 않는다.

Smallest safe contract는 다음과 같다.

- proven stable identity가 없는 동안 current no-dedupe behavior를 silently “deduplicated complete population”으로 표현하지 않는다.
- Phase 1은 duplicate handling을 명시적으로 no-dedupe/unknown identity 상태로 보존하고 regression으로 고정할 수 있다.
- Future evidence가 stable per-live identity를 확립하면 별도 reviewed change로 dedupe를 추가할 수 있다.
- Phase 2 live activation에서는 이 residual duplicate/mutation uncertainty를 remaining risk로 명시해야 한다. Human이 이를 수용하지 않으면 activation 전에 별도 identity/dedupe contract가 필요하다.

## Completeness Semantics

다음 세 층을 분리한다.

### Collector pagination completeness

`pagination_exhausted`는 current fixed cutoff보다 강한 traversal evidence다.

`hard_page_limit_reached`, `deadline_exceeded`, `repeated_cursor`, provider/request/response failure는 pagination-incomplete termination이다.

### Bucket-level collection evidence

Successful exhausted traversal로 생성된 category/channel rows는 해당 one logical collection bucket의 observed evidence다.

이는 provider list mutation/duplicate uncertainty를 제거하지 않으며, transactionally frozen full-population bucket을 의미하지 않는다.

Safety/failure termination은 successful derived bucket을 만들지 않는다.

### Product-level completeness

Current `bounded_sample_caveat="bounded_sample"` semantics를 유지한다.

Pagination exhaustion이 추가되어도 다음을 자동으로 claim하지 않는다.

- full provider population
- exact point-in-time universe
- uncaveated current viewers
- strict/full product completeness
- `Combined` completeness

Current `coverage_status` / 1d/7d bucket coverage semantics와 pagination termination evidence는 별개다.

Current `chzzk_collection_bucket_count_7d` 같은 persisted global bucket denominator도 scheduler success count나 frozen-population completeness proof로 재해석하지 않는다.

`bounded_sample`을 제거하거나 더 강한 product completeness label로 바꾸는 일은 이 contract와 Phase 1 범위 밖이다.

## Collection vs Mapping Boundary

Collector coverage expansion은 category-to-game identity/mapping과 분리한다.

- collector는 trusted Steam mapping이 없는 valid upstream Chzzk category evidence를 버리지 않는다.
- parser/schema의 observed category evidence boundary를 유지한다.
- collection을 trusted `GAME` mapping으로 제한하지 않는다.
- `categoryType=GAME`은 provider category-type evidence일 뿐 canonical Steam game identity가 아니다.
- candidate / unresolved / rejected review evidence와 trusted mapping의 authority separation을 유지한다.

이 contract는 automatic trusted mapping, fuzzy/inferred promotion, candidate → trusted auto-promotion, trusted mapping insert/update, mapping review workflow, mapping discovery scheduler, broader `Combined` semantics를 승인하지 않는다.

## Phase Authority

### Phase 1 — repository implementation

Phase 1은 repository capability만 구현할 수 있다.

Authorized examples:

- exhaustion-oriented cursor traversal
- finite hard page/request ceiling
- finite traversal deadline
- repeated-cursor loop guard
- explicit sanitized termination/exhaustion evidence
- compatibility for current pagination evidence
- deterministic single-run timestamp/bucket behavior
- focused tests
- implementation 때문에 실제로 필요한 최소 durable docs update

Phase 1 must not:

- authority production recurring breadth를 변경한다.
- scheduler configuration을 mutate한다.
- authority runtime에서 broader collector를 activate한다.
- uncontrolled live provider fetch를 수행한다.
- DB backfill/reingest/bootstrap을 수행한다.
- trusted mapping 또는 `Combined` semantics를 변경한다.
- Phase 2 authority를 스스로 부여한다.

Implementation은 separately gated live activation 전까지 authority runtime behavior에 inert해야 한다.

### Phase 2 — live activation / bounded runtime verification

Phase 2는 별도 Human Gate approval 이후에만 수행할 수 있다.

Human Gate Scope:

```text
Authority runtime에서 exhaustion-oriented Chzzk traversal을 실제 recurring/live collection에
적용하는 exact activation boundary. 여기에는 production hard page/request ceiling,
overall traversal deadline, recurring runtime breadth/configuration, live provider execution,
그리고 승인된 bounded runtime verification이 포함된다.
```

Pre-Gate Allowed Work:

```text
Phase 1 repository implementation, focused/full validation, required Fresh-context review,
그리고 reviewed Phase 1 implementation PR의 human merge decision/merge.
Merged implementation은 authority runtime collector breadth/configuration을 바꾸거나
live exhaustion-oriented traversal을 자동 활성화해서는 안 된다.
```

Pre-Gate Merge Allowed:

```text
Yes
```

Phase 1 merge 자체는 Phase 2 Human Gate approval이 아니다.

Phase 2 approval은 exact production safety budgets와 live activation scope를 human-authored GitHub PR comment 또는 review로 명시해야 한다.

## Risk / Review / Human Gate

- Risk Level: High
- Review Level: Fresh-context
- Human Gate Required: Yes
- Review Reason: scheduler/recurring collection behavior, provider request breadth, failure/partial semantics, pagination-completeness evidence, public/private evidence boundary를 함께 변경할 수 있기 때문이다.
- Independent Review Status: Pending — future Phase 1 implementation은 implementation conversation과 분리된 Fresh-context review가 필요하다.
- Human Decision Status: Pending — Phase 2 live activation은 별도 human-authored GitHub approval evidence가 필요하다.

Phase 1 pre-gate merge에는 current runbook의 조건을 적용한다. Required validation/CI가 통과하고, Fresh-context review가 `Passed`이며, blocking finding/evidence gap이 없고, Human이 별도 merge decision을 내려야 한다.

## Public Repo Safety

Public docs/PR/test evidence에는 다음을 포함하지 않는다.

- credentials, Client secret, token
- raw provider payload
- actual private category/channel/title values
- row-level UGC
- private host/path/runtime detail
- raw scheduler XML/stdout
- private DB rows
- raw terminal capture

Human-provided diagnostics를 public evidence로 사용할 때는 이 문서의 sanitized aggregate facts만 사용한다.

## Out of Scope

- additional live Chzzk diagnostic
- current fetch page default를 이 docs task에서 변경
- collector Python implementation in this docs task
- scheduler/runtime mutation
- DB schema/DDL change
- DB write, backfill, reingest, bootstrap
- live recurring activation
- trusted mapping mutation/promotion
- mapping discovery scheduler
- candidate write/promotion workflow
- `Combined` SQL/API/Web semantic change
- `bounded_sample` removal
- UI work
- Airflow, Dagster, dbt adoption
- orchestration architecture redesign
- unrelated retention/recovery work
- `dev-notes` edits 또는 private checkpoint sync

## Acceptance Criteria

- AC-1: Current fixed `size=20`, `pages=3`, cursor-following, failure classes, no-overlap, merge-before-aggregation, timestamp/bucket behavior를 current repository evidence와 일치하게 기록한다.
- AC-2: Normal success를 `pagination_exhausted`로 정의하고 hard ceiling/deadline/repeated cursor를 finite circuit breakers로 정의한다.
- AC-3: Provider/request/response failures와 safety termination을 explicit deterministic evidence로 구분하고 non-exhausted termination이 successful derived collection bucket으로 승격되지 않게 한다.
- AC-4: `pages_fetched`, `pages_requested`, `last_page_next_present`, `bounded_page_cutoff` compatibility와 new explicit termination/exhaustion evidence 요구사항을 정의한다.
- AC-5: One logical collection은 current single run-level `collected_at`과 one KST half-hour bucket semantics를 유지한다.
- AC-6: Provider-list mutation과 cross-page duplicate uncertainty를 명시하고, proven stable identity 없이 `channelId` 등으로 dedupe하지 않는다.
- AC-7: `pagination_exhausted`와 transactionally frozen/full-population/product completeness를 분리하고 current `bounded_sample`을 유지한다.
- AC-8: Collection과 category-to-game mapping authority를 분리하고 unmapped valid category evidence를 collection 단계에서 버리지 않는다.
- AC-9: Phase 1 implementation은 inert repository capability로 제한되고, Phase 2 live activation은 exact production budgets/runtime change에 대한 별도 Human Gate 뒤에만 가능하다.
- AC-10: Future Phase 1 implementation은 focused pagination/failure/timestamp/no-overlap regression과 final repo-root `./scripts/check.sh`를 통과하고 Fresh-context review evidence를 갖춘다.

### User Acceptance Examples

- Expected case: next cursor를 따라 finite budgets 안에서 terminal page까지 도달하면 `pagination_exhausted` evidence가 남고 one logical collection bucket의 derived rows가 생성될 수 있다.
- Boundary case: hard page ceiling, deadline, repeated cursor 또는 provider/request/response failure가 발생하면 explicit non-exhausted termination evidence가 남고 partial traversal이 successful derived bucket으로 쓰이지 않는다.
- Must not happen: next cursor가 남은 hard cutoff를 pagination exhaustion/full population으로 표시하거나, `bounded_sample`을 제거하거나, trusted mapping 여부로 upstream category collection을 제한하거나, Phase 1 merge만으로 authority runtime activation을 수행한다.

## Required Checks for Future Phase 1

최소 focused coverage:

- `tests/chzzk/probe/test_live_list_temporal_probe.py`
- `tests/chzzk/ingest/test_run_chzzk_fetch_load_manual_orchestration.py`
- relevant recurring/no-overlap regression
- current pagination evidence compatibility regression
- termination reason tests for exhaustion, hard ceiling, deadline, repeated cursor, `429`, other HTTP error, request error, invalid JSON, malformed page
- timestamp/bucket single-run determinism regression
- no-dedupe/unknown-identity boundary regression where applicable

Final code state:

```bash
./scripts/check.sh
```

Runtime/provider verification은 Phase 1 validation이 아니다.

## Documentation Impact

이 planning-contract가 future implementation authority의 canonical source다.

Phase 1 implementation 때 실제 code/data semantics가 바뀌는 durable docs만 최소 범위로 갱신한다. 이 docs-only planning task에서는 `README.md`, `docs/source-inventory.md`, `docs/data-model-spec.md`, `docs/metrics-definitions.md`, existing mapping/Combined contracts를 opportunistically refresh하지 않는다.

Current repository에는 historical/current-state wording이 완전히 정렬되지 않은 문서가 있을 수 있다. 그것이 이 collector contract의 authority를 materially contradict하지 않는 한 별도 cleanup scope로 남긴다.

## Suggested Branch Name

- `feat/chzzk-exhaustion-pagination`

## Suggested PR Title

- `feat(chzzk): add exhaustion-oriented collector traversal`
