# 데이터 거버넌스

문서 목적: Steam-only MVP의 데이터 의미, 품질, freshness, lineage, public/local 경계를 최소 거버넌스 기준으로 고정한다.  
버전: v0.5 (Chzzk probe result contract hardening boundary)  
작성일: 2026-04-20 (KST)

## 0. 현재 범위

- 현재 MVP governance scope는 Steam-only runtime baseline이다.
- Chzzk live-list fixture/parser/DDL 후보는 provider-specific 준비 산출물이다. 현재 runtime scope를 Steam-only 밖으로 넓히지 않는다.
- 이 문서는 데이터 거버넌스의 durable public 기준을 설명한다.
- 상세 metric formula는 `docs/metrics-definitions.md` 를 따른다.
- table grain, column meaning, layer contract는 `docs/data-model-spec.md` 를 따른다.
- source endpoint, probe, fixture boundary는 `docs/source-inventory.md` 를 따른다.
- exact local schedule, private DB smoke, runtime artifact path, host-specific evidence는 `docs/local/` 에서 관리한다.

## 1. Public repo에 남길 것

Public repo에는 재현 가능한 데이터 의미와 리뷰 가능한 계약을 둔다.

- 지표 정의:
  - metric name, grain, anchor, formula, comparison baseline, unit, null rule.
  - 예: current CCU Δ는 직전 bucket이 아니라 전일 동일 KST 30분 bucket 대비다.
- 데이터 모델 계약:
  - table/view name, grain/PK, nullable policy, upsert/idempotence rule, source provenance.
  - schema/API/data semantics가 바뀌면 durable docs와 regression tests를 같은 slice에서 갱신한다.
- Bronze/Silver/Gold 역할:
  - raw response preservation, normalized evidence, serving-ready facts/views의 책임 경계를 둔다.
- 데이터 품질 기준:
  - null 허용/불허, duplicate key handling, schema drift detection, parser fixture regression, missing evidence handling.
- Freshness 기준:
  - public에는 cadence-level expectation과 stale 판단 원칙을 둔다.
  - exact scheduler times, task names, local query output은 public contract가 아니다.
- 최소 lineage:
  - 주요 chart/API surface가 어떤 serving object, fact/agg table, job boundary를 거치는지 기록한다.
- Sanitized fixtures:
  - parser/ingest regression에 필요한 최소 representative fixture만 둔다.
  - token, cookie, personal header, UGC 원문, private host detail은 제거한다.
- Deferred governance scope:
  - 지금 의도적으로 하지 않는 data catalog UI, 세밀한 steward role, 권한 자동화, 고도화된 audit logging, 정교한 taxonomy/tagging을 명시한다.

## 2. Local/private로 관리할 것

Local/private 경계에는 운영 세부사항, 민감 정보, 원문성이 큰 자료를 둔다.

- 정확한 local scheduler 정보:
  - Windows Task Scheduler task name, 정확한 실행 시각, host path, WSL command, 일회성 activation note.
- live runtime 근거:
  - DB freshness query output, local API smoke result, run id, scratch artifact path, local logs.
- 원문 capture:
  - third-party raw JSON/HTML, UGC-heavy payload, large probe dumps, ambiguous source captures.
- secret과 local config:
  - API keys, tokens, cookies, session values, `.env`, private endpoints, personal absolute paths.
- 운영 소유권 세부사항:
  - personal contact, escalation note, temporary operator assignment, local incident scratch notes.
- 비공개 품질 조사:
  - sensitive path, raw payload excerpt, private DB count가 포함된 live data anomaly triage.

Local-only material은 durable contract가 되고 sanitized 처리된 뒤에만 public docs로 요약할 수 있다.

## 3. Naming and layer governance

Canonical naming은 `docs/data-model-spec.md` 에 둔다. 이 섹션은 governance intent만 기록한다.

- SQL names는 lower snake case를 쓴다.
- Provider-specific facts는 `fact_steam_ccu_30m` 처럼 table name에 provider를 둔다.
- 실제 두 번째 provider slice가 필요해지기 전에는 generalized provider tables를 만들지 않는다.
- `dim_` 은 canonical dimensions를 저장한다.
- `fact_` 는 선언된 grain의 bucket/snapshot facts를 저장한다.
- `agg_` 는 facts에서 파생한 rollups를 저장한다.
- `srv_` 는 serving/API read models를 저장한다.
- Time-window fields에는 `_7d`, `_30d`, `_90d` 같은 window suffix를 붙인다.
- Absolute delta와 percent delta는 `_abs`, `_pct` 를 쓴다.
- Percentage point 차이는 `_pct` 가 아니라 `_pp` 를 쓴다.
- Public API field names는 API contract가 명시적으로 매핑하지 않는 한 serving/view field names와 가깝게 유지한다.

