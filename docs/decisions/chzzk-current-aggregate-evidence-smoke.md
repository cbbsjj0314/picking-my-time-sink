# Chzzk Current Aggregate Evidence Smoke

Status: docs-only public-safe checkpoint
Ticket: CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001
Date: 2026-05-23 (KST)

## Purpose

이 문서는 `CHZZK-CURRENT-AGGREGATE-EVIDENCE-SMOKE-001`의 후속 public-safe checkpoint다.

이전 Codex-only smoke는 `unknown / insufficient local access`로 종료되었다. 이후 human-run read-only aggregate smoke가 sanitized aggregate evidence를 제공했으므로, 이 문서는 raw/private evidence를 공개하지 않고 current API/DB aggregate 결과만 요약한다.

## Evidence Source Boundary

- Source: human-run read-only aggregate smoke를 public-safe aggregate evidence로 요약한 결과.
- API boundary: local read-only API listener was available, API docs route returned HTTP `200`, and `/chzzk/categories/overview?limit=200` returned HTTP `200`.
- DB boundary: read-only aggregate checks confirmed the relevant Chzzk fact relations and aggregate counts.
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
- Reason: human-run read-only aggregate smoke가 current API and DB freshness/coverage를 public-safe aggregate 수준에서 확인했다.
- Still blocked: mapping implementation, candidate generation, mapping storage, trusted mapping, serving changes, and `Combined`.
- Next recommended action: real observed-data candidate implementation 전에는 별도 Human Gate와 test-only guardrails를 포함한 후속 ticket을 연다.

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

Interpretation:

- `coverage_status_distribution` and boolean count fields may differ because `coverage_status` is a mutually exclusive display/status field, while boolean fields can overlap.
- `bounded_sample_caveat=bounded_sample` remains the bounded sample / live-list completeness caveat.
- These values do not prove full live-list completeness or pagination exhaustion.
- These values do not create full 1d/7d product metric semantics beyond observed bucket-count candidate flags.

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

Interpretation:

- These are aggregate-only facts.
- They do not expose raw category ids, category names, channel ids, channel names, live titles, thumbnails, raw provider payloads, or row-level UGC.
- They support current freshness and aggregate coverage visibility.
- They do not authorize category-to-game mapping implementation by themselves.

## Coverage / Freshness Interpretation

The current API/DB aggregate evidence is fresh enough to reduce the previous `unknown / insufficient local access` blocker for public-safe documentation.

This checkpoint supports a public-safe aggregate evidence record, but it does not prove:

- full live-list completeness
- pagination exhaustion
- full 1d/7d product semantics
- trusted category-to-game mapping readiness

`bounded_sample_caveat=bounded_sample` remains separate from bucket coverage status. Bucket coverage status describes observed bucket availability per category; bounded sample caveat describes live-list / pagination completeness risk.

## Category Stability

Confirmed aggregate facts show:

- blank category id count: `0`
- blank category name count: `0`
- blank category type count: `0`
- categories with type variation count: `0`
- categories with name variation count: `0`

Interpretation:

- These aggregate checks improve confidence that the current observed category aggregate is usable for coverage/freshness discussion.
- `categoryType=GAME` remains provider category type evidence, not canonical game identity.
- The aggregate checks do not resolve alias, renamed category, regional title, same-name collision, or franchise collision questions for category-to-game review.

## Channel Evidence Availability

Confirmed aggregate facts show:

- `fact_chzzk_category_channel_30m` exists: true
- channel fact row count: `40213`
- distinct category count with channel evidence: `383`
- channel bucket time max: `2026-05-23 16:00:00+09`

Interpretation:

- Channel evidence is available as aggregate category-channel evidence.
- This does not expose channel ids, channel names, live titles, thumbnails, or row-level UGC.
- Channel evidence remains nullable observed evidence for `/chzzk/categories/overview`; it does not create trusted mapping or canonical game semantics.

## Serving Separation

`/chzzk/categories/overview` remains category-only observed evidence.

This checkpoint does not change endpoint behavior, response shape, API fields, UI fields, sorting, filtering, table columns, route behavior, serving semantics, or source-view semantics.

`candidate`, `unresolved`, and `rejected` remain untrusted review evidence states. `trusted` / `approved` remain future Human Gate terminology only.

`Combined` remains blocked/pending until trusted mapping, serving semantics, API response shape, regression expectations, and Human Gate are separately approved.

## Mapping Implication

This evidence improves current coverage/freshness visibility for Chzzk observed category aggregates.

It does not by itself approve:

- category-to-game mapping implementation
- candidate generation
- mapping storage
- trusted mapping
- automatic matching
- API/web/serving changes
- `Combined`

Before real observed-data candidate implementation, a later ticket still needs explicit Human Gate and likely test-only guardrails around candidate/trusted/Combined leakage.

## Public / Private Safety

This checkpoint intentionally records aggregate-only evidence.

It does not include raw command transcript, shell prompt, `.env` loading command, DB credential command shape, raw SQL block, raw `psql` output, raw API response, raw JSON row, raw provider payload, category/channel/display value, live title, thumbnail, screenshot, credential, secret value, private path, scheduler XML/stdout, raw runtime log, raw Grafana/Prometheus response, or row-level UGC.

## Deferred Items

- category-to-game candidate generation implementation
- mapping storage selection and implementation
- trusted mapping and promotion/demotion rules
- automatic matching
- schema/API/data semantics changes
- API/web/serving changes
- `Combined` readiness and semantics
- live fetch, scheduler mutation, DB write, backfill, reingest, DDL, migration
- raw/private evidence promotion
- generalized provider abstraction

## Validation Expectations

For this docs-only checkpoint:

- Reread this document after editing.
- Check for stale claim, scope creep, and private data exposure.
- Run `git diff --check`.
- Run `git status --short`.
- Search docs for forbidden implementation claims and public-safety risks, then manually inspect allowed boundary wording.
- `./scripts/check.sh` is not required because this change does not alter runtime/code paths.
