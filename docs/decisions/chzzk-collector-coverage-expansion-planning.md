# Chzzk Collector Coverage Expansion Planning Contract

Status: Proposed canonical planning-contract — Human이 선택한 방향을 기록한다. repository workflow를 통해 이 문서가 merge되기 전에는 implementation 또는 live activation authority가 아니다.

Ticket: `CHZZK-COLLECTOR-COVERAGE-EXPANSION-001`

Date: 2026-10-05 (KST)

## Type

Planning-contract ticket

## User Decision

- Problem: 현재 Chzzk `/open/v1/lives` collection은 provider cursor pagination을 따르지만 normal path에서는 fixed page bound에서 멈추므로, 성공한 run도 다음 cursor가 남은 상태에서 종료될 수 있다.
- Why now: Human은 `Useful Combined v1` live application 이후 다음 PMTS planning work로 Chzzk collector coverage expansion을 선택했다. 다음 implementation이 collector breadth 또는 authority runtime behavior를 바꾸기 전에 durable contract가 필요하다.
- Observable success: 후속 repository implementation이 provider pagination exhaustion과 safety/failure termination을 구분하고, 하나의 deterministic collection bucket을 유지하며, 별도 gate를 거친 live activation 전까지 inert 상태를 유지할 수 있다.
- Must not change: 이 planning task에서는 현재 `bounded_sample` product/API semantics, category observed-evidence boundary, trusted mapping authority, `Combined` semantics, scheduler/runtime authority, DB contents, current live collector breadth를 변경하지 않는다.

## Current Repository Evidence

`main @ 8827014e4efd8e8c64fd7c443c1001405408ad26` 기준으로 다음이 확인된다.

- `src/chzzk/ingest/run_chzzk_fetch_load_manual_orchestration.py`는 `DEFAULT_FETCH_SIZE = 20`과 `DEFAULT_FETCH_PAGES = 3`을 사용한다.
- `src/chzzk/probe/live_list_temporal_probe.py::fetch_pages(...)`는 provider `next` cursor를 따라가며 usable next cursor가 없으면 조기 종료하고, 그렇지 않으면 configured page bound에서 멈춘다.
- 기존 fetch failure는 HTTP `429`의 `quota_http_error`, 그 밖의 `http_error`, `request_error`, `invalid_json`, `malformed_page`를 구분한다.
- sanitized pagination evidence에는 `pages_fetched`, `pages_requested`, `last_page_next_present`, `bounded_page_cutoff`가 포함된다. configured page bound까지 성공적으로 도달했는데 다음 cursor가 남아 있으면 `bounded_page_cutoff`가 true다.
- multi-page payload는 category/channel aggregation 전에 `merge_pages(...)`가 이어 붙인다. 현재 code는 cross-page live-item dedupe를 수행하지 않는다.
- manual orchestration은 fetch/load path 전에 `NoOverlapLock`을 획득하고 bounded run이 끝난 뒤 해제한다.
- `src/chzzk/probe/live_list_temporal_probe.py::run_fetch()`는 `collected_at = utc_now()`를 provider fetch 전에 capture한 뒤 `fetch_pages(...)`를 실행하고, 같은 `collected_at`을 `write_probe_run(...)`에 전달한다.
- 반면 `src/chzzk/ingest/run_chzzk_fetch_load_manual_orchestration.py::_default_fetcher()`는 `fetch_pages(...)`가 끝난 뒤 `write_probe_run(..., collected_at=live_list_temporal_probe.utc_now(), ...)`를 호출하므로 logical `collected_at`을 fetch 후에 선택한다.
- 현재 durable semantics는 `bounded_sample_caveat="bounded_sample"`을 per-category bucket `coverage_status`와 분리한다. bounded cutoff 또는 남아 있는 next cursor를 pagination exhaustion이나 complete provider population으로 표현할 수 없다.
- `categoryType=GAME`은 provider category-type evidence일 뿐이다. candidate/unresolved/rejected evidence와 inferred/fuzzy/guessed mapping은 trusted mapping authority가 아니다.

이 evidence는 planning authority만 제공한다. Provider quota, full-population completeness, stable cross-page live-item identity, safe unbounded traversal을 증명하지 않는다.

## Human-Provided Diagnostic Evidence

