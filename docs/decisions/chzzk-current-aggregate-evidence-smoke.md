# Chzzk Current Aggregate Evidence Smoke

Status: docs-only public-safe checkpoint
Ticket: CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001
Date: 2026-05-23 (KST)

## Purpose

이 문서는 `CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001`의 후속 public-safe checkpoint다.

이전 Codex-only smoke는 `unknown / insufficient local access`로 종료되었다.

이후 human-run read-only aggregate smoke가 sanitized aggregate evidence를 제공했으므로, 이 문서는 raw/private evidence를 공개하지 않고 current API/DB aggregate 결과만 요약한다.

## Evidence Source Boundary

- Source: human-run read-only aggregate smoke를 public-safe aggregate evidence로 요약한 결과이다.
- API boundary: local read-only API listener를 사용할 수 있었고, API docs route가 HTTP `200`을 반환했으며, `/chzzk/categories/overview?limit=200`이 HTTP `200`을 반환했다.
- DB boundary: read-only aggregate check를 통해 관련 Chzzk fact relation 및 aggregate count를 확인했다.
- Public boundary: 이 문서는 raw command transcript, raw API response, raw JSON rows, raw SQL blocks, raw `psql` output, raw provider payload, row-level UGC, credential, `.env` value, private path, scheduler XML/stdout, raw runtime log, screenshot, raw Grafana/Prometheus response, category/channel/display value, live title, thumbnail을 포함하지 않는다.

## Explicit Non-Goals

이 checkpoint는 아래 항목을 승인하거나 구현하지 않는다.

- category-to-game mapping implementation, candidate generation, mapping storage, trusted mapping, automatic matching
- schema, SQL, DDL, migration, DB write, backfill, reingest, bootstrap, loader/runtime/scheduler 변경
- API endpoint, response shape, API field, web UI, route, table column, sort/filter/search, serving semantics 변경
- `Combined` semantics, API, UI, KPI, ranking, sorting, relationship interpretation
- generalized provider abstraction, App Catalog, tracked_universe, Price/Reviews wiring
- raw/private evidence promotion 또는 public fixture/example 생성

## Result

- Result: `public-safe aggregate evidence available`
- Reason: human-run read-only aggregate smoke가 current API 및 DB freshness/coverage를 public-safe aggregate 수준에서 확인했다.
- Still blocked: mapping implementation, candidate generation, mapping storage, trusted mapping, serving 변경 사항 및 `Combined`는 여전히 차단(blocked) 상태로 남겨둔다.
- Next recommended action: real observed-data candidate implementation을 진행하기 전에는 별도의 Human Gate와 test-only guardrails를 포함한 후속 ticket을 연다.

## API Aggregate Summary

Confirmed aggregate facts:

- API aggregate result: `available`
- `/chzzk/categories/overview?limit=200`: HTTP `200`
- API row count: `200`
- API distinct category id count: `200`
- latest API bucket max: `2026-05-23T16:00:00+09:00`
- API freshness age: `0.65` hours
- bounded sample caveat distribution: `bounded_sample`: `200`
- category type distribution: `GAME`: `189`, `ENTERTAINMENT`: `2`, `SPORTS`: `4`, `ETC`: `5`
- coverage status distribution: `observed_bucket_only`: `2`, `partial_window`: `123`, `full_1d_candidate_available`: `63`, `full_7d_candidate_available`: `12`
- `full_1d_candidate_available_count`: `75`
- `full_7d_candidate_available_count`: `12`
- missing 1d bucket count min/max: `0` / `47`
- missing 7d bucket count min/max: `0` / `335`
- blank category id count: `0`
- blank category name count: `0`
- blank category type count: `0`
- unknown or extra field count: `0`
- forbidden field present: `false`

Interpretation (해석):

- `coverage_status_distribution`과 boolean count 필드는 서로 다를 수 있다. `coverage_status`는 상호 배타적인 표시/상태(display/status) 필드인 반면, boolean 필드는 서로 중첩될 수 있기 때문이다.
- `bounded_sample_caveat=bounded_sample`은 제한된 샘플(bounded sample) 및 live-list completeness에 대한 경고(caveat) 조항으로 유지된다.
- 이 값들이 전체 live-list completeness나 pagination exhaustion(페이지네이션 소진)을 증명하는 것은 아니다.
- 이 값들은 관측된 bucket-count candidate flag를 넘어선 완전한 1d/7d product metric semantics를 생성하지 않는다.

## DB Aggregate Summary

Confirmed aggregate facts:

- DB reachable: yes
- `fact_chzzk_category_30m` exists: true
- `fact_chzzk_category_channel_30m` exists: true
- distinct Chzzk category count in category fact: `383`
- DB latest bucket max: `2026-05-23 16:00:00+09`
- DB freshness age: `0.65` hours
- DB coverage status counts: `observed_bucket_only`: `36`, `partial_window`: `272`, `full_1d_candidate_available`: `63`, `full_7d_candidate_available`: `12`
- DB missing 1d bucket count min/max: `0` / `47`
- DB missing 7d bucket count min/max: `0` / `335`
- categories with type variation count: `0`
- categories with name variation count: `0`
- channel fact row count: `40213`
- distinct category count with channel evidence: `383`
- channel bucket time max: `2026-05-23 16:00:00+09`

Interpretation (해석):

- 이는 오직 aggregate 전용 팩트(aggregate-only facts)들이다.
- raw category id, category name, channel id, channel name, live title, thumbnail, raw provider payload 또는 row-level UGC를 노출하지 않는다.
- 현재의 freshness 및 aggregate coverage 가시성을 지원한다.
- 이 자체만으로 category-to-game mapping 구현을 승인하는 것은 아니다.