## 4. Quality checks

현재 MVP의 최소 quality gates는 아래와 같다.

- Schema contract:
  - schema meaning이 바뀌면 SQL DDL tests가 table/view shape를 검증한다.
  - API response tests는 nullable evidence fields를 보존하고 fake fallback semantics를 거부한다.
- Duplicate/idempotence:
  - fact loaders는 선언된 grain key로 upsert한다.
  - source contract가 다르게 말하지 않는 한 같은 bucket/snapshot의 repeated runs는 안전해야 한다.
- Null and missing evidence:
  - missing source evidence를 zero, free, unavailable, synthetic score로 조용히 바꾸지 않는다.
  - field-level missing values는 table contract에 따라 null 또는 skipped evidence로 남긴다.
- Parser drift:
  - public sanitized fixtures로 parser shape를 보호한다.
  - raw provider captures는 sanitized 처리되고 regression에 필요할 때만 public으로 승격한다.
- Job status:
  - success, partial success, lock-busy skip, hard failure를 구분한다.
  - partial success 중에도 useful rows가 load될 수 있다. triage counts는 skipped/missing 항목을 설명해야 한다.
- Non-finite values:
  - `NaN` 과 `Infinity` 는 numeric value로 serving/API boundaries를 넘지 않는다.

## 5. Freshness expectations

Public freshness rules는 정확한 host scheduling이 아니라 기대 상태를 설명한다.

| Data family | Expected cadence | Public stale rule |
| --- | --- | --- |
| Steam CCU | 30분 | latest bucket은 보통 현재 KST 기준 2시간 이내여야 한다. |
| Steam price KR | 1시간 | latest bucket은 보통 현재 KST 기준 4시간 이내여야 한다. |
| Steam reviews | daily | daily run window 이후에는 current 또는 previous KST date의 latest snapshot이 있어야 한다. |
| Steam rankings | daily | daily run window 이후에는 current 또는 previous KST date의 latest snapshot이 있어야 한다. |
| Steam App Catalog | weekly or ad hoc | weekly automation이 live baseline에 들어올 때까지 freshness SLA는 deferred다. |

Local monitoring은 더 엄격한 thresholds, exact scheduler windows, host-specific smoke queries를 쓸 수 있다. 해당 세부사항은 `docs/local/` 아래에 둔다.

## 6. Minimal lineage

아래는 현재 Steam-only MVP의 public lineage map이다.

| Surface | Serving object | Upstream data | Job boundary |
| --- | --- | --- | --- |
| Latest CCU API / UI | `srv_game_latest_ccu` | `fact_steam_ccu_30m` | `ccu-30m`: fetch CCU, bronze to silver, silver to gold |
| Explore CCU period metrics | `srv_game_explore_period_metrics` | `agg_steam_ccu_daily`, `fact_steam_ccu_30m` | `ccu-30m`: includes daily CCU rollup maintenance |
| Latest price API / UI | `srv_game_latest_price` | `fact_steam_price_1h` | `price-1h`: fetch price, bronze to silver, silver to gold |
| Latest reviews API / UI | `srv_game_latest_reviews` | `fact_steam_reviews_daily` | `daily`: fetch reviews, bronze to silver, silver to gold |
| Latest KR top selling API / UI | `srv_rank_latest_kr_top_selling` | `fact_steam_rank_daily` | `daily`: ranking payload refresh and payload to gold |
| Explore overview table | `srv_game_explore_period_metrics` | active `tracked_game`, latest CCU, price, reviews, period facts/rollups | `ccu-30m`, `price-1h`, `daily` |
| Tracked universe | `tracked_game`, `game_external_id`, `dim_game` | Steam ranking payloads, optional completed App Catalog evidence | `daily`, optional `app-catalog-weekly` |

