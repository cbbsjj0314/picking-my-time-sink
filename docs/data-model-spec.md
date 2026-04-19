문서 목적: 테이블/파일 목록 + 그레인(1행 키) + 적재 규칙(증분/스냅샷) + 보존 기준 + repo-grounded provider 확장 경계 기록
버전: v0.12 (data governance documentation baseline)
작성일: 2026-04-19 (KST)

## 0. 레이어 개요

- Bronze: 원본 응답 보존(파싱 최소). 재처리/회귀 테스트의 근거.
- Silver: 분석/집계가 가능한 형태로 정규화(키/타입/시간 기준 정리).
- Gold: 대시보드/서빙 목적의 fact/rollup/snapshot. “쿼리 패턴”을 기준으로 설계.

저장소/엔진 결론:

- Current execution baseline: thin scheduler/CLI path with local/private runtime
  artifacts and Postgres serving facts/views.
- Target orchestration direction: Dagster OSS after the current scheduler
  operations baseline is stable.
- Target object/artifact storage direction: Garage as an S3-compatible store for
  future Bronze/Silver/Gold artifacts. MinIO is no longer the default storage
  direction.
- Portability rule: artifact/storage access should use an S3-compatible
  contract and avoid provider-specific features where possible, so later Amazon
  S3 or GCS XML API/HMAC interoperability remains plausible.
- Parquet remains a candidate artifact format for future object-backed
  Bronze/Silver/long-term snapshots, but current runtime data semantics are not
  changed by this direction.
- DuckDB: 변환/집계 작업(주로 Silver→Gold 산출)
- Postgres: 서빙용 Gold(대시보드/API가 직접 조회하는 테이블/뷰)

### 0.1 데이터 거버넌스 / naming 규칙

- Public governance baseline은 `docs/data-governance.md` 를 따른다.
- SQL object와 column은 lower snake case를 사용한다.
- Provider-specific fact는 provider name을 table name에 포함한다. 예: `fact_steam_ccu_30m`.
- 실제 두 번째 provider가 durable fact/serving surface를 요구하기 전까지 generalized provider table을 만들지 않는다.
- `dim_`: canonical dimension.
- `fact_`: declared grain을 가진 bucket/snapshot fact.
- `agg_`: fact에서 파생된 rollup.
- `srv_`: API/UI가 직접 읽는 serving read model.
- window field는 `_7d`, `_30d`, `_90d` 같은 suffix로 기간을 드러낸다.
- absolute delta는 `_abs`, percent delta는 `_pct`, percentage point delta는 `_pp` suffix를 사용한다.
- nullable column은 source가 실제로 제공하지 않는 값, missing evidence, current contract상 아직 정의되지 않은 의미를 구분할 수 있어야 한다. fake zero/default로 의미를 만들지 않는다.
- schema, grain, nullable policy, source series meaning이 바뀌면 이 문서와 관련 regression tests를 같은 slice에서 갱신한다.

## 1. 공통 시간/키 규칙

- 시간대: KST 기준으로 bucket_time/snapshot_date를 생성/저장
- bucket_time:
    - 30분 수집: HH:00 또는 HH:30으로 정규화
    - 1시간 수집: HH:00 정규화
- snapshot_date:
    - “실행 시각”이 아니라 “KST 날짜” 기준으로 저장(재시도/지연에도 날짜 기준 유지)

## 2. 도메인 키(식별자)

### 2.1 dim_game (canonical_game)

- 목적: 내부 대표 게임 키(canonical_game_id) 관리
- PK: canonical_game_id
- 컬럼(초안):
    - canonical_game_id (PK)
    - canonical_name
    - status (active/merged/deprecated)
    - merged_into_canonical_game_id (nullable)
    - created_at, updated_at

### 2.2 game_external_id (외부 ID 매핑)

- 목적: Steam appid와 향후 streaming provider 외부 ID를 canonical game에 연결
- durable doc facts:
    - current repo-grounded key는 `(source, external_id)` 이다.
    - `source`는 외부 ID namespace를 뜻하며, current runtime에서 실제 사용 중인 값은 `steam` 이다.
    - 향후 streaming 확장 시 `chzzk`, `twitch` 같은 `source` 값을 추가하는 방식으로 진입한다.
- current repo observations:
    - 현재 SQL DDL 기준 persisted 컬럼은 `source`, `external_id`, `canonical_game_id`, `first_seen_at`, `last_seen_at` 이다.
    - 현재 ingest/service query는 모두 `game_external_id.source = 'steam'` 기준으로 동작한다.
