# Metrics & Definitions (요구사항 + 지표 정의서)

문서 목적: 용어/지표/Δ 기준을 고정해 구현 중 재해석을 방지
버전: v0.4 (latest rankings API semantics 반영)
작성일: 2026-03-31 (KST)

## 0. 시간/기간 프리셋

- 시간대: KST
- 기본 프리셋:
    - 전일 대비 (Default)
    - 최근 7일
    - 최근 30일
    - 최근 90일(3개월) — 기본적으로 일 단위 rollup을 사용

## 1. 공통 정의

### 1.1 bucket_time (30분/1시간)

- 30분 버킷: HH:00 또는 HH:30으로 정규화된 시각
- 1시간 버킷: HH:00으로 정규화된 시각
- 이 문서에서 `bucket_time`은 section 0의 KST 기준으로 해석한다.
- Steam CCU의 internal/DB 의미는 KST half-hour bucket instant이다.
- `srv_game_latest_ccu`와 latest CCU API의 전일 대비는 section 1.3 규칙대로 전일 동일 KST 버킷을 비교한다.
- latest CCU API의 `bucket_time` wire output은 같은 instant를 표현한 timezone-aware ISO datetime string으로 본다.
- 현재 API 런타임은 timezone-aware `datetime`을 그대로 직렬화하며, UTC-only serialization을 강제하지 않는다.
- checkpoint 실측 단건 API 예시(`/games/{id}/ccu/latest`):

```json
{
  "canonical_game_id": 1,
  "canonical_name": "Counter-Strike 2",
  "bucket_time": "2026-03-07T05:00:00Z",
  "ccu": 858325,
  "delta_ccu_abs": null,
  "delta_ccu_pct": null,
  "missing_flag": true
}
```

- 같은 instant 대응: 위 wire example의 `"bucket_time":"2026-03-07T05:00:00Z"` 는 KST bucket/view 값 `2026-03-07 14:00:00 +0900` 와 같은 시각이다.
- 따라서 위 `Z` 예시는 실제 관측된 wire example이지만, current runtime이 보장하는 유일한 timezone representation은 아니다.

### 1.2 snapshot_date (1일 스냅샷)

- “수집 실행 시각”이 아니라 “KST 날짜”로 저장
- `srv_game_latest_reviews`와 latest reviews API의 `snapshot_date`는 같은 KST 날짜를 뜻하며, wire output은 ISO date string(`YYYY-MM-DD`)으로 본다.
- current rankings gold path는 raw payload contract에 별도 collected timestamp가 없으므로 runtime artifact file mtime을 `collected_at` anchor로 사용하고, 그 KST 날짜를 `snapshot_date`로 저장한다.
- latest reviews API의 전일 대비는 section 1.3 규칙대로 전일 `snapshot_date`를 비교한다.
- 스케줄:
    - Steam 랭킹: 03:10 KST
    - Steam 리뷰: 03:20 KST

### 1.3 Δ(전일 대비) 규칙

- 30분/1시간 시계열: 전일 동일 버킷 대비
    - 예: 2026-03-04 14:30 버킷의 값 vs 2026-03-03 14:30 버킷
- 1일 스냅샷: 전일 snapshot_date 대비
    - 예: 2026-03-04 스냅샷 vs 2026-03-03 스냅샷

## 2. Steam 리뷰 대시보드(살 만한가)

### 2.1 Positive Ratio

- 정의: total_positive / total_reviews
- 단위: 0~1 (화면에서는 %로 표시)

### 2.2 리뷰 수(표본 크기)

- 정의: total_reviews
- 표시: 절대값 + 필요 시 표본 배지(예: 부족/보통/충분) 기준은 추후 확정(TBD)

### 2.3 리뷰 모멘텀(Δ)

- 정의(일 스냅샷 기준):
    - Δ_total_reviews = total_reviews(D) - total_reviews(D-1)
    - Δ_positive_ratio = positive_ratio(D) - positive_ratio(D-1)

### 2.4 Latest reviews API serving shape

- latest reviews API는 `srv_game_latest_reviews`를 직접 읽는다.
- list endpoint는 `/games/reviews/latest`, single-game endpoint는 `/games/{canonical_game_id}/reviews/latest` 이다.
- `missing_flag = true` 는 전일 `snapshot_date` 기준 비교 행이 없어 Δ 필드가 계산되지 않았음을 뜻한다.
- current wire example(`/games/{id}/reviews/latest`):

```json
{
  "canonical_game_id": 1,
  "canonical_name": "Counter-Strike 2",
  "snapshot_date": "2026-03-29",
  "total_reviews": 9154321,
  "total_positive": 7983210,
  "total_negative": 1171111,
  "positive_ratio": 0.8719,
  "delta_total_reviews": null,
  "delta_positive_ratio": null,
  "missing_flag": true
}
```

## 3. Steam CCU 대시보드(살아있나/뜨나)

### 3.1 현재 CCU

- 정의: 가장 최신 bucket_time의 ccu

### 3.2 CCU 모멘텀(Δ)