## Coverage / Freshness Interpretation

현재의 API/DB aggregate evidence는 public-safe 문서를 작성하기 위해 이전의 `unknown / insufficient local access` 차단 요인(blocker)을 완화할 수 있을 만큼 충분히 신선(fresh)하다.

본 checkpoint는 public-safe aggregate evidence 기록을 지원하지만, 다음 항목들을 증명하는 것은 아니다:

- 전체 live-list completeness
- pagination exhaustion (페이지네이션 소진)
- 전체 1d/7d product semantics
- trusted category-to-game mapping 준비 상태

`bounded_sample_caveat=bounded_sample`은 bucket coverage status와 분리된 상태로 유지된다. Bucket coverage status는 카테고리별로 관측된 bucket 가용성을 나타내며, bounded sample caveat는 live-list / pagination completeness 위험을 나타낸다.

## Category Stability

Confirmed aggregate facts show:

- blank category id count: `0`
- blank category name count: `0`
- blank category type count: `0`
- categories with type variation count: `0`
- categories with name variation count: `0`

Interpretation (해석):

- 이러한 aggregate check는 현재 관측된 category aggregate가 coverage/freshness 논의에 사용될 수 있다는 신뢰도를 높여준다.
- `categoryType=GAME`은 오직 provider category type evidence로 유지되며, canonical game identity가 아니다.
- 해당 aggregate check는 category-to-game 검토를 위한 alias, renamed category, regional title, same-name collision 또는 franchise collision 문제를 해결하지 않는다.

## Channel Evidence Availability

Confirmed aggregate facts show:

- `fact_chzzk_category_channel_30m` exists: true
- channel fact row count: `40213`
- distinct category count with channel evidence: `383`
- channel bucket time max: `2026-05-23 16:00:00+09`

Interpretation (해석):

- Channel evidence는 aggregate category-channel evidence 형태로 제공된다.
- 이는 channel id, channel name, live title, thumbnail 또는 row-level UGC를 노출하지 않는다.
- Channel evidence는 `/chzzk/categories/overview`에 대한 nullable observed evidence로 유지되며, trusted mapping이나 canonical game semantics를 생성하지 않는다.

## Serving Separation

`/chzzk/categories/overview`는 category-only observed evidence로 남는다.

본 checkpoint는 endpoint 동작, response shape, API 필드, UI 필드, 정렬(sorting), 필터링(filtering), 테이블 컬럼, route 동작, serving semantics 또는 source-view semantics를 변경하지 않는다.

`candidate`, `unresolved` 및 `rejected`는 신뢰할 수 없는 검토 증거 상태(untrusted review evidence states)로 유지된다. `trusted` / `approved`는 오직 향후 Human Gate 용어로만 남겨둔다.

`Combined`는 trusted mapping, serving semantics, API response shape, regression expectations 및 Human Gate가 별도로 승인될 때까지 차단/보류(blocked/pending) 상태로 유지된다.

## Mapping Implication

이 증거는 Chzzk observed category aggregate에 대한 현재의 coverage/freshness 가시성을 향상시킨다.

이 자체만으로 다음 항목들을 승인하는 것은 아니다:

- category-to-game mapping implementation
- candidate generation
- mapping storage
- trusted mapping
- automatic matching
- API/web/serving 변경 사항
- `Combined`

실제 관측 데이터(real observed-data) 기반의 candidate 구현을 진행하기 전에, 향후의 ticket에는 명시적인 Human Gate와 candidate/trusted/Combined 누수(leakage)를 방지하기 위한 test-only guardrails가 여전히 요구된다.

## Public / Private Safety

본 checkpoint는 의도적으로 aggregate 전용 증거(aggregate-only evidence)만을 기록한다.

여기에는 raw command transcript, shell prompt, `.env` loading command, DB credential command shape, raw SQL block, raw `psql` output, raw API response, raw JSON row, raw provider payload, category/channel/display value, live title, thumbnail, screenshot, credential, secret value, private path, scheduler XML/stdout, raw runtime log, raw Grafana/Prometheus response 또는 row-level UGC를 포함하지 않는다.

## Deferred Items

- category-to-game candidate generation implementation
- mapping storage 선택 및 구현
- trusted mapping 및 승격/강등(promotion/demotion) 규칙
- 자동 매칭(automatic matching)
- schema/API/data semantics 변경 사항
- API/web/serving 변경 사항
- `Combined` 준비 상태 및 semantics
- live fetch, scheduler 변경(scheduler mutation), DB write, backfill, reingest, DDL, migration
- raw/private evidence promotion
- 일반화된 제공자 추상화(generalized provider abstraction)

## Validation Expectations

본 문서 전용 체크포인트(docs-only checkpoint)에 대한 검증 사항:

- 편집 후 이 문서를 다시 정독한다.
- 오래된 주장(stale claim), 범위 확장(scope creep) 및 비공개 데이터 노출(private data exposure) 여부를 점검한다.
- `git diff --check`를 실행한다.
- `git status --short`를 실행한다.
- 문서에서 금지된 구현 주장(forbidden implementation claims) 및 public-safety 위험을 검색한 후, 허용된 경계 문구(boundary wording)를 수동으로 검사한다.
- 이번 변경은 runtime/code 경로를 수정하지 않으므로 `./scripts/check.sh` 실행은 요구되지 않는다.
