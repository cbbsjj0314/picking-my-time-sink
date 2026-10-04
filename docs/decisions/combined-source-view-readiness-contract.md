# Combined Source View Readiness Contract

Status: Useful Combined v1 activity implemented; identity/source-availability guardrail preserved
Date: 2026-10-03 (KST)

Role: 기존 minimal identity/source-availability boundary와 승인된 `Useful Combined v1` activity boundary를 구분한다. 현재 구현 계약은 아래 Phase 1 planning contract 및 Phase 2 implementation 기록과 [metrics definitions §1.6](../metrics-definitions.md#16-useful-combined-v1-7-day-activity-metrics)을 따른다. Score/ranking/recommendation 및 다른 deferred scope는 계속 별도 승인 대상이다.

## Historical implementation boundaries

아래 과거 update는 각 slice 당시의 승인 범위를 기록한다. 현재 activity 구현 상태는 `Useful Combined v1` section을 따른다.

Updated by CATEGORY-MAPPING-COMBINED-SOURCE-VIEW-CONTRACT-001:

이 update는 docs/tests-only planning contract다.

- `Combined` API route, SQL serving view, web data surface, web fetch/hook, mapping coverage panel, product ranking, KPI, score, or recommendation behavior를 구현하지 않는다.
- Proposed future `Combined` row grain은 one row per `dim_game.canonical_game_id` 이다. 이는 future implementation gate의 proposed contract일 뿐이며 현재 API, SQL, web, runtime behavior가 아니다.
- Current Steam contracts must be compared as candidate inputs only. `srv_game_explore_period_metrics`, `/games/explore/overview`, latest CCU, latest price, latest reviews, and latest rankings may be reviewed as a candidate Steam source contract, but none is selected or implemented as the `Combined` source by this update.
- `GET /chzzk/category-game-mappings` and `srv_chzzk_category_game_mapping` are current trusted identity surfaces and may be referenced only as future gated identity input candidates for `Combined`.
- Chzzk viewer metrics are not merged into a `Combined` product table by this update. Chzzk observed fields remain bounded/category evidence and must not imply full live-list population, current unbounded viewers, Steam-equivalent Chzzk baseline, recommendation quality, ranking readiness, KPI readiness, or score semantics.
- Candidate, unresolved, rejected, `categoryType=GAME`, inferred mapping, guessed mapping, hidden fallback mapping, and synthetic joins remain invalid as `Combined` identity.

Updated by CATEGORY-MAPPING-COMBINED-BACKEND-API-CONTRACT-001:

이 update는 이미 승인된 docs/tests-only backend contract boundary를 기록한다.

- 첫 향후 backend `Combined` API contract boundary는 canonical game identity, Steam source availability, nullable trusted Chzzk mapping identity/context fields로 제한한다.
- Proposed future row grain은 one row per `dim_game.canonical_game_id` 로 유지한다. 이는 현재 SQL/API/runtime behavior가 아니며 `Combined` SQL serving view, API route, response model, service query, web fetch/hook, table, mapping coverage panel, DB write/backfill/reingest, scheduler/runtime job, live fetch를 추가하지 않는다.
- 첫 Steam evidence-base contract family는 `srv_game_explore_period_metrics` / `/games/explore/overview` 로 선택한다. 이 선택은 향후 `Combined` 를 위한 evidence-base contract family일 뿐이며 ranking/KPI/score/recommendation source가 아니고 현재 Steam runtime contract도 바꾸지 않는다.
- 최신 CCU, 최신 price, 최신 reviews, 최신 rankings는 별도 승인 전까지 보조/향후 evidence source 후보로만 남긴다.
- 향후 backend service/query boundary의 trusted Chzzk identity input은 `srv_chzzk_category_game_mapping` 이다. `GET /chzzk/category-game-mappings` 는 read-only inspection/API surface로 남기며, `srv_chzzk_category_game_mapping` 을 사용할 수 있을 때 backend-internal dependency로 쓰지 않는다.
- `srv_chzzk_category_game_mapping` 과 `GET /chzzk/category-game-mappings` 만으로 runtime `Combined` readiness가 열리지는 않는다.
- 첫 response boundary는 향후 contract proposal로서 canonical identity fields, Steam source availability, nullable trusted Chzzk mapping identity/context fields만 설명할 수 있다. 구체적인 Pydantic model, OpenAPI schema, route, SQL view, exact runtime payload는 정의하지 않는다.
- Chzzk viewer/channel metrics, `latest_viewers_observed`, `viewer_hours_observed`, `avg_viewers_observed`, `peak_viewers_observed`, `viewer_per_channel_observed`, `unique_channels_observed`, ranking/KPI/score/recommendation semantics, mapping coverage panel, web surface, automatic matching, platform generalization, candidate/unresolved/rejected/fallback mapping exposure는 계속 deferred다.
- Candidate, unresolved, rejected, `categoryType=GAME`, inferred mapping, guessed mapping, fuzzy mapping, hidden fallback mapping, synthetic joins, private/local row evidence, raw provider payloads, automatic matching은 `Combined` identity로 유효하지 않다.

Updated by CATEGORY-MAPPING-COMBINED-MINIMAL-BACKEND-API-001:

이 update는 첫 minimal backend-only read-only `Combined` API slice를 구현한다.

- SQL serving view는 `srv_combined_game_overview` 이고, API route는 `GET /combined/games/overview` 이다.
- Row driver는 `srv_game_explore_period_metrics` 이며, output grain은 selected Steam evidence-base 안의 one row per `dim_game.canonical_game_id` 로 유지한다.
- Trusted Chzzk identity/context input은 DB view `srv_chzzk_category_game_mapping` 이다. Backend service는 `GET /chzzk/category-game-mappings` 를 내부 호출하지 않는다.
- Response fields는 `canonical_game_id`, `canonical_name`, `steam_appid`, `steam_source_available`, `chzzk_mapping_available`, nullable `chzzk_category_id`, nullable `category_name`, nullable `category_type`, nullable `latest_bucket_time` 만이다.
- 동일 `mapped_canonical_game_id` 에 trusted mapping row가 여러 개 있으면 deterministic single-row guard로 한 row만 붙인다. 이 guard는 row-grain safety용이며 representative category, best mapping, primary mapping, ranking, product, coverage semantics가 아니다.
- Chzzk viewer/channel metrics, `latest_viewers_observed`, `viewer_hours_observed`, `avg_viewers_observed`, `peak_viewers_observed`, `viewer_per_channel_observed`, `unique_channels_observed`, ranking/KPI/score/recommendation semantics, mapping coverage fields, candidate/unresolved/rejected/fallback mapping exposure, writes/backfills/scheduler/live fetch, and web data surface는 이 backend-only slice에서는 deferred였다.
- 기존 `/games/explore/overview`, `/chzzk/categories/overview`, and `GET /chzzk/category-game-mappings` source endpoints는 각각의 기존 contract로 남으며, 이 slice는 Chzzk viewer metrics를 `Combined` product semantics로 merge하지 않는다.

Updated by CATEGORY-MAPPING-COMBINED-WEB-SURFACE-001:

이 update는 첫 minimal read-only `Combined` web source surface를 구현한다.

- Web source view는 `GET /combined/games/overview` 만 호출한다.
- Web surface는 identity/source availability table로 제한한다.
- Visible fields는 canonical identity, Steam source availability, nullable trusted Chzzk mapping identity/context, nullable `latest_bucket_time` 이다.
- `latest_bucket_time` 은 nullable trusted Chzzk mapping/context timestamp로만 표시하며 freshness score, popularity, ranking, coverage, viewer activity, or recommendation evidence가 아니다.
- Chzzk viewer/channel metrics, ranking/KPI/score/recommendation semantics, mapping coverage panel, candidate/unresolved/rejected/fallback mapping exposure, backend SQL/API/schema changes, writes/backfills/reingest/scheduler/live fetch는 계속 deferred다.
- `GET /chzzk/category-game-mappings`, `/chzzk/categories/overview`, Steam provider APIs, Chzzk provider/live APIs를 이 web surface에서 호출하지 않는다.
- `PendingSourcePanel` 은 active `Combined` source tab에서 제거된다.

## Current Context

- `Combined` 는 기존 minimal identity/source-availability table과 별도 `Useful Combined v1` activity scatter를 제공한다.
- 이 table은 `GET /combined/games/overview` 만 사용하는 read-only web source surface다.
- Steam source view와 Chzzk source view는 현재 분리되어 있다.
- Chzzk category evidence는 observed source evidence이며 canonical game identity가 아니다.
- Candidate category-to-game evidence는 trusted mapping이 아니다.
- `categoryType=GAME` 은 Chzzk provider category type evidence일 뿐이며 canonical game relationship을 만들지 않는다.

## Blocked-State Rule

승인된 `Useful Combined v1` activity 밖의 broader `Combined` product semantics는 아래 readiness gates가 별도 승인될 때까지 blocked 상태로 남는다.

- `candidate`, `unresolved`, `rejected` category-to-game evidence는 `Combined` row, KPI, ranking, sorting, game identity를 만들거나 보강하는 데 사용할 수 없다.
- `categoryType=GAME` 만으로는 `Combined` row, canonical game relationship, Steam-Chzzk mapping을 만들 수 없다.
- hidden inferred mapping, synthetic join, fallback mapping, guessed mapping은 허용하지 않는다.
- Approved minimal identity/source-availability 및 `Useful Combined v1` activity 밖의 trusted mapping과 serving semantics는 추가 승인이 필요하다.

`srv_chzzk_category_game_mapping` 같은 internal read-only DB serving view contract는 단독으로 `Combined` readiness gate를 충족하지 않는다.

`GET /chzzk/category-game-mappings` API response shape도 trusted mapping identity rows만 노출하며, 단독으로 `Combined` readiness gate를 충족하지 않는다.

현재 Combined backend는 `srv_chzzk_category_game_mapping` DB view를 사용하며 `GET /chzzk/category-game-mappings`를 내부 호출하지 않는다.

아래 승인된 game-bucket Chzzk metric merge와 activity serving 이외의 ranking/KPI, mapping coverage, broader `Combined` semantics는 별도 Human Gate 대상이다.

## Readiness Gates

나중에 broader `Combined` product semantics를 blocked 상태 밖으로 옮기려면 아래 조건을 checklist 수준에서 모두 만족해야 한다.

- Trusted category-to-game mapping contract와 promotion rules가 승인되어야 한다.
- Serving semantics가 별도 승인되어야 한다.
- API response shape가 별도 승인되어야 한다.
- Untrusted Chzzk category evidence가 canonical game identity로 취급되지 않음을 증명하는 regression tests가 있어야 한다.
- Public/private evidence boundary가 유지되어야 한다.
- Human Gate approval이 필요하다.
- Implementation ticket은 관련 durable docs와 tests를 같은 slice에서 갱신해야 한다.

## Allowed While Product Semantics Are Blocked

승인된 `Useful Combined v1` 밖의 product semantics는 blocked 상태다. 현재 허용된 boundary는 다음과 같다.

- Public product-semantics blocked explanation
- Durable readiness checklist
- Read-only review 또는 planning-contract follow-up
- Separate Steam and Chzzk source views
- Minimal read-only identity/source-availability table using `GET /combined/games/overview`
- 아래 승인된 `Useful Combined v1` activity SQL/API/scatter
- No broader `Combined` product semantics beyond the approved v1

## Explicit Non-Goals

승인된 v1 밖의 다음 작업은 범위 밖이다.

- 추가 Combined UI/API/metric semantics
- Live schema/view application, migration/DDL execution
- DB write, backfill, reingest, bootstrap
- Live fetch 및 collector expansion
- Category-to-game mapping creation/promotion/expansion, automatic matching
- Generalized provider abstraction, `gold_stream_game_30m`
- KPI formula, score, ranking, recommendation

## Useful Combined v1 — Phase 1 planning contract

Proposal date: 2026-10-03 (KST)

Status: Implemented — Human Gate Approved. Phase 1 contract를 승인된 Phase 2 SQL/API/Web slice로 구현했다. 기존 minimal identity/source-availability contract는 유지한다. Checked-in serving definition은 live DB에 적용하지 않았다.

### Authority / phase boundary

- Human Gate Required: Yes. Human Decision Status: Approved. Human Gate status: Approved.
- Approval evidence: [Human-authored approval on PR #185](https://github.com/cbbsjj0314/picking-my-time-sink/pull/185#issuecomment-5968328872). Reviewed Phase 1 HEAD는 `a052d582d93ee1ab511d498491e6c430fcc19d2f`다. 이 human-authored GitHub PR comment와 별도의 explicit implementation handoff가 동일 branch / Draft PR의 bounded Phase 2 구현을 승인했다. Canonical ticket은 필요하지 않다.
- Phase 2 implementation: Implemented and merged via PR #185 — checked-in SQL serving definition, separate API, minimal web scatter, docs/lineage/regression evidence. PR #185는 squash merge되었다.
- Independent Review Status: Passed — [Fresh-context independent review evidence](https://github.com/cbbsjj0314/picking-my-time-sink/pull/185#issuecomment-5968984373). Reviewed Phase 2 implementation HEAD는 `12a8dd1b50ed43cebaadea25a6584e8fe5f7d7df`이며 final status는 `Passed — Useful Combined v1 Phase 2`다.
- Live DB application, live DB/provider diagnostics, collector expansion, DB write/backfill/reingest/bootstrap, scheduler/runtime mutation, trusted mapping mutation, private planning-state/checkpoint sync는 범위 밖이다. PR #185 merge와 Fresh-context review Passed는 production/live PostgreSQL application approval을 의미하지 않으며, live DB application은 계속 별도 authority가 필요하다.

### Product question / universe

첫 surface는 다음 질문에 답하는 것을 목표로 한다.

> 현재 PMTS가 추적하면서 trusted Chzzk mapping도 가진 게임 중, 최근 7일 Steam에서는 많이 플레이되고 Chzzk의 bounded live sample에서도 많이 관측된 게임은 무엇인가?

Product row는 `srv_game_explore_period_metrics`의 active Steam tracked games (`tracked_game.is_active = true`) 중 trusted Chzzk category mapping이 최소 1개 있는 게임으로 제한한다. Grain은 one row per `dim_game.canonical_game_id`다. 관측이 없더라도 trusted-mapped game은 이 universe에 남는다.

Trusted identity input은 `srv_chzzk_category_game_mapping`이다. Candidate, unresolved, inferred, guessed, fuzzy, rejected, hidden fallback mapping, synthetic joins, `categoryType=GAME` alone은 product identity가 아니다. 이 contract는 trusted mapping creation/promotion/expansion이나 automatic matching을 승인하지 않는다.

### Shared window / separate activity dimensions

- Shared anchor는 기존 Steam `ccu_period_anchor_date`다. Seven KST dates는 `anchor_date - 6` through `anchor_date`, inclusive다. Chzzk evidence도 이 window의 KST half-hour buckets로 제한한다. Chzzk에 독립적인 두 번째 “latest 7 days” anchor를 만들지 않는다.
- Primary Steam signal은 `period_avg_ccu_7d`, supporting signal은 `period_peak_ccu_7d`다. `srv_game_explore_period_metrics`의 기존 daily-rollup formula, metric-wide anchor, full-window/null semantics를 재사용한다.
- Chzzk는 bounded observed activity다. Fields와 formula, unit, null rule은 [metrics definitions §1.6](../metrics-definitions.md#16-useful-combined-v1-7-day-activity-metrics)을 따른다. Full Chzzk population activity, estimated 또는 complete Chzzk viewer-hours를 주장하지 않는다.
- Multiple trusted categories는 canonical game + `bucket_time`으로 먼저 합친다. Category `concurrent_sum`을 SUM한 하나의 `game_bucket_observed_viewers`를 만든 후 7일 집계를 한다. 기존 alphabetical deterministic single-mapping guard는 identity row-grain safety일 뿐이며 activity semantic으로 재사용하지 않는다.
- `chzzk_observed_bucket_count_7d`는 merge 이후 distinct game buckets를 세고 category bucket counts를 합산하지 않는다. `chzzk_peak_viewers_observed_7d`는 merged game-bucket 값의 MAX다.
- `chzzk_collection_bucket_count_7d`는 shared window에서 `fact_chzzk_category_30m`에 persisted global category-fact evidence가 있는 distinct `bucket_time` 수다. 특정 게임이나 trusted categories에 제한한 분모가 아니다. 고정 `336`은 game visibility denominator로 사용하지 않는다.
- 관측이 없는 게임은 observed count가 `0`이고, collection denominator가 양수일 때만 observation ratio가 `0`이다. Denominator가 `0`이면 ratio는 null이다. Viewer-hours, peak viewers, selected-window latest observed bucket은 null로 남기고 `Not observed in bounded sample`로 해석한다. Viewers/viewer-hours `0`, “no Chzzk streams” 또는 full-population-zero 의미를 합성하지 않는다. Persisted observed zero bucket은 실제 관측된 zero로 구분한다.
- Weighted `PMTS score`, one-dimensional combined ranking, recommendation score, unexplained Steam/Chzzk weighting을 만들지 않는다. Steam activity와 Chzzk bounded-observed activity는 별도 dimensions다.

### Phase 2 backend / UI implementation

`srv_combined_game_overview`와 `GET /combined/games/overview`는 기존 minimal identity/source-availability meaning, universe, response fields를 유지한다. Activity product path는 별도 boundary인 `srv_combined_game_activity_7d` / `GET /combined/games/activity`로 구현한다. `CombinedGameActivityResponse`는 canonical identity, shared anchor, §1.6 metrics와 `bounded_sample_caveat`만 노출한다. Latest field는 `chzzk_latest_observed_bucket_7d`다. API는 canonical ID ascending order와 기본 50 / 최대 200의 transport limit을 사용하며 ranking 의미를 부여하지 않는다. DB serving view가 있는 trusted identity를 위해 backend가 mapping API를 내부 호출하지 않는다.

현재 UI는 기존 `Combined` view 안의 linear scatter plot 하나다. 별도 activity client/hook이 activity endpoint를 읽으며 overview fetch 의미는 유지한다. Each point represents one game: x-axis는 Steam `period_avg_ccu_7d`, y-axis는 `chzzk_viewer_hours_observed_7d`다. 두 값이 모두 존재하는 게임만 plot한다. Chzzk observation이 없는 게임을 y=0으로 plot하지 않으며, Combined surface의 다른 위치에 `Not observed in bounded sample` 상태로 남길 수 있다. 실제 observed zero는 y=0이 될 수 있다.

목적은 Steam-vs-Chzzk 관계를 시각적으로 살펴보는 것이다. 현재 identity table은 그대로 남기며 broad Combined-page redesign, 추가 cards/dashboard/recommendations, multiple charts는 v1 필수 범위가 아니다.

### Phase 2 evidence / exclusions

`029_srv_combined_game_activity_7d.sql`, Combined activity API, 별도 web client/hook/view-model/scatter와 focused SQL/API/web/docs regressions가 구현 계약을 보호한다. SQL behavioral tests는 synthetic in-memory DuckDB에서 checked-in view definition을 실행한다. Live/production PostgreSQL 실행 증거는 아니며 DDL application은 별도 authority가 필요하다. 기존 overview view/model/endpoint/identity table의 의미는 유지한다.

Shared anchor가 null이면 window-derived Chzzk 값은 모두 null이다. Anchor가 있고 collection bucket이 없으면 counts는 0, ratio/viewer-hours/peak/latest는 null이다. Persisted observed zero는 미관측과 구분한다. 새 activity lineage는 `docs/data-governance.md`에 overview lineage와 별도로 기록한다.

Collector pagination/page count, provider fetch, scheduler/runtime configuration, DB writes/DDL execution, backfill/reingest/bootstrap, trusted mapping creation/promotion/expansion, score/ranking/recommendation, watchlist/personal-interest model, Twitch/generalized provider abstraction은 범위 밖이다. `bounded_sample`과 public/private evidence boundary는 유지한다.

## Public/Private Boundary

Public docs에는 durable activity/identity contract와 deferred scope의 readiness boundary만 남긴다.

Public docs에는 raw provider payload, row-level UGC, live title, thumbnail, channel display value, credential, private runtime path, local scheduler evidence, screenshot, scheduler XML/stdout, host/path detail, raw API response를 포함하지 않는다.

이 boundary를 바꾸거나 `Combined` semantics를 구현하려면 별도 approved implementation slice에서 Human Gate를 거치고, 관련 durable docs와 regression tests를 함께 갱신한다.
