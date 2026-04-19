# Data Governance

문서 목적: Steam-only MVP 데이터 의미, 품질, freshness, lineage, public/local 경계를 최소 거버넌스 기준으로 고정
버전: v0.1 (MVP data governance baseline)
작성일: 2026-04-19 (KST)

## 0. 현재 범위

- current MVP governance scope는 Steam-only runtime baseline이다.
- 이 문서는 데이터 거버넌스의 durable public 기준을 설명한다.
- 상세 metric formula는 `docs/metrics-definitions.md` 를 따른다.
- 테이블 grain, column meaning, layer contract는 `docs/data-model-spec.md` 를 따른다.
- source endpoint, probe, fixture boundary는 `docs/source-inventory.md` 를 따른다.
- exact local schedule, private DB smoke, runtime artifact path, host-specific evidence는 `docs/local/` 에서 관리한다.

## 1. Public repo에 남길 것

Public repo에는 재현 가능한 데이터 의미와 리뷰 가능한 계약을 둔다.

- 지표 정의:
    - metric name, grain, anchor, formula, comparison baseline, unit, null rule.
    - 예: current CCU Δ는 직전 버킷이 아니라 전일 동일 KST 30분 버킷 대비다.
- 데이터 모델 계약:
    - table/view name, grain/PK, nullable policy, upsert/idempotence rule, source provenance.
    - schema/API/data semantics 변경 시 durable docs와 regression tests를 같은 slice에서 갱신한다.
- Bronze/Silver/Gold 역할:
    - raw response preservation, normalized evidence, serving-ready facts/views의 책임 경계.
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

Local/private 경계는 운영 세부, 민감 정보, 원문성이 큰 자료를 담는다.

- exact local scheduler:
    - Windows Task Scheduler task name, exact run time, host path, WSL command, one-off activation note.
- live runtime evidence:
    - DB freshness query output, local API smoke result, run id, scratch artifact path, local logs.
- raw captures:
    - third-party raw JSON/HTML, UGC-heavy payload, large probe dumps, ambiguous source captures.
- secrets and local config:
    - API keys, tokens, cookies, session values, `.env`, private endpoints, personal absolute paths.
- operational ownership detail:
    - personal contact, escalation note, temporary operator assignment, local incident scratch notes.
- non-public quality investigations:
    - live data anomaly triage with sensitive paths, raw payload excerpts, private DB counts.

Local-only material can be summarized back into public docs once it becomes a durable contract and has been sanitized.

## 3. Naming and layer governance

Canonical naming lives in `docs/data-model-spec.md`; this section records the governance intent.

- SQL names use lower snake case.
- Provider-specific facts keep the provider in the table name, such as `fact_steam_ccu_30m`.
- Do not introduce generalized provider tables before a real second provider slice requires them.
- `dim_` stores canonical dimensions.
- `fact_` stores bucket/snapshot facts at a declared grain.
- `agg_` stores rollups derived from facts.
- `srv_` stores serving/API read models.
- Time-window fields include the window suffix, such as `_7d`, `_30d`, or `_90d`.
- Absolute and percent deltas use `_abs` and `_pct`.
- Ratio differences that are percentage points use `_pp`, not `_pct`.
- Public API field names should stay close to serving/view field names unless the API contract explicitly maps them.

## 4. Quality checks

Minimum quality gates for current MVP:

- Schema contract:
    - SQL DDL tests cover table/view shape when schema meaning changes.
    - API response tests preserve nullable evidence fields and reject fake fallback semantics.
- Duplicate/idempotence:
    - fact loaders upsert by declared grain key.
    - repeated runs for the same bucket/snapshot should be safe unless a source contract explicitly says otherwise.
- Null and missing evidence:
    - missing source evidence is not silently converted into zero, free, unavailable, or synthetic score.
    - field-level missing values remain null or skipped evidence according to the table contract.
