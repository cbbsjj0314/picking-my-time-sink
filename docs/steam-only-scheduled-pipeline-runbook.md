문서 목적: Steam-only scheduled pipeline의 durable flow와 데이터 계약을 고정
버전: v0.6 (public docs / probe boundary cleanup)
작성일: 2026-04-17 (KST)

## 0. 현재 범위

- current runtime scope는 Steam-only 이다.
- 이 문서는 public durable reference로서 pipeline 단계, 데이터 흐름, schema/API 의미를 설명한다.
- local 실행 명령, scratch artifact path, DB 확인 쿼리, local runtime verification 절차는 public contract가 아니며 `docs/local/` runbook에서 관리한다.
- scheduler automation / external scheduling은 current MVP baseline에 포함하지 않는다.
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
  - Warm grace, stale culling, and fetch-only lifecycle states are not current rules.
- Ranking facts
  - KR and global rankings are stored separately.
  - Unmapped appids may remain with `canonical_game_id = null` until mapping exists.
- Price facts
  - Current slice is KR only.
  - Latest price serving treats legacy lowercase `kr` rows as KR evidence while public API output remains `KR`.
  - Free-title fallback semantics remain deferred.
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

## 5. Public Verification Boundary

- Public validation should focus on schema/API contracts, fact/upsert idempotence, null-preserving serving semantics, and fixture-backed parser behavior.
- Local runtime verification may check live DB rows, local API responses, and web rendering, but those commands and endpoint details belong in `docs/local/`.
- Runtime artifacts, execution meta, raw probe captures, and operator scratch paths are local/private by default.

## 6. Deferred

- App Catalog external scheduling operationalization.
- Parquet / MinIO artifact exchange.
- Price free / unavailable semantics expansion.
- Reviews generalized history / parameter expansion.
- Broader CCU history / generalized date-range serving.
- Chzzk/Twitch provider expansion and real streaming integration.
