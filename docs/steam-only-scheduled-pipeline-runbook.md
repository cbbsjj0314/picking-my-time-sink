문서 목적: Steam-only scheduled pipeline의 durable flow와 데이터 계약을 고정
버전: v0.10 (observability metric boundary)
작성일: 2026-04-20 (KST)

## 0. 현재 범위

- current runtime scope는 Steam-only 이다.
- 이 문서는 public durable reference로서 pipeline 단계, 데이터 흐름, schema/API 의미를 설명한다.
- local 실행 명령, scratch artifact path, DB 확인 쿼리, local runtime verification 절차는 public contract가 아니며 `docs/local/` runbook에서 관리한다.
- current MVP baseline은 external scheduler / cron / systemd 등이 호출할 수 있는
  thin cadence-aware CLI job boundary를 포함한다.
- Scheduler service, heavy DAG runtime, Docker deployment, object storage handoff는
  current live requirement가 아니다.
- Dagster orchestration and Garage/S3-compatible artifact storage are target
  directions, not current live requirements for this pipeline contract.
- Prometheus/Grafana metrics are a local observability companion for scheduler
  and DB freshness evidence. They do not change this Steam-only scheduler
  contract and do not move Steam ingest/API/Postgres runtime into Docker.
- DuckDB batch recompute, dbt Core modeling, Loki logs, and ClickHouse
  historical OLAP are not current live requirements for this Steam-only
  scheduler contract.
- If adopted later, these tools must preserve this boundary: Postgres remains
  the current serving/metadata baseline until a separate schema/API/runtime
  slice changes that contract.
- Chzzk/Twitch provider 확장, Combined synthesis, generalized provider abstraction은 이 pipeline contract 밖이다.

## 1. Pipeline 단계

1. Ranking payload refresh
   - Steam ranking service에서 KR/global top sellers와 most played payload를 수집한다.
   - payload는 tracked universe seed와 ranking gold upsert의 공통 입력이다.
2. Tracked universe update
   - ranking seed를 병합해 `dim_game`, `game_external_id`, `tracked_game`를 갱신한다.
   - current MVP에서 `tracked_game.is_active = true` 는 serving eligibility와 downstream Steam fetch eligibility를 함께 뜻한다.
3. Ranking gold upsert
   - refreshed ranking payload를 `fact_steam_rank_daily`에 적재한다.
   - `snapshot_date`는 ranking payload artifact의 KST date anchor를 사용한다.
4. Price branch
   - active Steam target의 KR 가격 snapshot을 1시간 bucket fact로 적재한다.
   - current public API region contract는 `KR` casing이다.
   - primary request는 `filters=price_overview` 를 유지한다.
   - primary request는 active appid를 batch로 묶어 `appids=<a>,<b>,...` 로 보낸다. 기본 batch 크기는 100이며 `fetch_price_1h --batch-size` 로 바꿀 수 있다.
   - batch 응답은 앱별로 나눠 bronze row마다 기존과 같은 `{"<appid>": {...}}` 형태의 `payload` 로 둔다. `primary.request` 에는 실제로 보낸 batch의 `appids` 와 `batch_size` 를 남긴다.
   - batch request가 최종 실패하거나 응답에 앱 key가 없으면, 그 앱은 같은 filter의 단건 request로 보완한다.
   - primary `appdetails` 가 성공했지만 `price_overview` 가 없을 때만 같은 `cc=kr`, `l=koreana` context의 no-filter full `appdetails` fallback을 앱별 단건으로 호출한다.
   - fallback full payload의 `data.is_free is true` 만 grounded free title evidence로 적재하며, numeric price fields는 null로 보존한다.
   - 1차 pass 뒤에도 fetch 최종 실패인 앱은 마지막에 한 번 더 수집한다(re-collect pass).
   - Price job의 모든 Steam request는 직전 request 종료 뒤 최소 간격(기본 1.5초, `--min-request-interval-sec`)을 지킨다. 재시도도 같은 간격을 따른다.
   - HTTP 429에 delta-seconds `Retry-After` 가 있으면 그 시간(상한 기본 60초, `--max-retry-after-sec`)만큼 기다린다. 헤더가 없거나 해석할 수 없으면 기존 지수 backoff를 쓴다.
   - Fetch 시작부터 시간 상한(기본 1500초, `--time-budget-sec`)이 지나면 새 request를 보내지 않는다. 남은 앱은 `time_budget_exceeded` 로 기록하고 job은 정상 종료한다. 상한을 넘기는 대기는 하지 않으므로 초과분은 마지막 request 하나의 timeout 이내다.
   - 이 pacing은 price job 안에서만 적용한다. 공유 `request_with_retry` 의 기본 retry 동작과 다른 job은 바뀌지 않는다.
   - Scheduler는 추가 인자 없이 `price-1h` 를 호출하므로 위 기본값이 운영 동작이다.