- 정의(30분 버킷 기준):
    - Δ_ccu_abs = ccu(t) - ccu(t - 1day_same_bucket)
    - Δ_ccu_pct = (ccu(t) - ccu(t-1d)) / NULLIF(ccu(t-1d), 0)

## 4. 스트리밍 요약(화제인가) — Chzzk/Twitch 공통 지향

원천은 “동시 시청자(concurrent)”를 30분 단위로 수집한다.

### 4.1 Avg concurrent (기본 표시)

- 정의: 기간 내 concurrent의 평균
    - avg_concurrent = AVG(concurrent_bucket)

### 4.2 Total (파생: viewer-hours)

- 정의: viewer_hours = Σ (concurrent_bucket * bucket_hours)
    - 30분 버킷이면 bucket_hours = 0.5
- 해석: “기간 동안 소비된 총 시청량(근사)”

### 4.3 Total streams (방송 수)

- 정의: 해당 bucket_time에서 라이브 채널 수(또는 카테고리 내 라이브 수)의 합/평균
- MVP에서는 bucket_time 스냅샷 기준의 live_count를 저장하고, 기간 합계/평균은 파생

### 4.4 Top streamer (입구)

- 정의: bucket_time에서 concurrent가 가장 큰 채널(또는 스트리머)
- 저장: top_channel_id, top_channel_name, top_channel_concurrent

### 4.5 시청 모멘텀(Δ)

- 30분 버킷 기준으로 전일 동일 버킷 대비:
    - Δ_avg_concurrent: 동일 버킷 비교 또는 기간 평균 비교(표현 방식은 UI에서 선택)
    - Δ_viewer_hours: 일 단위 rollup이 생기면 일 스냅샷 Δ로 전환 가능

## 5. 가격/할인(구매 타이밍)

### 5.1 price fields

- initial_price_minor: 할인 전 가격(최소 단위)
- final_price_minor: 현재 가격(최소 단위)
- discount_percent: 할인율(0~100)
- region: MVP는 KR만. 확장 시 US 등 추가 가능
- currency_code: region에 따라 저장(확장 대비)

### 5.2 할인 이벤트(관계 KPI에 사용)

- 할인 시작: discount_percent가 0 → 양수로 전환되는 시점(또는 final < initial)
- 할인 종료: discount_percent가 양수 → 0으로 전환

### 5.3 Latest price API serving shape

- latest price API는 `srv_game_latest_price`를 직접 읽는다.
- current minimum path는 `tracked_game.is_active = true` 인 게임의 최신 KR 가격 행만 다룬다.
- list endpoint는 `/games/price/latest`, single-game endpoint는 `/games/{canonical_game_id}/price/latest` 이다.
- `region`은 current slice에서 항상 `KR` 이고, generalized region query param은 아직 없다.
- `is_free`는 `fact_steam_price_1h`에 적재된 existing fact semantics를 그대로 노출하며, broader free/unavailable/missing-price semantics는 아직 확장하지 않는다.
- current wire example(`/games/{id}/price/latest`):

```json
{
  "canonical_game_id": 1,
  "canonical_name": "Counter-Strike 2",
  "bucket_time": "2026-03-29T14:00:00+09:00",
  "region": "KR",
  "currency_code": "KRW",
  "initial_price_minor": 4200000,
  "final_price_minor": 3360000,
  "discount_percent": 20,
  "is_free": null
}
```

## 6. 랭킹(추적 유니버스 seed)

- 시장(market): KR, global 둘 다 저장
- rank_type: top_selling / top_played 등(정의는 파서에서 고정)
- rank_position: 1..N
- 사용처:
    - 대시보드 “오늘의 상위”
    - tracked_universe 자동 갱신(seed)

### 6.1 Latest rankings API serving shape

- latest rankings API는 `srv_rank_latest_kr_top_selling` 를 직접 읽는다.
- current minimum path는 latest KR top-selling list만 다루며, generalized market/rank_type query param은 아직 없다.
- list endpoint는 `/games/rankings/latest` 이다.
- `canonical_game_id`, `canonical_name` 은 current Steam mapping이 없으면 `null` 이다.
- current wire example(`/games/rankings/latest` item):

```json
{
  "snapshot_date": "2026-03-31",
  "rank_position": 1,
  "steam_appid": 730,
  "canonical_game_id": 1,
  "canonical_name": "Counter-Strike 2"
}
```

## 7. 관계(동행) — MVP 최소 KPI

MVP에서는 시차 이벤트 탐지까지 가지 않고 KPI 1~2개로 최소 정의한다.

### KPI A: 할인 전후 24h CCU 리프트

- 정의:
    - lift_ccu_pct = (AVG(CCU, [t0, t0+24h]) - AVG(CCU, [t0-24h, t0])) / NULLIF(AVG(CCU, [t0-24h, t0]), 0)
- t0: 할인 시작 시점

### KPI B: 시청 ↔ 플레이 동행(둘 중 하나를 선택)

- 옵션1) viewer_to_player = avg_concurrent / avg_ccu (기간 평균 기반)
- 옵션2) 동행률: Δ의 부호가 같은 버킷 비율(최근 7일 등)
