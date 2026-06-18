# Chzzk Current Aggregate Evidence Smoke

Status: docs-only public-safe checkpoint
Ticket: CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001
후속 티켓: CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001-FOLLOWUP
Date: 2026-05-23 (KST)

## Purpose

이 문서는 `CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001`의 후속 public-safe checkpoint다.

이전 Codex-only smoke는 `unknown / insufficient local access`로 종료되었다.

이후 human-run read-only aggregate smoke가 sanitized aggregate evidence를 제공했으므로, 이 문서는 raw/private evidence를 공개하지 않고 current API/DB aggregate 결과만 요약한다.

## Evidence Source Boundary

- Source: human-run read-only aggregate smoke를 public-safe aggregate evidence로 요약한 결과다.
- API boundary: local read-only API listener를 사용할 수 있었고, API docs route가 HTTP `200`을 반환했으며, `/chzzk/categories/overview?limit=200`도 HTTP `200`을 반환했다.
- DB boundary: read-only aggregate check로 관련 Chzzk fact relation, aggregate count를 확인했다.
- Public boundary: 이 문서는 raw command transcript, raw API response, raw JSON rows, raw SQL blocks, raw `psql` output, raw provider payload, row-level UGC, credential, `.env` value, private path, scheduler XML/stdout, raw runtime log, screenshot, raw Grafana/Prometheus response, category/channel/display value, live title, thumbnail을 포함하지 않는다.

## Non-goals

이 checkpoint는 아래 항목을 승인하거나 구현하지 않는다.

- category-to-game mapping implementation, candidate generation, mapping storage, trusted mapping, automatic matching
- schema, SQL, DDL, migration, DB write, backfill, reingest, bootstrap, loader/runtime/scheduler 변경
- API endpoint, response 구조, API field, web UI, route, table column, sort/filter/search, serving semantics 변경
- `Combined` semantics, API, UI, KPI, ranking, sorting, relationship interpretation
- generalized provider abstraction, App Catalog, tracked_universe, Price/Reviews wiring
- raw/private evidence promotion, public fixture/example 생성

## Result

- Result: `public-safe aggregate evidence available`
- Reason: human-run read-only aggregate smoke가 current API/DB freshness와 coverage를 public-safe aggregate 수준에서 확인했다.
- Still blocked: mapping implementation, candidate generation, mapping storage, trusted mapping, serving 변경, `Combined`는 여전히 `blocked` 상태로 남겨둔다.
- Next recommended action: observed data 기반 candidate implementation 전에 별도의 Human Gate와 test-only guardrails를 포함한 후속 ticket을 연다.

## API Aggregate Summary

확인된 aggregate 사실:

- API aggregate result: `available`
- `/chzzk/categories/overview?limit=200`: HTTP `200`
- API row count: `200`
- API distinct category id count: `200`
- latest API bucket max: `2026-05-23T16:00:00+09:00`
- API freshness age: `0.65` hours
- bounded sample caveat별 count: `bounded_sample`: `200`
- category type별 count: `GAME`: `189`, `ENTERTAINMENT`: `2`, `SPORTS`: `4`, `ETC`: `5`
- coverage status별 count: `observed_bucket_only`: `2`, `partial_window`: `123`, `full_1d_candidate_available`: `63`, `full_7d_candidate_available`: `12`
- `full_1d_candidate_available_count`: `75`
- `full_7d_candidate_available_count`: `12`
- missing 1d bucket count min/max: `0` / `47`
- missing 7d bucket count min/max: `0` / `335`
- blank category id count: `0`
- blank category name count: `0`
- blank category type count: `0`
- unknown or extra field count: `0`
- forbidden field present: `false`

해석:

- `coverage_status_distribution`과 boolean count field는 서로 다를 수 있다. `coverage_status`는 상호 배타적인 display/status field지만 boolean field는 서로 중첩될 수 있기 때문이다.
- `bounded_sample_caveat=bounded_sample`은 bounded sample, live-list completeness에 대한 caveat로 유지된다.
- 이 값들이 전체 live-list completeness나 pagination exhaustion을 증명하는 것은 아니다.
- 이 값들을 observed bucket-count candidate flag를 넘어선 full 1d/7d product semantics로 표현하지 않는다.

## DB Aggregate Summary

확인된 aggregate 사실:

- DB 연결 가능: yes
- `fact_chzzk_category_30m` 존재: true
- `fact_chzzk_category_channel_30m` 존재: true
- category fact의 distinct Chzzk category count: `383`
- DB latest bucket max: `2026-05-23 16:00:00+09`
- DB freshness age: `0.65` hours
- DB coverage status별 count: `observed_bucket_only`: `36`, `partial_window`: `272`, `full_1d_candidate_available`: `63`, `full_7d_candidate_available`: `12`
- DB missing 1d bucket count min/max: `0` / `47`
- DB missing 7d bucket count min/max: `0` / `335`
- type variation이 있는 category count: `0`
- name variation이 있는 category count: `0`
- channel fact row count: `40213`
- channel evidence가 있는 distinct category count: `383`
- channel bucket time max: `2026-05-23 16:00:00+09`