- still undecided items:
    - `mapping_status`, `mapping_method`, `confidence`, `evidence_json` 같은 richer mapping metadata는 아직 current schema에 없다.
    - 위 metadata는 실제 streaming provider 연동 또는 수동 매핑 workflow가 시작될 때 별도 slice에서 추가 검토한다.

## 3. tracked_universe (추적 대상 집합)

- 목적: “무거운 수집(details/리뷰/가격)”을 전체가 아니라 추적 대상만 수행
- 테이블: tracked_game (또는 tracked_universe)
- PK(권장): canonical_game_id
- 컬럼(초안):
    - canonical_game_id
    - is_active
    - priority (1~5)
    - sources: steam_rank_kr/global, chzzk_top 등
    - first_seen_at, last_seen_at
    - note
- current repo-grounded Steam-only semantics:
    - current persisted `tracked_game.is_active` 는 serving eligibility 와 price/reviews/ccu fetch eligibility 를 함께 뜻한다.
    - current `srv_game_*` serving views 와 Steam price/reviews/ccu fetchers 는 모두 `tracked_game.is_active = true` 만 읽는다.
    - `is_active = false` row는 삭제되지 않고 historical facts도 남을 수 있지만, current active serving views와 downstream Steam price/reviews/ccu fetch 대상에서는 제외된다.
    - 따라서 current MVP에서 `is_active` 는 lifecycle phase, cooldown, warm grace 상태가 아니다.
    - ranking seed updater는 completed App Catalog latest summary가 가리키는 full snapshot JSONL을 읽을 수 있을 때만 catalog-driven active filter를 적용한다.
    - current thin slice에서는 ranking seed appid가 그 snapshot에 없으면 row를 삭제하지 않고 `tracked_game.is_active = false` 로 upsert 한다.
    - summary가 없거나 incomplete/unreadable 이면 기존처럼 non-blocking 으로 건너뛴다.
    - current ranking seed에 더 이상 나타나지 않는 기존 tracked row는 이 updater가 자동 deactivate/delete 하지 않는다.
    - 오래 관측되지 않은 row에 대한 staleness cull rule은 없다. `tracked_game.last_seen_at` 은 updater가 처리한 current ranking candidate의 관측 시각 기록이며, 현재 fetch cadence나 serving lifecycle을 결정하지 않는다.
    - warm 7일 rule은 current serving active rule 이 아니며, current `tracked_game.is_active` 를 직접 바꾸는 rule로 구현하지 않는다.
    - warm 7일이 필요해지면 `is_active` 와 분리된 lifecycle/fetch-cadence 상태(예: lifecycle state 또는 warm-until/fetch eligibility)를 먼저 정의한 뒤 별도 schema/code/test slice에서 구현한다.
    - 그 전까지 warm 7일은 fetch-only grace proposal/deferred 항목으로만 취급한다.

## 4. Fact / Snapshot (Gold 중심)

아래는 “1행 키(그레인)”를 확정하는 목적의 테이블 초안이다.

### 4.1 Steam CCU (30분)

- 테이블: fact_steam_ccu_30m
  (Postgres + future S3-compatible Parquet artifact path when implemented)
- 그레인/PK: (canonical_game_id, bucket_time)
- 컬럼(초안):
    - canonical_game_id
    - bucket_time
    - ccu
    - collected_at
    - source_appid (추적/디버그용)
- strict `Estimated Player-Hours` semantics:
    - 이 raw 30분 bucket series가 strict `estimated_player_hours_Nd` 의 source of truth다.
    - canonical formula는 `SUM(ccu * bucket_duration_hours)` 이며, 현재 30분 bucket은 `bucket_duration_hours = 0.5` 로 계산한다.
    - selected/previous N-day window는 각각 expected KST half-hour bucket `48 * N` 개가 모두 있어야 full coverage다.
    - missing bucket, partial history, per-game older anchor fallback, gap fill, synthetic score는 허용하지 않는다.
    - 이 metric은 Steam public CCU 기반 근사 activity metric이며 unique players, sales, ownership, playtime telemetry가 아니다.
    - current `srv_game_explore_period_metrics` / `/games/explore/overview` 는 7d strict fields를 raw 30분 bucket 기준으로 노출한다.

### 4.2 Streaming Category Metrics (30분) — Provider 확장 entry (초안)