5. Reviews branch
   - active Steam target의 all-language / all-purchase cumulative review snapshot을 daily fact로 적재한다.
6. CCU branch
   - active Steam target의 current players snapshot을 30분 bucket fact로 적재한다.
7. CCU daily rollup maintenance
   - `fact_steam_ccu_30m`을 KST daily rollup인 `agg_steam_ccu_daily`로 재계산한다.

## 2. Data Flow

- Ranking payloads feed both tracked universe maintenance and `fact_steam_rank_daily`.
- `tracked_game.is_active = true` selects downstream price, reviews, and CCU fetch targets.
- Price, reviews, and CCU branches write independent facts and do not synthesize cross-source metrics during ingest.
- Serving views read fact tables and rollups to expose latest evidence and Explore overview fields.
- `agg_steam_ccu_daily` supports daily CCU period metrics; strict raw CCU activity metrics still require complete 30분 bucket coverage.

## 3. Durable Contracts

- `tracked_game.is_active`
  - Current Steam-only MVP uses this flag for both active serving and downstream Steam fetch eligibility.
  - Existing tracked rows that disappear from a ranking seed are not automatically deleted by the ranking updater.
  - Completed App Catalog evidence can deactivate ranking seed appids that are absent from the completed catalog snapshot.
  - Cadence-job `partial_success` triage does not by itself flip `is_active`, imply stale culling, or reclassify the job as a hard failure.
  - Warm grace, stale culling, and fetch-only lifecycle states are not current rules.
- Ranking facts
  - KR and global rankings are stored separately.
  - Unmapped appids may remain with `canonical_game_id = null` until mapping exists.
- Price facts
  - Current slice is KR only.
  - Latest price serving treats legacy lowercase `kr` rows as KR evidence while public API output remains `KR`.
  - Paid rows require `price_overview.currency`, `initial`, `final`, and `discount_percent`.
  - Grounded free rows require fallback full `appdetails` `data.is_free is true`; `currency_code`, `initial_price_minor`, `final_price_minor`, and `discount_percent` stay null.
  - Missing `price_overview`, fallback `is_free=false`, invalid JSON, HTTP failure, and unsuccessful payloads are not converted into free/unavailable/region-blocked/delisted meaning.
  - Bronze row의 `fetch_failure` 는 재시도와 re-collect 뒤에도 Steam의 앱별 응답을 얻지 못한 "fetch 최종 실패"만 `{"stage": "primary" | "fallback", "reason": ...}` 로 기록한다. 실패가 아니면 `null` 이다.
    - `reason`: `rate_limited`(429), `server_error`(5xx), `http_error`(그 밖의 HTTP 실패), `timeout`, `network_error`, `invalid_json`, `missing_key`, `time_budget_exceeded`
    - 무료 후보의 fallback request가 위 이유로 실패하면 `stage: "fallback"` 이다.
  - `success:false`, fallback `is_free=false`, `price_overview` 없음은 Steam의 정상 응답이다. Fetch 실패가 아니며, 지금처럼 silver에서 제외될 뿐이다.
  - Bronze row의 `fetch_trail` 은 앱별로 보낸 batch / single / fallback request의 pass와 결과를 순서대로 남기는 triage용 보조 field다. Silver/gold 변환은 이 field를 읽지 않는다.
- Reviews facts
  - Current reviews series uses `json=1`, `filter=all`, `language=all`, `purchase_type=all`, and bounded page size.
  - Gold facts preserve cumulative totals; broader review history and alternate filter series need a separate schema/ingest slice.
- CCU facts
  - 30분 buckets are interpreted in KST.
  - Missing or invalid rows can be represented as skipped/missing evidence before gold insertion.
  - Daily rollup rows store `avg_ccu` and `peak_ccu`; bucket coverage completeness metadata is not part of the current rollup.