해석:

- 이는 aggregate-only fact다.
- raw category id, category name, channel id, channel name, live title, thumbnail, raw provider payload 또는 row-level UGC를 노출하지 않는다.
- 현재 freshness와 aggregate coverage 가시성을 지원한다.
- 이 evidence만으로 category-to-game mapping implementation을 승인하는 것은 아니다.

## Coverage / Freshness Interpretation

현재 API/DB aggregate evidence는 public-safe 문서 작성에 필요한 수준으로 충분히 최신이며, 이전의 `unknown / insufficient local access` blocker를 완화한다.

이 checkpoint는 public-safe aggregate evidence 기록을 지원하지만 다음 항목을 증명하는 것은 아니다:

- 전체 live-list completeness
- pagination exhaustion
- full 1d/7d product semantics
- trusted category-to-game mapping 준비 상태

`bounded_sample_caveat=bounded_sample`은 bucket coverage status와 별도로 유지된다. Bucket coverage status는 category별로 관측된 bucket 가용성을 나타내고, bounded sample caveat는 live-list/pagination completeness 위험을 나타낸다.

## 카테고리 안정성

확인된 aggregate 사실:

- blank category id count: `0`
- blank category name count: `0`
- blank category type count: `0`
- type variation이 있는 category count: `0`
- name variation이 있는 category count: `0`

해석:

- 이 aggregate check는 현재 관측된 category aggregate를 coverage/freshness 논의에 사용할 수 있다는 신뢰도를 높인다.
- `categoryType=GAME`은 provider category type evidence일 뿐 canonical game identity가 아니다.
- 이 aggregate check는 category-to-game 검토에서 alias, renamed category, regional title, same-name collision, franchise collision 문제를 해결하지 않는다.

## Channel Evidence Availability

확인된 aggregate 사실:

- `fact_chzzk_category_channel_30m` 존재: true
- channel fact row count: `40213`
- channel evidence가 있는 distinct category count: `383`
- channel bucket time max: `2026-05-23 16:00:00+09`

해석:

- Channel evidence는 aggregate category-channel evidence로 제공된다.
- channel id, channel name, live title, thumbnail, row-level UGC를 노출하지 않는다.
- Channel evidence는 `/chzzk/categories/overview`의 nullable observed evidence로 유지되며 trusted mapping이나 canonical game semantics를 생성하지 않는다.

## Serving 분리

`/chzzk/categories/overview`는 category-only observed evidence로 남는다.

이 checkpoint는 endpoint 동작, response 구조, API 필드, UI 필드, 정렬, 필터링, 테이블 컬럼, route 동작, serving semantics, source-view semantics를 변경하지 않는다.

`candidate`, `unresolved`, `rejected`는 untrusted review evidence state로 유지된다. `trusted` / `approved`는 향후 Human Gate 용어로만 남겨둔다.

`Combined`는 trusted mapping, serving semantics, API response 구조, regression expectations, Human Gate가 별도로 승인될 때까지 `blocked/pending` 상태로 유지된다.

## Mapping Implication

이 evidence는 Chzzk observed category aggregate의 current coverage/freshness 가시성을 높인다.

이 evidence만으로 다음 항목을 승인하는 것은 아니다:

- category-to-game mapping implementation
- candidate generation
- mapping storage
- trusted mapping
- automatic matching
- API/web/serving 변경
- `Combined`

observed data 기반 candidate implementation 전에 별도의 Human Gate와 candidate/trusted/Combined leakage를 방지하는 test-only guardrails가 여전히 요구된다.

## Public/Private Safety

이 checkpoint는 의도적으로 aggregate-only evidence만 기록한다.

여기에는 raw command transcript, shell prompt, `.env` loading command, DB credential command 구조, raw SQL block, raw `psql` output, raw API response, raw JSON row, raw provider payload, category/channel/display value, live title, thumbnail, screenshot, credential, secret value, private path, scheduler XML/stdout, raw runtime log, raw Grafana/Prometheus response, row-level UGC를 포함하지 않는다.

## Deferred

- category-to-game candidate generation implementation
- mapping storage 선택과 implementation
- trusted mapping, promotion/demotion rules
- automatic matching
- schema/API/data semantics 변경
- API/web/serving 변경
- `Combined` 준비 상태와 semantics
- live fetch, scheduler mutation, DB write, backfill, reingest, DDL, migration
- raw/private evidence promotion
- generalized provider abstraction

## Validation Expectations

이 docs-only checkpoint의 검증 사항:

- 편집 후 이 문서를 다시 정독한다.
- stale claim, 범위 확장, 비공개 데이터 노출 여부를 점검한다.
- `git diff --check`를 실행한다.
- `git status --short`를 실행한다.
- 문서에서 forbidden implementation claim, public-safety 위험을 검색한 뒤 허용된 boundary wording을 수동으로 검사한다.
- 이번 변경은 runtime/code 경로를 수정하지 않으므로 `./scripts/check.sh` 실행은 요구되지 않는다.