- durable doc facts:
    - current MVP runtime은 Steam-only 이며, streaming fact/serving object는 아직 repo에 구현되지 않았다.
    - streaming 확장 시작점은 provider-specific probe/ingest 와 category-level 30분 fact다.
    - 첫 provider-specific 후보는 Chzzk category live-list source다.
    - 첫 fact 방향은 provider-specific `fact_chzzk_category_30m` 후보이며, generalized streaming fact/table은 만들지 않는다.
    - canonical game 기준 서빙 shape는 provider raw/category 수집 이후의 downstream 단계다.
- current repo observations:
    - 현재 repo에는 `src/chzzk`, `src/twitch`, streaming probe sample, streaming DDL이 없다.
    - 현재 재사용 가능한 공통 경계는 `game_external_id` 매핑과 `tracked_game.sources` provenance다.
- first provider-specific fact direction:
    - `fact_chzzk_category_30m`
    - 그레인/PK: `(chzzk_category_id, bucket_time)`
    - source boundary: Chzzk live/category payload에서 category id/name, live concurrent, channel id/name을 category-level evidence로 정규화한다.
    - 컬럼 후보: `chzzk_category_id`, `bucket_time`, `category_name`, `concurrent_sum`, `live_count`, `top_channel_id`, `top_channel_name`, `top_channel_concurrent`, `collected_at`
    - upsert rule 후보: 같은 `(chzzk_category_id, bucket_time)` 재실행은 row를 대체하되, raw/probe payload와 execution metadata는 별도로 보존한다.
- raw/probe/ingest responsibility boundary:
    - probe/raw: representative payload와 수집 메타데이터를 local/private 경계에 보존한다. current slice에서는 real Chzzk API call, auth, token/cookie handling을 구현하지 않는다.
    - ingest: 한 Chzzk payload를 category 30분 fact row로 정규화한다.
    - ingest가 하지 않는 것: `canonical_game_id` 확정, `game_external_id` 자동 매핑, `gold_stream_game_30m`, serving API, web UI, Combined/relationship metric 생성.
- real integration 전 필요 조건:
    - sanitized parser fixture 확보
    - Chzzk auth/quota/runtime contract 확인
    - `fact_chzzk_category_30m` DDL과 parser/upsert regression test 동시 추가
    - category-to-game mapping workflow를 별도 schema/code slice로 고정
- explicitly deferred:
    - Twitch fallback, generalized provider abstraction, `gold_stream_game_30m`, streaming serving API, web dashboard streaming UI wiring, Combined/relationship KPI

### 4.3 Steam Price (1시간)

- 테이블: fact_steam_price_1h
- 그레인/PK: (canonical_game_id, bucket_time, region)
- 컬럼(초안):
    - canonical_game_id
    - bucket_time
    - region (MVP: KR만, write path는 `KR` casing으로 정규화)
    - currency_code (paid price row는 required, grounded free row는 null)
    - initial_price_minor (paid price row는 required, grounded free row는 null)
    - final_price_minor (paid price row는 required, grounded free row는 null)
    - discount_percent (paid price row는 required, grounded free row는 null)
    - is_free (fallback full `appdetails` 의 `data.is_free is true` 일 때만 true, paid row는 nullable/non-true)
    - collected_at
- price evidence contract:
    - Paid row는 Steam `price_overview.currency`, `initial`, `final`, `discount_percent` 가 모두 loadable일 때만 생성한다.
    - Free row는 filtered primary `appdetails` 가 성공했지만 `price_overview` 를 제공하지 않았고, no-filter fallback full `appdetails` 에서 `data.is_free is true` 로 확인될 때만 생성한다.
    - Free row에는 source가 제공하지 않은 `currency_code`, `initial_price_minor`, `final_price_minor`, `discount_percent` 를 fake `KRW` / `0` / `0%` 로 채우지 않는다.
    - `price_overview` 없음, fallback `is_free=false`, missing/invalid fallback, unsuccessful payload는 free/unavailable/region-blocked/delisted 의미로 해석하지 않고 row를 만들지 않는다.
- current serving compatibility:
    - `srv_game_latest_price` 는 기존 lowercase `kr` fact도 KR fact로 읽고, public serving/API `region`은 `KR`로 고정한다.

### 4.4 Steam Reviews Snapshot (1일)

