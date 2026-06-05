# Combined Source View Readiness Contract

Status: current minimal Combined identity/source-availability guardrail
Date: 2026-05-19 (KST)

Role: current `Combined` identity/source-availability guardrail, not a broader `Combined` product semantics contract.

이 문서는 첫 minimal `Combined` web surface 이후에도 broader `Combined` product semantics가 닫혀 있어야 하는 조건을 고정한다.

이 결정은 schema, API, runtime, loader, scheduler, DB write, category-to-game trusted mapping, 또는 broader `Combined` semantics 구현 승인이 아니다.

현재 durable context는 `README.md`, `docs/source-inventory.md`, `docs/data-model-spec.md`, `docs/decisions/category-to-game-mapping-contract.md` 를 따른다.

목적은 approved minimal identity/source-availability surface 밖에서 trusted mapping과 serving semantics가 별도 승인될 때까지 broader `Combined` product semantics를 blocked 상태로 유지하는 것이다.

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

- `Combined` 는 web source tab에 존재하며, 현재 minimal identity/source-availability table을 제공한다.
- 이 table은 `GET /combined/games/overview` 만 사용하는 read-only web source surface다.
- Steam source view와 Chzzk source view는 현재 분리되어 있다.
- Chzzk category evidence는 observed source evidence이며 canonical game identity가 아니다.
- Candidate category-to-game evidence는 trusted mapping이 아니다.
- `categoryType=GAME` 은 Chzzk provider category type evidence일 뿐이며 canonical game relationship을 만들지 않는다.

## Blocked-State Rule

Broader `Combined` product semantics는 아래 readiness gates가 모두 별도 승인될 때까지 blocked 상태로 남아야 한다.

- `candidate`, `unresolved`, `rejected` category-to-game evidence는 `Combined` row, KPI, ranking, sorting, game identity를 만들거나 보강하는 데 사용할 수 없다.
- `categoryType=GAME` 만으로는 `Combined` row, canonical game relationship, Steam-Chzzk mapping을 만들 수 없다.
- hidden inferred mapping, synthetic join, fallback mapping, guessed mapping은 허용하지 않는다.
- Approved minimal identity/source-availability fields 밖에서는 trusted mapping과 serving semantics가 승인되기 전까지 `Combined` product semantics가 없다.

`srv_chzzk_category_game_mapping` 같은 internal read-only DB serving view contract는 단독으로 `Combined` readiness gate를 충족하지 않는다.

`GET /chzzk/category-game-mappings` API response shape도 trusted mapping identity rows만 노출하며, 단독으로 `Combined` readiness gate를 충족하지 않는다.

Future backend `Combined` should not need to call `GET /chzzk/category-game-mappings` internally when `srv_chzzk_category_game_mapping` is available as the DB serving view.

Product serving behavior, ranking/KPI semantics, Chzzk metric merge, mapping coverage, and broader `Combined` semantics remain separate Human Gate items.

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

Broader `Combined` product semantics가 blocked 상태인 동안 허용되는 작업은 아래 boundary에 한정한다.

- Public product-semantics blocked explanation
- Durable readiness checklist
- Read-only review 또는 planning-contract follow-up
- Separate Steam and Chzzk source views
- Minimal read-only identity/source-availability table using `GET /combined/games/overview`
- No broader `Combined` product semantics

## Explicit Non-Goals

이 문서는 아래 작업을 승인하거나 구현하지 않는다.

- Broader `Combined` UI implementation beyond the minimal identity/source-availability table
- `Combined` API 또는 response shape changes
- Schema, SQL, migration, DDL
- DB write, backfill, reingest, bootstrap
- Live fetch
- Category-to-game mapping implementation
- Automatic matching
- Trusted mapping usage
- Generalized provider abstraction
- `gold_stream_game_30m`
- KPI formula, ranking/sort semantics, table grain, storage shape, UI field behavior

## Public/Private Boundary

Public docs에는 durable blocked-state/readiness contract만 남긴다.

Public docs에는 raw provider payload, row-level UGC, live title, thumbnail, channel display value, credential, private runtime path, local scheduler evidence, screenshot, scheduler XML/stdout, host/path detail, raw API response를 포함하지 않는다.

이 boundary를 바꾸거나 `Combined` semantics를 구현하려면 별도 approved implementation slice에서 Human Gate를 거치고, 관련 durable docs와 regression tests를 함께 갱신한다.