## 4. Cadence

- Ranking refresh: daily.
- Reviews snapshot: daily.
- Price snapshot: hourly.
- CCU snapshot: 30m.
- App Catalog full snapshot: weekly or ad hoc, optional for the current Steam-only scheduled baseline.

Exact local run times are scheduler/config responsibility, not public data semantics.

Current cadence-aware operation boundary:

- `ccu-30m`: `fetch_ccu_30m -> bronze_to_silver_ccu -> silver_to_gold_ccu -> gold_to_agg_ccu_daily`.
- `price-1h`: `fetch_price_1h -> bronze_to_silver_price -> silver_to_gold_price`.
- `daily`: `run_tracked_universe_scheduled -> payload_to_gold_rankings -> fetch_reviews_daily -> bronze_to_silver_reviews -> silver_to_gold_reviews`.
- `app-catalog-weekly`: optional weekly/ad hoc App Catalog fetch that maintains the existing latest summary consumer boundary for tracked universe updates.

The single-command Steam wrapper remains a one-shot manual handoff baseline and is not the 30m scheduler path.

Cadence jobs should expose local/private result, log, execution meta, and no-overlap lock evidence. Exact paths, host-specific schedule, and local smoke commands belong in `docs/local/`.

`ccu-30m`은 daily rollup recompute/upsert와 stale aggregate-row reconciliation을 수행하되, 매 run마다 full-history `ccu.daily-rollup-result.jsonl`을 생성하지 않는다. Compact rollup evidence는 기존 `result.json`의 rollup step `records_out` / `paths.meta`, `triage.rollup_records`, job status와 execution meta로 남긴다. Rollup step meta는 `records_in`, `records_out`, `success`, error 정보를 유지하며, step `paths`에는 생성하지 않은 rollup `result` 경로를 포함하지 않는다.

Full row-level JSONL이 필요한 diagnostic/debug 작업은 `gold_to_agg_ccu_daily.run(result_path=...)` 또는 해당 CLI의 `--result-path`를 명시한다. 이 boundary는 DB recompute/upsert도 수행하므로 read-only export가 아니다. 기존 historical artifact는 삭제하거나 다시 쓰지 않는다. `retained_ccu_rollup_probe`는 남아 있는 full rollup artifact와 비교할 수 있지만, latest retained rollup이 최신 cadence run의 결과라는 보장은 없다. Full rollup artifact가 없으면 `latest_rollup=null`, `comparison.compared=false`로 보고하며, artifact가 없는 run을 `compare_run_id`로 지정하면 오류를 반환한다. One-shot manual wrapper의 기존 output 동작은 유지한다.

Windows desktop hosts may use Windows Task Scheduler to invoke `wsl.exe`, with
the actual cadence command still running inside the WSL2 Linux runtime. That
keeps `.env` loading, Poetry execution, local artifacts, and the current Linux
no-overlap lock boundary on the existing WSL path instead of introducing a
native Windows Python/Poetry scheduler path. Host-specific task names, schedules,
repo paths, and scheduler-triggered evidence remain local/private operations
details.

`price-1h` 는 fetch 최종 실패 앱이 1개 이상이면 `partial_success` 다. Triage에는 `fetch_failed_records`, reason별 `fetch_failure_reasons`, `partial_reason: "price_fetch_failed"` 를 남긴다. 실패가 0이면 `success` 이고 `partial_reason` 은 `null` 이다. `success:false` 나 `is_free=false` 만 있는 run은 `success` 다. Fetch step execution meta에는 실제 HTTP request 수(`request_count`), request 단위로 센 `rate_limit_count` / `retry_count`, `fetch_failed_records`, `time_budget_exceeded` 를 남긴다. Exit code 규칙은 바뀌지 않는다(`partial_success` → 0).

Active 앱 약 280개 기준으로 평소 price fetch는 batch 3회와 무료 후보 fallback 수십 회, 합계 약 60회 request로 2분 안팎이다. 429나 timeout이 계속되는 최악의 경우에도 시간 상한(1500초)과 request 하나의 timeout 안에서 끝난다.