다음 one-off evidence는 sanitized point-in-time aggregate context로만 유지할 수 있다.

- 한 run에서 30 pages / 600 live items를 순회했고 모든 request가 HTTP `200`이었지만 page 30 뒤에도 next cursor가 남았다.
- 별도 run에서 60 pages / 1,200 live items를 순회했고 모든 request가 HTTP `200`이었지만 page 60 뒤에도 next cursor가 남았다.
- 일반 HTTP `200` response header에서는 numeric rate-limit/quota 값을 확인하지 못했다.

따라서 numeric `/open/v1/lives` quota는 **unknown**이다. 이 evidence는 production-wide 또는 peak-time behavior, full-population completeness, transactionally frozen snapshot, truly unbounded traversal의 안전성을 증명하지 않는다. 이 contract-writing task는 추가 live Chzzk diagnostic을 허용하지 않는다.

## Scope

이 contract는 후속 Phase 1 repository implementation이 finite repository-controlled safety budget과 deterministic evidence를 갖춘 exhaustion-oriented Chzzk live-list traversal capability만 추가하도록 허용한다.

계획된 normal success target은 다음과 같다.

```text
provider pagination exhaustion
```

3, 6, 10 pages 같은 fixed ordinary sample은 새 capability의 target success rule이 아니다. 다만 exhaustion-oriented traversal도 explicit circuit breaker로 유한하게 제한해야 하며 truly unbounded loop가 되어서는 안 된다.

## Out of Scope

이 planning contract는 다음을 허용하지 않는다.

- 추가 Chzzk live API diagnostic
- 현재 active fetch page default 또는 authority recurring breadth 변경
- scheduler/runtime mutation 또는 live recurring activation
- DB schema/DDL 변경, DB write, backfill, reingest, bootstrap
- trusted mapping insert/update, automatic/fuzzy/inferred mapping, candidate promotion, mapping scheduler work
- `Combined` SQL/API/Web semantic 변경, score, ranking, recommendation, `bounded_sample` 제거 또는 재해석
- UI 작업
- Airflow, Dagster, dbt 또는 orchestration architecture redesign
- 관련 없는 retention/recovery 작업
- `dev-notes` 또는 private planning-state/checkpoint 변경

인접 작업을 발견해도 그 작업에 대한 authority가 생기지 않는다.

## Requirements

### 1. Normal termination and finite safety budgets

새 exhaustion-oriented capability는 valid provider page에 usable next cursor가 없을 때만 정상적인 pagination success로 종료해야 한다.

또한 다음 두 finite repository-controlled guard를 모두 요구한다.

- hard page/request ceiling
- overall execution deadline/time budget

page/request ceiling은 runaway-protection circuit breaker이며 ordinary collection rule이나 provider quota claim이 아니다. deadline은 traversal이 느려질 때 provider interaction과 lock occupancy를 제한한다.

Provider quota/headroom이 확인되지 않았으므로 이 contract는 어느 guard에도 numeric production value를 임의로 만들지 않는다. Phase 1은 current authority runtime breadth를 바꾸지 않으면서 새 capability에 guard를 explicit하게 만들고 fail-closed로 동작하게 해야 한다. Phase 2 activation 전에 Human Gate approval은 authority runtime에서 실제 사용할 exact page/request ceiling과 deadline을 지정해야 한다.

### 2. Pagination-loop protection

새 traversal은 repeated cursor 또는 그와 동등한 deterministic pagination loop condition을 감지해야 한다. loop가 감지되면 non-success termination으로 종료하고 추가 provider request를 발행하지 않아야 한다.

Loop protection은 hard page/request ceiling과 독립적이다. 새로운 provider behavior를 cursor loop로 인식하지 못하더라도 ceiling은 최종 runaway guard로 남는다.

### 3. Failure and termination semantics

다음 termination class는 sanitized evidence에서 서로 구분할 수 있어야 한다.

- `pagination_exhausted`
- `safety_cutoff`
- `deadline_exceeded`
- `pagination_loop_detected`
- `quota_http_error`
- `http_error`
- `request_error`
- `invalid_json`
- `malformed_page`

새 capability에서 `pagination_exhausted`만 successful pagination-completeness termination이다. Safety cutoff, deadline expiry, loop detection, provider/request/response failure는 incomplete collection attempt다.