- 테이블: fact_steam_reviews_daily
- 그레인/PK: (canonical_game_id, snapshot_date)
- current source contract:
    - Steam `appreviews` query summary cumulative snapshot
    - request params: `filter=all`, `language=all`, `purchase_type=all`, `num_per_page=20`
- 컬럼(초안):
    - canonical_game_id
    - snapshot_date
    - total_reviews
    - total_positive
    - total_negative
    - positive_ratio (total_positive / total_reviews)
    - collected_at
    - current DDL에는 language/filter/purchase_type 파라미터 기록용 컬럼이 없다.
- period-derived candidates:
    - `reviews_added_7d`, `reviews_added_30d`, `period_positive_ratio_7d`, `period_positive_ratio_30d` 와 previous same-length comparison fields는 cumulative daily boundary snapshot 차이로 계산할 수 있다.
    - exact formula와 null handling은 `docs/metrics-definitions.md` 의 `Explore review period-derived candidates` 를 따른다.
    - current fact는 위 후보 계산에 필요한 cumulative totals를 담고 있지만, source series provenance를 DB에 보존하지는 않는다.
- future schema implication:
    - `filter`, `language`, `purchase_type` 별 review series를 동시에 보존해야 하면 이 테이블의 grain/PK와 ingest path를 별도 slice에서 확장한다.
    - current canonical all/all/all series만 다루는 동안에는 schema 변경 없이 current derived serving view/API path를 유지할 수 있다.

### 4.5 Steam Ranking Snapshot (1일)

- 테이블: fact_steam_rank_daily
- 그레인/PK: (snapshot_date, market, rank_type, rank_position)
- current repo observations:
    - current gold path input은 ranking refresh가 쓰는 local/private runtime payload 4종이다.
    - current payload contract는 raw Steam JSON만 저장하므로, `collected_at`은 runtime artifact file mtime(UTC)로 고정한다.
    - `snapshot_date`는 위 artifact write time을 KST로 변환한 날짜로 저장한다.
- 컬럼:
    - snapshot_date
    - market (KR/global)
    - rank_type (top_selling/top_played 등)
    - rank_position (1..N)
    - steam_appid
    - canonical_game_id (current Steam mapping이 있으면 채움, 없으면 NULL 허용)
    - collected_at
- 적재 메모:
    - current PK upsert는 `(snapshot_date, market, rank_type, rank_position)` 기준 재실행 안전성을 전제로 한다.

## 5. Rollup / Serving Views (대시보드 쿼리 패턴)

### 5.1 “최신 스냅샷” 서빙 테이블(권장)

- 목적: API에서 실시간 집계 대신 “미리 계산된 결과”를 읽게 함
- 예시:
    - srv_game_latest_ccu: game별 최신 bucket_time의 ccu + Δ(전일 동일 버킷)
    - srv_game_latest_price: game별 최신 KR bucket_time 가격 스냅샷
    - srv_game_latest_reviews: game별 최신 snapshot_date의 positive_ratio + Δ(전일)
    - srv_rank_latest_kr_top_selling: current minimum path의 최신 KR top-selling 랭킹 리스트
    - srv_game_explore_period_metrics: 현재 최소 `Explore` 개요 근거 테이블용 기간 지표 묶음
    - broader KR/global + top_selling/top_played serving split은 후속 slice에서 필요 시 확장

### 5.2 Explore 기간 지표 서빙 객체