Chzzk `fact_chzzk_category_30m` 은 provider-specific DDL/parser candidate에서
local/private `category-result.jsonl` artifact-to-Postgres write path로 승격되었다.
아직 live fetch write boundary, serving read model, API, UI, canonical game mapping lineage가 없다.

Chzzk bounded pagination/temporal raw captures는 local/private로 유지한다.
live row에 category id/name/type이 없으면 current category fact candidates는 unknown category를 만들지 않고 skip evidence를 기록한다.
Public fixtures는 synthetic/sanitized 상태를 유지하며 raw UGC-heavy provider payloads를 포함하지 않는다.

Local/private Chzzk temporal probe summaries에는 반복 비교를 위한 sanitized run-level reporting fields를 둘 수 있다.
예시는 `run_status`, `result_status`, `failure.kind`, `failure.http_status_code`, `pagination.bounded_page_cutoff`, `pagination.last_page_next_present`, `skip_counts`, `coverage.status` 다.
이 fields는 skip/pagination/failure/coverage caveats를 설명하지만 raw payloads, UGC-heavy evidence, public API/UI semantics를 승격하지 않는다.

Chzzk category-result-to-gold loader summary는 local/private operator evidence다.
Summary는 input/valid/skipped/upsert-attempt/committed/failed row counts, skip reason
counts, bucket min/max, unique category count, and sanitized failure reason만 담는다.
`ON CONFLICT` upsert 때문에 inserted row와 updated row는 구분하지 않는다.
Summary에는 raw row contents, actual category/channel names, live title, thumbnail,
raw provider payload, credentials, or DB environment details를 넣지 않는다.

첫 Chzzk source-view semantics는 category-only category evidence browser semantics다.
`categoryType=GAME` 은 Chzzk category evidence이지 Steam game mapping이 아니다.
`viewer_hours_observed`, `avg_viewers_observed`, `peak_viewers_observed`, `live_count_observed_total`, optional `unique_channels_observed` 같은 observed sample metrics는 category/channel result artifacts에서 정의할 수 있다.
다만 observed naming 또는 동등한 caveat를 유지해야 하며, strict/full 1d 또는 7d metrics를 대체하지 않는다.

Full Chzzk 1d/7d source-view metrics에는 category별 distinct KST half-hour bucket coverage가 각각 48/336 buckets 필요하다.
failed, partial, malformed, empty, missing-result runs는 coverage에 포함하지 않는다.
bounded page cutoff 또는 last-page next cursor evidence가 남아 있으면 product/public semantics에서 pagination exhaustion 또는 full live-list population을 주장하면 안 된다.
별도 implementation and semantics slice 없이는 이 candidates를 game semantics, Combined/relationship metrics, uncaveated API/UI fields로 승격하지 않는다.

새 chart 또는 API surface를 추가하면 implementation 전 또는 같은 slice 안에서 lineage row를 최소 1개 추가한다.

## 7. Deferred governance scope

아래 항목은 현재 MVP implementation 범위가 아니다.

- 본격적인 data catalog UI.
- owner/steward 역할 체계의 세밀한 분리.
- 세부 권한 정책 자동화.
- audit logging 고도화.
- taxonomy/tagging 정교화.

아래 조건 중 하나가 충족되면 다시 검토한다.

- multiple collaborators가 별도 data ownership 또는 approval workflows를 필요로 한다.
- public/private data boundaries가 directory/docs 구조만으로 분명하지 않다.
- 두 번째 real provider가 durable facts와 serving surfaces를 만든다.
- external users가 데이터를 MVP evidence browser가 아니라 contract로 의존한다.
- compliance, incident response, production deployment 요구가 명시된다.

## 8. Change checklist

schema, API, ingestion, metrics, serving semantics를 바꿀 때 아래 항목을 확인한다.

- metric definition에 formula, grain, anchor, unit, comparison baseline, null rule이 있는가?
- table/view contract에 grain, primary/unique key, nullable policy, upsert behavior가 있는가?
- source boundary는 public and durable이고, raw/private evidence는 local에 남는가?
- Bronze/Silver/Gold responsibility boundaries를 보존하는가?
- semantic change에 맞춰 quality checks 또는 regression tests를 갱신했는가?
- freshness expectation에 영향이 있는가?
- minimal lineage에 영향이 있는가?
- deferred governance items는 여전히 deferred인가, 아니면 필요한 trigger가 생겼는가?