이 contract는 새 retry/backoff loop를 허용하지 않는다. 기존 fail-fast provider/request/response behavior를 safe default로 유지하며, automatic retry behavior가 필요하면 별도 authority가 필요하다.

새 exhaustion-oriented capability의 incomplete collection attempt는 앞선 page 일부를 성공적으로 fetch했다는 이유만으로 DB-load-eligible category/channel evidence가 되어서는 안 된다. 기존 governance에 따라 local/private raw page를 유지할 수는 있지만, write path에 사용되는 derived category/channel result artifact는 incomplete traversal에 대해 fail-closed여야 한다.

### 4. Sanitized pagination evidence and compatibility

Phase 1은 기존 pagination field를 삭제하거나 조용히 재정의하지 않으면서 deterministic sanitized termination evidence를 추가해야 한다.

정확한 field name은 implementation에서 정할 수 있지만, emitted evidence로 reviewer가 최소한 다음을 판단할 수 있어야 한다.

- pagination이 정상 exhaustion으로 끝났는지
- hard safety cutoff가 발생했는지
- deadline이 만료됐는지
- pagination loop가 감지됐는지
- provider/request/response failure가 발생했는지
- termination 전까지 몇 request가 수행됐고 몇 JSON-object page가 local page evidence collection에 보존됐는지
- failure가 발생했다면 failing page 자체를 제외하고 그 전에 strict live payload validation까지 성공적으로 통과한 page가 몇 개인지
- 마지막으로 보존된 page evidence에 usable next cursor가 남아 있었는지

Compatibility expectation은 다음과 같다.

- `pages_fetched`는 해당 attempt에서 request와 JSON-object level 처리를 거쳐 local page evidence collection에 보존된 page 수를 계속 의미한다. 후속 strict live payload validation에서 마지막 page가 `malformed_page`로 판정되더라도 그 JSON object가 이미 local page evidence에 보존됐다면 current compatibility semantics상 `pages_fetched`에 포함될 수 있다. 이를 successful/valid page count로 재정의하지 않는다.
- `failure.pages_fetched_before_failure`는 failing page 자체를 제외하고 failure 발생 전에 strict live payload validation까지 성공적으로 통과한 page 수를 나타내는 별도 evidence다. `pages_fetched`와 같은 의미로 합치거나 하나를 다른 하나로 재정의하지 않는다.
- `pages_requested`는 계속 지원한다. 새 exhaustion-oriented mode에서 이를 모든 configured page를 정상적으로 fetch해야 한다는 기대값으로 표현해서는 안 된다. 재사용한다면 해당 invocation의 finite configured request/page ceiling이라는 의미를 문서화해야 한다.
- `last_page_next_present`는 current summary가 마지막으로 보존된 page evidence에서 관찰한 usable next cursor presence를 의미하는 compatibility evidence다. 이 field 하나만으로 해당 traversal이 successful pagination-completeness를 달성했다는 뜻은 아니다.
- hard page ceiling 때문에 traversal이 멈추고 usable next cursor가 남으면 `bounded_page_cutoff`가 true다. deadline, loop, provider/request/response failure 때문에 종료된 경우에는 true로 바꾸지 않는다.
- `coverage.status`는 temporal bucket coverage evidence로 유지하며 pagination-completeness 의미를 덧씌우지 않는다.

`malformed_page`는 계속 failure다. Malformed JSON-object page가 local page evidence에 보존되어 `pages_fetched`와 `last_page_next_present`에 반영될 수 있다는 사실은 successful collection, pagination exhaustion, load-eligible category/channel result, complete provider population 중 어느 것도 의미하지 않는다. Incomplete traversal의 derived category/channel result는 계속 fail-closed여야 한다.

Phase 1의 새 exhaustion-oriented capability는 기존 bounded/default path의 termination/result/write behavior를 암묵적으로 재정의해서는 안 된다. Shared `fetch_pages(...)` 또는 인접 shared code를 수정하더라도 Phase 2 activation 전까지 현재 active/default bounded path는 current observable behavior와 write eligibility semantics를 유지해야 한다. 이 compatibility는 기존 bounded behavior를 새로운 product-level completeness claim으로 승격하는 근거가 아니며, focused regression test로 보호해야 한다.

### 5. Collection timestamp and 30-minute bucket semantics