- 현재 runtime에는 `Explore` table shell이 있고, backend/API 7d metric fields는 current web table default surface까지 연결되어 있다.
- 서빙 객체는 `srv_game_explore_period_metrics` 이고, 목록 엔드포인트는 `/games/explore/overview` 이다.
- 현재 엔드포인트는 `limit`만 지원한다. period/window, region, market, rank_type 쿼리 계약은 아직 없다.
- 기준 유니버스는 `tracked_game.is_active = true` 인 Steam canonical game이다.
- 기본 정렬은 `period_avg_ccu_7d DESC NULLS LAST, canonical_game_id ASC` 이다.
- 현재 서빙 형태는 게임 식별 정보, current/latest CCU, 7일 CCU 기간 평균/최고 및 same-window delta, strict 7일 `Estimated Player-Hours`, 리뷰 누적 기준 snapshot, 리뷰 7일/30일 boundary 기반 파생 필드와 previous-period comparison, 최신 KR 가격 근거를 한 row에 담는다.
- current `Most Played` longer-window API는 `7d|30d|90d` list ordering context만 바꾸고 latest CCU row shape를 반환한다. 이를 `Explore` period avg/peak metric API로 재해석하지 않는다.
- CCU 기간 지표:
    - `agg_steam_ccu_daily` 는 `period_avg_ccu_Nd`, `period_peak_ccu_Nd`, selected vs previous same-length delta 계산에 필요한 daily `avg_ccu` / `peak_ccu` 를 담고 있다.
    - 단, current table은 daily row 존재 여부만 알려주며 하루 내부 30분 bucket coverage completeness는 저장하지 않는다.
    - strict `Estimated Player-Hours` 는 raw 30분 bucket coverage가 필요한 metric이므로, current `agg_steam_ccu_daily` 만으로는 충분하지 않다.
    - `SUM(avg_ccu * 24)` 또는 `AVG(avg_ccu) * 24 * N` 은 strict `estimated_player_hours_Nd` 의 current source of truth로 사용하지 않는다.
    - daily `avg_ccu * 24` path는 future approximation으로 별도 caveat/name을 붙이거나, daily rollup에 raw bucket count / expected bucket count / completeness flag 같은 coverage metadata가 추가되어 strict coverage를 증명할 수 있을 때만 derived path로 검토한다.
    - current `srv_game_explore_period_metrics` 는 `fact_steam_ccu_30m` 에서 KST date 기준 latest available raw CCU date를 anchor로 잡고, selected `[anchor - 6, anchor]` 와 previous `[anchor - 13, anchor - 7]` 가 각각 raw 30분 bucket 336개를 모두 가질 때만 7d strict fields를 계산한다.
    - 노출 필드는 `estimated_player_hours_7d`, `delta_estimated_player_hours_7d_abs`, `delta_estimated_player_hours_7d_pct` 이다.
- 리뷰 기간 파생 지표:
    - `fact_steam_reviews_daily` 는 current all/all/all cumulative daily snapshot 기준 `reviews_added_7d`, `reviews_added_30d`, `period_positive_ratio_7d`, `period_positive_ratio_30d` 계산에 충분한 boundary totals를 담고 있다.
    - previous same-length comparison fields는 `delta_reviews_added_Nd_abs`, `delta_reviews_added_Nd_pct`, `delta_period_positive_ratio_Nd_pp` 이며, current serving/API는 7d/30d variants를 노출한다.
    - 7d comparison에는 `anchor`, `anchor - 7`, `anchor - 14` boundary snapshot이 필요하고, 30d comparison에는 `anchor`, `anchor - 30`, `anchor - 60` boundary snapshot이 필요하다.
    - missing boundary snapshot, negative cumulative delta, invalid denominator, inconsistent positive delta는 null로 유지한다.
    - DB에 request-param provenance를 보존해야 하거나 여러 review series를 병렬 보존해야 하면 schema/ingest 확장이 필요하다.
- 가격 근거:
    - 현재 `srv_game_latest_price` 는 KR-only latest price evidence column으로만 사용할 수 있다.
    - KR/USD 또는 generalized region query는 provider/region serving/API slice까지 열지 않는다.
- Explore 서빙 형태는 다음을 회귀 테스트로 고정한다.
    - metric-wide 최신 가용 KST anchor
    - 선택 기간/이전 기간의 full-window 요구조건
    - raw bucket/daily row/boundary snapshot 누락, 분모 0, inconsistent cumulative review delta 시 null 반환
    - per-game older-anchor fallback, gap fill, synthetic score 금지

### 5.3 90일 프리셋용 일 단위 rollup (권장)

- 예시:
    - agg_steam_ccu_daily: (canonical_game_id, date) → avg_ccu, peak_ccu
    - agg_stream_daily: (canonical_game_id or category_id, date) → viewer_hours, avg_concurrent, peak_concurrent

## 6. 적재 규칙(초안)

- Fact 계열은 “버킷/스냅샷 PK로 upsert”를 기본으로 한다(재실행 안전).
- Bronze 원본은 append-only + 실행 메타데이터를 별도 저장한다.
- 결측 버킷은 NULL로 채우기보다 “해당 버킷이 없었다”를 명확히 표시(예: missing_flag 또는 별도 품질 테이블).

## 7. 보존기간(초안)

- 최소 요구: 대시보드 프리셋(전일/7/30/90) 지원을 위해 30분/1시간 fact는 “최소 90일”
- 일 스냅샷(랭킹/리뷰)은 1년 이상 보관을 권장
- 최종 값은 운영 저장공간/성능을 보고 조정(TBD)