- Parser drift:
    - public sanitized fixtures guard parser shape.
    - raw provider captures remain local/private unless sanitized and needed for regression.
- Job status:
    - distinguish success, partial success, lock-busy skip, and hard failure.
    - useful rows may load during partial success; triage counts should explain what was skipped or missing.
- Non-finite values:
    - `NaN` and `Infinity` do not cross serving/API boundaries as numeric values.

## 5. Freshness expectations

Public freshness rules describe what should be true, not exact host scheduling.

| Data family | Expected cadence | Public stale rule |
| --- | --- | --- |
| Steam CCU | 30분 | latest bucket should usually be within 2 hours of current KST time. |
| Steam price KR | 1시간 | latest bucket should usually be within 4 hours of current KST time. |
| Steam reviews | daily | latest snapshot should be available for the current or previous KST date after the daily run window. |
| Steam rankings | daily | latest snapshot should be available for the current or previous KST date after the daily run window. |
| Steam App Catalog | weekly or ad hoc | freshness SLA is deferred until weekly automation becomes part of the live baseline. |

Local monitoring may use stricter thresholds, exact scheduler windows, or host-specific smoke queries, but those details belong under `docs/local/`.

## 6. Minimal lineage

This is the current public lineage map for the Steam-only MVP.

| Surface | Serving object | Upstream data | Job boundary |
| --- | --- | --- | --- |
| Latest CCU API / UI | `srv_game_latest_ccu` | `fact_steam_ccu_30m` | `ccu-30m`: fetch CCU, bronze to silver, silver to gold |
| Explore CCU period metrics | `srv_game_explore_period_metrics` | `agg_steam_ccu_daily`, `fact_steam_ccu_30m` | `ccu-30m`: includes daily CCU rollup maintenance |
| Latest price API / UI | `srv_game_latest_price` | `fact_steam_price_1h` | `price-1h`: fetch price, bronze to silver, silver to gold |
| Latest reviews API / UI | `srv_game_latest_reviews` | `fact_steam_reviews_daily` | `daily`: fetch reviews, bronze to silver, silver to gold |
| Latest KR top selling API / UI | `srv_rank_latest_kr_top_selling` | `fact_steam_rank_daily` | `daily`: ranking payload refresh and payload to gold |
| Explore overview table | `srv_game_explore_period_metrics` | active `tracked_game`, latest CCU, price, reviews, period facts/rollups | `ccu-30m`, `price-1h`, `daily` |
| Tracked universe | `tracked_game`, `game_external_id`, `dim_game` | Steam ranking payloads, optional completed App Catalog evidence | `daily`, optional `app-catalog-weekly` |

If a new chart or API surface is added, add at least one lineage row before or with implementation.

## 7. Deferred governance scope

The following are intentionally not part of the current MVP implementation:

- 본격적인 데이터 카탈로그 UI.
- owner/steward 역할 체계의 세밀한 분리.
- 세부 권한 정책 자동화.
- 감사 로그 체계 고도화.
- 분류 체계와 태깅 체계의 정교화.

Revisit these when one of the following becomes true:

- multiple collaborators need separate data ownership or approval workflows.
- public/private data boundaries are no longer obvious from directory and docs structure.
- a second real provider produces durable facts and serving surfaces.
- external users rely on the data as a contract rather than as an MVP evidence browser.
- compliance, incident response, or production deployment requirements become explicit.

## 8. Change checklist

Use this checklist when changing schema, API, ingestion, metrics, or serving semantics.

- Does the metric definition include formula, grain, anchor, unit, comparison baseline, and null rule?
- Does the table/view contract define grain, primary/unique key, nullable policy, and upsert behavior?
- Is the source boundary public and durable, while raw/private evidence stays local?
- Does the change preserve Bronze/Silver/Gold responsibility boundaries?
- Are quality checks or regression tests updated with the semantic change?
- Is freshness expectation affected?
- Is minimal lineage affected?
- Are deferred governance items still deferred, or has a trigger made one necessary?