현재 timestamp capture timing은 path마다 다르다. Standalone `live_list_temporal_probe.py::run_fetch()`는 provider fetch 전에 `collected_at`을 capture하지만, current manual/default orchestration의 `_default_fetcher()`는 page traversal 이후 `collected_at`을 선택한다. 후자의 방식은 짧은 bounded fetch에서는 현재 observable behavior지만, 더 긴 logical collection에서는 traversal duration만으로 이후 30-minute bucket에 배치될 수 있다.

Phase 1은 새 exhaustion-oriented capability가 첫 provider request 직전에 하나의 logical collection anchor를 capture하도록 구현하는 것을 허용한다. 이 anchor는 traversal의 모든 derived category/channel row에 변경 없이 전달해야 하고, `bucket_time`은 계속 그 단일 anchor를 KST half-hour로 floor한 값이어야 한다.

하나의 logical traversal은 row를 서로 다른 30-minute bucket으로 나누어서는 안 된다. Completion time과 duration은 sanitized run evidence에 별도로 기록할 수 있지만 logical collection anchor를 조용히 대체해서는 안 된다.

기존 active/default bounded path의 observable behavior는 Phase 2 activation이 reviewed capability로 authority runtime을 명시적으로 전환하기 전까지 유지해야 한다.

### 6. Coordination and no-overlap behavior

Phase 1은 현재 no-overlap boundary를 유지해야 한다. fetch/load orchestration을 보호하는 lock은 전체 logical attempt를 계속 포함해야 하며, traversal이 길어져도 concurrent provider fetch를 만들거나 `lock_busy` behavior를 약화해서는 안 된다.

deadline은 하나의 traversal이 coordination boundary를 점유하는 시간을 제한하므로 이 safety model의 일부다.

### 7. Provider-list mutation during traversal

`pagination_exhausted`는 해당 traversal에서 제시된 cursor chain이 끝났다는 의미다. Provider가 transactionally frozen point-in-time universe를 제공했다는 의미가 **아니다**.

page를 순회하는 동안 live row는 나타나거나 사라지고, 순서가 바뀌거나 다른 page로 이동할 수 있다. 따라서 pagination exhaustion은 known fixed cutoff보다 강한 evidence일 수 있지만 full snapshot completeness보다는 약하다.

어떤 product/API wording도 exhaustion evidence를 특정 시점에 존재한 모든 live item을 정확히 한 번씩 관찰했다는 claim으로 바꾸어서는 안 된다.

### 8. Duplicate handling

현재 `merge_pages(...)`는 parser-eligible live item을 page 간에 이어 붙인 뒤 aggregation한다. Repository/provider evidence는 dedupe에 사용할 안전하고 stable한 cross-page live-session identity를 증명하지 않는다. 특히 `channelId`가 존재한다는 사실만으로 이를 해당 identity로 취급할 authority가 생기지 않는다.

따라서 Phase 1의 smallest safe contract는 다음과 같다.

- 새 cross-page dedupe key를 추측하거나 적용하지 않는다.
- strict live payload validation을 통과해 derived result merge 대상으로 처리되는 page는 현재 row multiplicity를 유지한다.
- proven dedupe identity가 없다는 사실을 explicit implementation/review caveat로 남긴다.
- pagination exhaustion에서 exact de-duplicated population total을 claim하지 않는다.

향후 live item을 dedupe하거나 stable identity를 선택하거나 aggregation semantics를 바꾸려면 사용 전에 별도의 evidence-backed contract update가 필요하다.

### 9. Completeness semantics

다음 의미는 계속 구분해야 한다.

```text
pagination exhausted
!=
transactionally frozen, complete point-in-time provider universe
```

또한 temporal bucket coverage 및 product-level completeness와도 분리해야 한다.

- 새 pagination termination evidence는 하나의 collector traversal을 설명한다.
- `coverage_status`는 시간에 따른 observed category bucket coverage를 설명한다.
- `bounded_sample_caveat="bounded_sample"`은 public/product caveat로 유지하며 traversal이 cursor chain을 exhaustion했다는 이유만으로 제거하지 않는다.
- `chzzk_collection_bucket_count_7d`는 persisted global category-fact bucket evidence로 유지한다. pagination-complete run count나 full provider-population completeness proof가 아니다.
- observation ratio `1`도 incomplete provider-population evidence와 양립할 수 있다.