CCU per-app missing evidence is not the same as a hard job failure. A CCU fetch can produce useful bronze/gold rows while recording missing app-level evidence such as 404/empty/invalid payloads. Operators should distinguish full success, partial success, lock-busy skip, and hard failure from job-level result/meta evidence.

Prometheus-facing scheduler metrics should preserve that same distinction:
`success`, `partial_success`, `lock_busy`, and `hard_failure` are separate
status values. Per-app CCU missing evidence, daily reviews skipped evidence, and
price fetch final failures are partial-success triage signals, not automatic
hard-failure semantics.
Current chronic partial-success rows are therefore operator-trust signals inside
the tracked evidence eligibility boundary, not automatic serving blockers or
lifecycle-state changes.

## 5. Public Verification Boundary

- Public validation should focus on schema/API contracts, fact/upsert idempotence, null-preserving serving semantics, and fixture-backed parser behavior.
- Local runtime verification may check live DB rows, local API responses, and web rendering, but those commands and endpoint details belong in `docs/local/`.
- Runtime artifacts, execution meta, raw probe captures, and operator scratch paths are local/private by default.

## 6. Existing DB Apply Note

Existing local/dev databases created before the free-title fallback contract need an explicit `fact_steam_price_1h` ALTER before free rows can load. Fresh schema creation uses `sql/postgres/012_fact_steam_price_1h.sql`.

Minimum existing-table migration shape:

```sql
ALTER TABLE fact_steam_price_1h
    ALTER COLUMN currency_code DROP NOT NULL,
    ALTER COLUMN initial_price_minor DROP NOT NULL,
    ALTER COLUMN final_price_minor DROP NOT NULL,
    ALTER COLUMN discount_percent DROP NOT NULL;

ALTER TABLE fact_steam_price_1h
    DROP CONSTRAINT IF EXISTS fact_steam_price_1h_currency_code_non_empty,
    DROP CONSTRAINT IF EXISTS fact_steam_price_1h_initial_price_minor_non_negative,
    DROP CONSTRAINT IF EXISTS fact_steam_price_1h_final_price_minor_non_negative,
    DROP CONSTRAINT IF EXISTS fact_steam_price_1h_discount_percent_range,
    DROP CONSTRAINT IF EXISTS fact_steam_price_1h_price_evidence_shape;

ALTER TABLE fact_steam_price_1h
    ADD CONSTRAINT fact_steam_price_1h_currency_code_non_empty
        CHECK (currency_code IS NULL OR BTRIM(currency_code) <> ''),
    ADD CONSTRAINT fact_steam_price_1h_initial_price_minor_non_negative
        CHECK (initial_price_minor IS NULL OR initial_price_minor >= 0),
    ADD CONSTRAINT fact_steam_price_1h_final_price_minor_non_negative
        CHECK (final_price_minor IS NULL OR final_price_minor >= 0),
    ADD CONSTRAINT fact_steam_price_1h_discount_percent_range
        CHECK (
            discount_percent IS NULL
            OR (discount_percent >= 0 AND discount_percent <= 100)
        ),
    ADD CONSTRAINT fact_steam_price_1h_price_evidence_shape
        CHECK (
            (
                is_free IS TRUE
                AND currency_code IS NULL
                AND initial_price_minor IS NULL
                AND final_price_minor IS NULL
                AND discount_percent IS NULL
            )
            OR (
                is_free IS DISTINCT FROM TRUE
                AND currency_code IS NOT NULL
                AND initial_price_minor IS NOT NULL
                AND final_price_minor IS NOT NULL
                AND discount_percent IS NOT NULL
            )
        );
```

## 7. Deferred

- Host-specific scheduler/timer files and exact local run schedules.
- Prometheus/Grafana alerting and on-call operations.
- DuckDB runtime wiring for rollup/recompute/backfill.
- S3-compatible artifact exchange, including Garage target storage and Parquet
  artifact layout.
- dbt Core mart/test/docs wiring.
- Dagster orchestration runtime, jobs/assets, schedules, sensors, checks, and
  backfills.
- Loki centralized logs.
- ClickHouse historical OLAP engine before a proven bottleneck.
- Price unavailable / delisted / region-blocked / age-gated semantics expansion.
- Reviews generalized history / parameter expansion.
- Broader CCU history / generalized date-range serving.
- Chzzk/Twitch provider expansion and real streaming integration.
