문서 목적: 테이블/파일 목록 + 그레인(1행 키) + 적재 규칙(증분/스냅샷) + 보존 기준 + repo-grounded provider 확장 경계 기록
버전: v0.2 (provider-boundary 정리 반영)
작성일: 2026-03-28 (KST)

## 0. 레이어 개요

- Bronze: 원본 응답 보존(파싱 최소). 재처리/회귀 테스트의 근거.
- Silver: 분석/집계가 가능한 형태로 정규화(키/타입/시간 기준 정리).
- Gold: 대시보드/서빙 목적의 fact/rollup/snapshot. “쿼리 패턴”을 기준으로 설계.

저장소/엔진 결론:

- MinIO: Bronze/Silver/Gold Parquet(원본/중간/장기 보관)
- DuckDB: 변환/집계 작업(주로 Silver→Gold 산출)
- Postgres: 서빙용 Gold(대시보드/API가 직접 조회하는 테이블/뷰)

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

## 4. Fact / Snapshot (Gold 중심)

아래는 “1행 키(그레인)”를 확정하는 목적의 테이블 초안이다.

### 4.1 Steam CCU (30분)

- 테이블: fact_steam_ccu_30m (Postgres + 필요 시 MinIO Parquet)
- 그레인/PK: (canonical_game_id, bucket_time)
- 컬럼(초안):
    - canonical_game_id
    - bucket_time
    - ccu
    - collected_at
    - source_appid (추적/디버그용)

### 4.2 Streaming Category Metrics (30분) — Provider 확장 entry (초안)

- durable doc facts:
    - current MVP runtime은 Steam-only 이며, streaming fact/serving object는 아직 repo에 구현되지 않았다.
    - streaming 확장 시작점은 provider-specific probe/ingest 와 category-level 30분 fact다.
    - canonical game 기준 서빙 shape는 provider raw/category 수집 이후의 downstream 단계다.
- current repo observations:
    - 현재 repo에는 `src/chzzk`, `src/twitch`, streaming probe sample, streaming DDL이 없다.
    - 현재 재사용 가능한 공통 경계는 `game_external_id` 매핑과 `tracked_game.sources` provenance다.
- still undecided items:
    - 첫 구현이 `fact_chzzk_category_30m` 같은 provider-specific table로 시작할지, 더 일반화된 이름으로 시작할지는 미정이다.
    - provider auth/quota/runtime contract와 category-to-game mapping workflow도 미정이다.
- 첫 provider-specific candidate 예시:
    - `fact_chzzk_category_30m`
    - 그레인/PK: `(chzzk_category_id, bucket_time)`
    - 컬럼(초안): `chzzk_category_id`, `bucket_time`, `concurrent_sum`, `live_count`, `top_channel_id`, `top_channel_name`, `top_channel_concurrent`, `collected_at`
- 매핑 확정 시(선택):
    - `gold_stream_game_30m`: `(canonical_game_id, bucket_time)` 형태의 view/materialized view 제공

### 4.3 Steam Price (1시간)

- 테이블: fact_steam_price_1h
- 그레인/PK: (canonical_game_id, bucket_time, region)
- 컬럼(초안):
    - canonical_game_id
    - bucket_time
    - region (MVP: KR만)
    - currency_code
    - initial_price_minor
    - final_price_minor
    - discount_percent
    - is_free (nullable)
    - collected_at

### 4.4 Steam Reviews Snapshot (1일)

- 테이블: fact_steam_reviews_daily
- 그레인/PK: (canonical_game_id, snapshot_date)
- 컬럼(초안):
    - canonical_game_id
    - snapshot_date
    - total_reviews
    - total_positive
    - total_negative
    - positive_ratio (total_positive / total_reviews)
    - collected_at
    - (선택) language/filter 파라미터 기록용 컬럼

### 4.5 Steam Ranking Snapshot (1일)

- 테이블: fact_steam_rank_daily
- 그레인/PK: (snapshot_date, market, rank_type, rank_position)
- 컬럼(초안):
    - snapshot_date
    - market (KR/global)
    - rank_type (top_selling/top_played 등)
    - rank_position (1..N)
    - steam_appid
    - canonical_game_id (매핑되면 채움)
    - collected_at

## 5. Rollup / Serving Views (대시보드 쿼리 패턴)

### 5.1 “최신 스냅샷” 서빙 테이블(권장)

- 목적: API에서 실시간 집계 대신 “미리 계산된 결과”를 읽게 함
- 예시:
    - srv_game_latest_ccu: game별 최신 bucket_time의 ccu + Δ(전일 동일 버킷)
    - srv_game_latest_reviews: game별 최신 snapshot_date의 positive_ratio + Δ(전일)
    - srv_rank_latest_kr/global: 최신 snapshot_date의 랭킹 리스트

### 5.2 90일 프리셋용 일 단위 rollup (권장)

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