Phase 1은 implementation이 증명할 수 없는 더 강한 product-level completeness claim을 추가해서는 안 된다.

### 10. Collection and mapping remain separate

Collector expansion은 trusted Steam mapping이 있는 category만이 아니라 valid upstream Chzzk observed category evidence에 적용한다.

기존 parser/schema category evidence boundary가 authoritative하다. `categoryType=GAME`은 provider category-type evidence이지 canonical Steam game identity가 아니다. Candidate, unresolved, rejected, inferred, guessed, fuzzy, hidden fallback mapping evidence가 이 작업을 통해 trusted mapping input이 되어서는 안 된다.

이 contract는 mapping discovery/promotion 또는 broader `Combined` semantics를 허용하지 않는다.

## Future Phase Authority

### Phase 1 — repository implementation

Phase 1은 이 contract에 필요한 inert repository capability만 구현할 수 있다.

- exhaustion-oriented traversal
- mandatory finite hard page/request ceiling
- mandatory overall deadline/time budget
- repeated-cursor/equivalent loop guard
- deterministic sanitized termination evidence와 compatibility handling
- 위에서 정의한 single logical collection-anchor behavior
- focused synthetic/mocked test
- implementation contract의 정확성을 유지하는 데 필요한 최소 durable docs update

Phase 1은 다음을 해서는 안 된다.

- `DEFAULT_FETCH_PAGES = 3`을 바꾸거나 current authority runtime collection breadth를 다른 방식으로 확장
- scheduler configuration mutation
- authority runtime에서 새 traversal 활성화
- validation을 위한 live provider fetch
- DB write, DDL, backfill, reingest, bootstrap
- 스스로 Phase 2 authority 부여

Checked-in capability는 별도 gate가 필요한 live activation에 대해 inert 상태로 남아야 한다.

### Phase 2 — live activation and bounded runtime verification

Phase 2는 required Human Gate가 exact approved scope를 명시한 human-authored GitHub evidence와 함께 Approved된 뒤에만 시작할 수 있다.

그 뒤에도 승인된 activation step만 수행할 수 있다.

- exact authority-runtime hard page/request ceiling과 deadline 선택
- actual recurring collector breadth를 reviewed exhaustion-oriented capability로 전환
- 그 전환에 필요한 exact scheduler/runtime configuration mutation
- approved budget을 사용하는 bounded live provider execution
- termination evidence, coordination behavior, write-path compatibility의 bounded runtime verification

Phase 1 PR merge, Fresh-context review 또는 이 planning-contract merge 자체는 Phase 2 Human Gate approval이 아니다.

## Acceptance Criteria

### Phase 1 repository implementation

- AC-1: synthetic/mocked test가 normal success가 hard ceiling 전에 provider pagination exhaustion에서 멈추는 것을 증명한다.
- AC-2: test가 hard ceiling에서 usable cursor가 남아 있으면 `safety_cutoff`로 종료하고 compatible cutoff evidence를 보존하며 load-eligible category/channel result를 만들지 않는 것을 증명한다.
- AC-3: test가 deadline expiry와 repeated-cursor/loop detection이 추가 request 없이 deterministic하게 종료되고 load-eligible category/channel result를 만들지 않는 것을 증명한다.
- AC-4: test가 `429`, other HTTP, request, invalid JSON, malformed-page failure evidence를 구분해서 보존하고 partial derived result를 successful collection으로 받아들이지 않는 것을 증명한다.
- AC-5: test가 새 termination evidence와 함께 `pages_fetched`, `pages_requested`, `last_page_next_present`, `bounded_page_cutoff` compatibility를 검증한다.
- AC-6: KST half-hour boundary를 가로지르는 simulated traversal에서도 모든 derived category/channel row가 single pre-request logical collection anchor와 bucket을 유지한다.
- AC-7: focused test가 새 traversal 때문에 current no-overlap behavior가 약화되지 않는 것을 증명한다.
- AC-8: 별도 authorized stable identity contract가 없는 한 multi-page merge behavior는 explicit no-dedupe를 유지하며, `channelId` alone을 dedupe key로 승격하지 않는다.
- AC-9: `bounded_sample`, bucket `coverage_status`, collection-bucket denominator meaning, mapping authority, `Combined` semantics가 변경되지 않는다.
- AC-10: focused regression test가 Phase 1의 새 exhaustion-oriented capability 또는 shared `fetch_pages(...)` 변경이 기존 active/default bounded `pages=3` path의 termination/result/write eligibility semantics를 바꾸지 않음을 증명한다. Phase 2 activation 전까지 current observable behavior를 유지하며, 이 compatibility를 새로운 product completeness claim으로 승격하지 않는다. Phase 1에서는 live provider/runtime/DB activation을 수행하지 않는다.

### Phase 2 activation

- AC-11: 실행 전에 Human Gate evidence가 exact authority-runtime page/request ceiling, deadline, runtime/scheduler mutation, bounded verification scope를 명시한다.
- AC-12: bounded verification이 approved runtime이 no-overlap behavior 또는 public/private evidence boundary를 약화하지 않으면서 exhaustion과 이 contract에 필요한 모든 safety/failure termination을 구분할 수 있음을 증명한다.
- AC-13: activation evidence는 증명되지 않은 frozen complete provider universe, de-duplicated exact population, provider quota를 claim하지 않는다.

## Required Checks

Phase 1 implementation에서는 당시 current repository runbook을 따르고 focused synthetic/mocked pagination, orchestration, timestamp/bucket, no-overlap test와 기존 bounded/default path compatibility regression test를 수행한 뒤 canonical final code-state validation을 실행한다. Implementation validation에는 live Chzzk provider call이 필요하지 않으며 허용되지도 않는다.

이 docs-only planning-contract PR에서는 current docs-only static validation contract를 따른다. Runtime/provider check는 applicable하지 않다.

## Manual QA

- Phase 1: live provider QA를 수행하지 않는다. Deterministic synthetic evidence를 검토하고 checked-in capability가 authority runtime breadth에 연결되지 않았음을 확인한다.
- Phase 2: Human Gate가 승인한 bounded runtime verification만 live provider/runtime을 사용할 수 있다.

## Risk Level

High

Reason: eventual activation은 recurring external-provider request breadth를 바꾸고 unknown provider quota/headroom 아래에서 collection/write behavior에 영향을 줄 수 있다. docs-only planning task와 inert Phase 1 implementation 자체는 이 live risk를 실행하지 않는다.

## Review Level

Fresh-context

## Review Reason

Future implementation은 pagination/failure semantics, recurring/no-overlap execution, timestamp/bucket semantics, public/private completeness evidence를 건드린다. Fresh-context review는 accepted contract, focused test, exact validation evidence, Phase 1 merge decision 전에 implementation이 inert 상태인지 검증해야 한다.

## Human Gate Required

Yes

```text
Human Gate Scope:
Phase 2 authority-runtime activation: exact recurring collector breadth/budget selection, any scheduler/runtime mutation that switches the authority runtime to exhaustion-oriented traversal, live provider execution using that broader traversal, and bounded runtime verification.

Pre-Gate Allowed Work:
Phase 1 inert repository implementation, focused tests, required durable docs, canonical validation/CI, required Fresh-context review, and—only after those requirements pass and a Human separately decides to merge—the Phase 1 implementation PR merge. This work must not itself change the authority runtime breadth, scheduler configuration, perform a live provider fetch, or activate the new traversal.

Pre-Gate Merge Allowed:
Yes
```

Human Gate는 human-authored GitHub PR comment 또는 review가 exact Phase 2 scope를 명시적으로 승인할 때까지 Pending이다. Planning-contract PR, implementation PR, PR merge, agent report, ChatGPT conversation은 approval evidence가 아니다.

## Public Repo Safety

Public evidence에는 durable contract text와 sanitized aggregate/termination evidence만 포함할 수 있다. Credentials, application identifiers, raw provider payloads, category/channel/title values, private paths, host-specific runtime detail, scheduler XML/stdout, raw terminal output, raw API bodies, row-level UGC를 publish하지 않는다.

위의 Human-provided 30-page 및 60-page diagnostic이 이 public planning record에 허용된 live diagnostic detail의 최대 범위다.

## Suggested Branch Name

`docs/chzzk-collector-coverage-contract`

## Suggested PR Title

`docs(chzzk): define collector coverage expansion contract`
