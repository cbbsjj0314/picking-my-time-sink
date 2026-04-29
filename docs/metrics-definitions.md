# 지표 정의서

문서 목적: 용어/지표/Δ 기준을 고정해 구현 중 재해석을 방지
버전: v0.28 (public 한국어 톤 정리)
최종 수정일: 2026-04-24 (KST)

## 0. 시간/기간 프리셋

- 시간대: KST
- 기본 프리셋:
    - 전일 대비 (Default)
    - 최근 7일
    - 최근 30일
    - 최근 90일(3개월) — 기본적으로 일 단위 rollup을 사용

### 0.1 지표 정의 governance

- 지표 정의는 구현 전 또는 구현과 같은 slice에서 고정한다.
- 각 지표는 name, grain, anchor, formula, comparison baseline, unit, null rule을 포함한다.
- Δ 지표는 비교 기준을 반드시 명시한다. 예: 현재 CCU Δ는 직전 30분 버킷이 아니라 전일 동일 KST 30분 버킷과 비교한다.
- percent change는 `_pct`, percentage point 차이는 `_pp` suffix를 사용한다.
- field-level missing evidence는 synthetic fallback으로 채우지 않는다. null, skipped evidence, missing flag 중 해당 table/API contract에 맞는 형태로 보존한다.
- 지표가 schema/API/data semantics를 바꾸면 `docs/data-governance.md`, `docs/data-model-spec.md`, 관련 tests를 함께 갱신한다.

## 1. 공통 정의

### 1.1 bucket_time (30분/1시간)

- 30분 버킷: HH:00 또는 HH:30으로 정규화된 시각
- 1시간 버킷: HH:00으로 정규화된 시각
- 이 문서에서 `bucket_time`은 0장의 KST 기준으로 해석한다.
- Steam CCU의 internal/DB 의미는 KST half-hour bucket instant다.
- `srv_game_latest_ccu`와 latest CCU API의 전일 대비는 1.3장 규칙대로 전일 동일 KST 버킷을 비교한다.
- latest CCU API의 `bucket_time` wire output은 같은 instant를 표현한 timezone-aware ISO datetime string이다.
- 현재 API 런타임은 timezone-aware `datetime`을 그대로 직렬화하며, UTC-only serialization을 강제하지 않는다.
- Historical 단건 API 예시(`/games/{id}/ccu/latest`):

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
- 위 `Z` 예시는 가능한 wire representation 중 하나다. 현재 runtime이 UTC-only serialization을 보장하지는 않는다.

### 1.2 snapshot_date (1일 스냅샷)

- “수집 실행 시각”이 아니라 “KST 날짜”로 저장
- `srv_game_latest_reviews`와 latest reviews API의 `snapshot_date`는 같은 KST 날짜를 뜻하며, wire output은 ISO date string(`YYYY-MM-DD`)으로 본다.
- 현재 rankings gold path는 raw payload contract에 별도 collected timestamp가 없으므로 runtime artifact file mtime을 `collected_at` anchor로 사용하고, 그 KST 날짜를 `snapshot_date`로 저장한다.
- latest reviews API의 전일 대비는 1.3장 규칙대로 전일 `snapshot_date`를 비교한다.
- 수집 cadence:
    - Steam 랭킹: daily
    - Steam 리뷰: daily

### 1.3 Δ(전일 대비) 규칙

- Δ는 signal별 자연스러운 비교 기준을 따른다.
- 모든 latest surface가 Δ를 반드시 가져야 하는 것은 아니다.
- 30분/1시간 시계열:
    - 전일 동일 버킷 대비
    - 예: 2026-03-04 14:30 버킷의 값 vs 2026-03-03 14:30 버킷
- 1일 스냅샷:
    - 전일 snapshot_date 대비
    - 예: 2026-03-04 스냅샷 vs 2026-03-03 스냅샷
- 이벤트/상태형 latest surface:
    - 현재 MVP에서는 상태 요약만 두고 Δ를 강제하지 않을 수 있다.
    - 대표 예: latest price surface는 현재 가격, 할인율, 세일 상태, 마지막 세일 시점 같은 현재 문맥을 우선한다.

### 1.4 Explore period metric anchor / null rule

- 이 섹션은 target/proposed `Explore` evidence table의 durable metric semantics다. latest 개별 API contract는 2.5장, 3.5장, 5.3장, 6.1장을 따르고, 현재 `Explore` overview API contract는 1.5장을 따른다.
- `Explore` target base universe는 `tracked_game.is_active = true` 인 Steam canonical game이다.
- 현재 MVP에서 `tracked_game.is_active` 는 serving eligibility 와 Steam price/reviews/ccu fetch eligibility를 함께 뜻한다.
- `tracked_game.last_seen_at` 은 현재 metric freshness anchor가 아니며, 오래 관측되지 않은 row를 자동으로 포함/제외하는 lifecycle timer로 사용하지 않는다.
- warm 7일 rule은 현재 `Explore` serving active rule이 아니며, `is_active` 와 분리된 lifecycle/fetch-cadence 상태가 정의되기 전까지 metric base universe에 반영하지 않는다.
- tracked universe seed provenance는 `topsellers_global`, `topsellers_kr`, `mostplayed_global`, `mostplayed_kr` 의 합집합으로 본다.
- `Explore` default period preset은 `Last 7 Days` 이고, target default sort는 strict `Estimated Player-Hours desc` 다.
- period metric family는 KST date 기준 `latest available data date` 를 anchor로 쓴다.
- anchor는 per-game anchor가 아니라 metric-wide anchor를 우선한다. 같은 테이블의 row들이 같은 기준일로 비교되도록, 특정 게임의 더 오래된 최신일로 fallback하지 않는다.
- metric-wide anchor 예시:
    - CCU daily rollup family: `agg_steam_ccu_daily.bucket_date` 의 latest available KST date
    - strict Estimated Player-Hours raw CCU family: `fact_steam_ccu_30m.bucket_time` 의 KST date 기준 latest complete raw data date. Complete raw KST date의 현재 minimum 기준은 해당 KST date에 distinct half-hour bucket timestamp 48개가 있는 것이다.
    - review daily snapshot family: `fact_steam_reviews_daily.snapshot_date` 의 latest available KST date
- selected period window가 N일이면 selected window는 `[anchor - (N - 1), anchor]`, previous same-length window는 `[anchor - (2N - 1), anchor - N]` 로 둔다.
- selected period의 full coverage 조건을 만족하지 못하면 selected period value 자체가 null이다.
- previous same-length period의 full coverage 조건을 만족하지 못하면 previous-period comparison delta는 null이다.
- raw 30분 CCU bucket 기반 period metric은 해당 window의 모든 expected KST half-hour bucket이 있어야 full coverage로 본다. KST는 DST가 없으므로 N일 window의 expected bucket 수는 `48 * N` 이다.
- daily rollup 기반 period metric은 해당 window의 N개 daily row가 있어야 full coverage로 본다.
- review cumulative snapshot 기반 period metric은 필요한 boundary snapshot이 모두 있어야 full coverage로 본다.
- partial history, missing raw bucket, missing daily row, missing boundary snapshot, invalid denominator, inconsistent review cumulative delta는 null/no data다.
- fake fallback, gap fill, synthetic score, per-game older anchor fallback으로 메우지 않는다.
- list/table-level no rows는 empty state로 처리할 수 있고, field-level missing은 null / `-` / caveat로 표시한다.
- 현재 daily CCU rollup은 day row 존재 여부만 알려준다. 하루 안의 30분 bucket coverage completeness까지 보장해야 하는 metric이 필요하면 별도 quality metadata가 필요하다.

### 1.5 Explore 개요 API 서빙 형태

- `Explore` 개요 API는 `srv_game_explore_period_metrics`를 직접 읽는다.
- 목록 엔드포인트는 `/games/explore/overview` 이다.
- 현재 최소 경로는 쿼리 파라미터로 `limit`만 받는다. period/window, region, market, rank_type 쿼리 계약은 아직 없다.
- 기준 유니버스는 `tracked_game.is_active = true` 인 Steam canonical game이다.
- API/server default 정렬은 `estimated_player_hours_7d DESC NULLS LAST, current_ccu DESC NULLS LAST, canonical_game_id ASC` 이다.
- 현재 web `Explore` table도 프론트 row/view-model layer에서 동일한 기본 정렬을 유지한다. header click sort는 프론트 상태로 관리하고, 현재 fixed `Last 7 Days` path에서는 period-aware column sort key를 7d fields에 매핑한다.
- 현재 응답 row는 아래의 실제 근거 필드 묶음으로 구성된다.
    - 식별 정보: `canonical_game_id`, `canonical_name`, `steam_appid`
    - 현재 CCU: `ccu_bucket_time`, `current_ccu`, `current_delta_ccu_abs`, `current_delta_ccu_pct`, `current_ccu_missing_flag`
    - 7일 CCU 기간 지표: `ccu_period_anchor_date`, `period_avg_ccu_7d`, `period_peak_ccu_7d`, `delta_period_avg_ccu_7d_abs`, `delta_period_avg_ccu_7d_pct`, `delta_period_peak_ccu_7d_abs`, `delta_period_peak_ccu_7d_pct`
    - 7일 raw CCU activity 지표: `estimated_player_hours_7d`, `delta_estimated_player_hours_7d_abs`, `delta_estimated_player_hours_7d_pct`, `observed_player_hours_7d`, `estimated_player_hours_7d_observed_bucket_count`, `estimated_player_hours_7d_expected_bucket_count`, `estimated_player_hours_7d_coverage_ratio`
    - 리뷰 metric-wide anchor의 누적 snapshot: `reviews_snapshot_date`, `total_reviews`, `total_positive`, `total_negative`, `positive_ratio`
    - 리뷰 기간 파생 지표: `reviews_added_7d`, `reviews_added_30d`, `period_positive_ratio_7d`, `period_positive_ratio_30d`, `delta_reviews_added_7d_abs`, `delta_reviews_added_7d_pct`, `delta_period_positive_ratio_7d_pp`, `delta_reviews_added_30d_abs`, `delta_reviews_added_30d_pct`, `delta_period_positive_ratio_30d_pp`
    - 최신 KR 가격 근거: `price_bucket_time`, `region`, `currency_code`, `initial_price_minor`, `final_price_minor`, `discount_percent`, `is_free`
- 7일 CCU 기간 지표는 `agg_steam_ccu_daily` 의 최신 가용 `bucket_date` 를 metric-wide anchor로 사용한다.
- 7일 raw CCU activity 지표는 `fact_steam_ccu_30m.bucket_time` 의 KST date 기준 최신 complete raw CCU date를 metric-wide anchor로 사용한다. Complete raw KST date의 현재 minimum 기준은 해당 KST date에 distinct half-hour bucket timestamp 48개가 있는 것이다.
- `estimated_player_hours_7d` 는 selected window `[anchor - 6, anchor]` 에 raw 30분 bucket 336개가 모두 있을 때만 `SUM(ccu * 0.5)` 로 계산한다.
- `observed_player_hours_7d` 는 같은 selected window에서 실제 존재하는 raw 30분 bucket만 `SUM(ccu * 0.5)` 로 합산한 observed evidence field다. 이 값은 gap fill, interpolation, coverage-adjusted extrapolation을 하지 않으며 strict sort key가 아니다.
- `estimated_player_hours_7d_observed_bucket_count` 는 selected window에서 실제 관측된 raw 30분 bucket 수다.
- `estimated_player_hours_7d_expected_bucket_count` 는 현재 fixed 7d window의 expected bucket 수인 `336` 이다.
- `estimated_player_hours_7d_coverage_ratio` 는 `observed_bucket_count / expected_bucket_count` 를 0..1로 cap한 coverage hint다.
- `delta_estimated_player_hours_7d_abs` / `delta_estimated_player_hours_7d_pct` 는 previous same-length window `[anchor - 13, anchor - 7]` 도 raw 30분 bucket 336개를 모두 가질 때만 계산한다.
- 리뷰 기간 파생 지표는 `fact_steam_reviews_daily` 의 최신 가용 `snapshot_date` 를 metric-wide anchor로 사용한다.
- 리뷰 previous-period comparison은 selected boundary snapshot과 previous same-length boundary snapshot을 사용한다. 7d는 `anchor`, `anchor - 7`, `anchor - 14`, 30d는 `anchor`, `anchor - 30`, `anchor - 60` 이 필요하다.
- 선택/이전 기간의 full-window daily row, raw 30분 bucket full coverage, 리뷰 boundary snapshot, 유효한 분모가 없거나 누적 delta가 일관되지 않으면 null을 반환한다.
- serving boundary에서 `NaN` / `Infinity` 같은 non-finite numeric output은 null로 정규화하고, UI는 이를 합성 delta처럼 표시하지 않는다.
- strict `Estimated Player-Hours` 는 현재 `/games/explore/overview` 응답에 7d fields로 포함된다.
- 현재 CCU와 최신 KR 가격은 최신 근거 필드로 유지하며, 기간 지표로 재해석하지 않는다.
- 현재 web `Explore` table은 visible rows의 `ccu_bucket_time`, `ccu_period_anchor_date`, `reviews_snapshot_date`, `price_bucket_time` 을 summary support text로 표시한다. 동일하지 않은 visible timestamp 묶음은 synthetic 대표 시각으로 합치지 않고 mixed snapshots로 표시한다.
- `Top Selling` 순위는 의도적으로 `Explore` 개요 응답에 포함하지 않는다.

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
- `delta_positive_ratio` 같은 ratio 차이는 표시할 때 percentage points(pp)로 해석한다. percent change(`%`)로 라벨링하지 않는다.

### 2.4 Explore 리뷰 기간 파생 지표

- 이 섹션은 target/proposed `Explore` table metric semantics다. 현재 latest reviews API에는 노출되지 않고, `/games/explore/overview` 에서 최소 경로 필드로 노출된다.
- 현재 canonical review source series는 Steam `appreviews` query summary 기준 `filter=all`, `language=all`, `purchase_type=all`, `num_per_page=20` 이다.
- cumulative metrics(`total_reviews`, `total_positive`, `total_negative`, `positive_ratio`)는 period-derived metrics와 별도 필드로 유지한다.
- `reviews_added_7d`, `reviews_added_30d`:
    - `reviews_added_Nd = total_reviews(anchor) - total_reviews(anchor - N)`
    - N은 7 또는 30이다.
    - 최신 boundary snapshot(`anchor`)과 이전 boundary snapshot(`anchor - N`)이 모두 있어야 한다.
    - 결과가 음수이면 cumulative source inconsistency로 보고 null 처리한다.
    - 결과가 0이면 0으로 유지한다.
- Reviews Added previous same-length delta의 canonical serving field name은 `delta_reviews_added_Nd_abs` / `delta_reviews_added_Nd_pct` 로 둔다.
    - `delta_reviews_added_Nd_abs = reviews_added_Nd(selected) - reviews_added_Nd(previous)`
    - `delta_reviews_added_Nd_pct = delta_reviews_added_Nd_abs / NULLIF(reviews_added_Nd(previous), 0) * 100`
    - selected 또는 previous `reviews_added_Nd` 가 null이면 두 delta 모두 null이다.
    - previous `reviews_added_Nd` 가 0이면 absolute delta는 계산할 수 있지만 percent delta는 null이다.
    - 현재 `/games/explore/overview` 는 7d/30d fields를 노출한다.
- `period_positive_ratio_7d`, `period_positive_ratio_30d`:
    - `period_positive_ratio_Nd = positive_delta_Nd / reviews_added_Nd`
    - `positive_delta_Nd = total_positive(anchor) - total_positive(anchor - N)`
    - N은 7 또는 30이다.
    - missing boundary snapshot, `reviews_added_Nd <= 0`, `positive_delta_Nd < 0`, `positive_delta_Nd > reviews_added_Nd` 인 경우 null 처리한다.
    - 단위는 0~1 ratio이고, 화면에서는 %로 표시할 수 있다.
- period positive ratio delta가 필요하면 selected period와 previous same-length period의 ratio 차이로 계산한다.
    - canonical serving field name은 `delta_period_positive_ratio_Nd_pp` 로 둔다.
    - `delta_period_positive_ratio_Nd_pp = (period_positive_ratio_Nd(selected) - period_positive_ratio_Nd(previous)) * 100`
    - previous period boundary는 `anchor - N` 과 `anchor - 2N` 을 사용한다.
    - selected 또는 previous ratio가 null이면 delta도 null이다.
    - 표시 단위는 percentage points(pp)이고, percent change(`%`)가 아니다.
- 현재 `fact_steam_reviews_daily` 의 cumulative daily snapshot은 위 후보 metric 계산에 필요한 boundary totals를 담고 있다.
- 다만 현재 gold fact에는 `filter`, `language`, `purchase_type` provenance 컬럼이 없으므로, 여러 review source series를 같은 테이블에 보존해야 하면 schema/ingest 확장이 필요하다.

### 2.5 Latest reviews API 서빙 형태

- latest reviews API는 `srv_game_latest_reviews`를 직접 읽는다.
- list endpoint는 `/games/reviews/latest`, single-game endpoint는 `/games/{canonical_game_id}/reviews/latest` 이다.
- `missing_flag = true` 는 전일 `snapshot_date` 기준 비교 행이 없어 Δ 필드가 계산되지 않았음을 뜻한다.
- 현재 latest reviews API는 Steam-authored `review_score_desc`를 서빙하지 않는다.
- review summary band는 UI local derived label이며, `positive_ratio` 와 `total_reviews` 만으로 아래 순서를 위에서 아래로 적용한다.
- 현재 UI의 Reviews signal card subtitle은 review summary band만 보여주고, detail card row에서 latest `snapshot_date` 를 `Review snapshot` 으로 표시한다.
- signal card 자체의 refresh/update cadence 표기는 별도 UI semantics slice에서 다룬다.
- `total_reviews < 10`: `Not Enough Reviews`
- `positive_ratio >= 0.95` and `total_reviews >= 500`: `Overwhelmingly Positive`
- `positive_ratio >= 0.80` and `total_reviews >= 50`: `Very Positive`
- `positive_ratio >= 0.80` and `10 <= total_reviews <= 49`: `Positive`
- `0.70 <= positive_ratio < 0.80` and `total_reviews >= 10`: `Mostly Positive`
- `0.40 <= positive_ratio < 0.70` and `total_reviews >= 10`: `Mixed`
- `positive_ratio < 0.20` and `total_reviews >= 500`: `Overwhelmingly Negative`
- `positive_ratio < 0.20` and `total_reviews >= 50`: `Very Negative`
- `positive_ratio < 0.20` and `10 <= total_reviews <= 49`: `Negative`
- `0.20 <= positive_ratio < 0.40` and `total_reviews >= 10`: `Mostly Negative`
- fallback: `Mixed`
- `delta_total_reviews` 는 `1D reviews added` 의미로만 노출한다.
- 현재 wire 예시(`/games/{id}/reviews/latest`):

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
- 현재 UI detail card는 latest `bucket_time` 을 `CCU snapshot` 시각으로 표시한다.

### 3.2 CCU 모멘텀(Δ)

- 정의(30분 버킷 기준):
    - Δ_ccu_abs = ccu(t) - ccu(t - 1day_same_bucket)
    - Δ_ccu_pct = (ccu(t) - ccu(t-1d)) / NULLIF(ccu(t-1d), 0)
- 이 latest CCU delta는 period avg/peak CCU delta와 다른 metric이다. selected period 변화량으로 재해석하지 않는다.

### 3.3 Explore CCU 기간 평균/최고 지표

- 이 섹션은 target/proposed `Explore` table metric semantics다. 현재 latest CCU API row shape에는 노출되지 않고, `/games/explore/overview` 에서 7d 최소 경로 필드로 노출된다.
- `period_avg_ccu_Nd`:
    - `agg_steam_ccu_daily.avg_ccu` 를 selected N-day window에서 평균한다.
    - `period_avg_ccu_Nd = AVG(avg_ccu for bucket_date in selected window)`
- `period_peak_ccu_Nd`:
    - `agg_steam_ccu_daily.peak_ccu` 를 selected N-day window에서 최댓값으로 집계한다.
    - `period_peak_ccu_Nd = MAX(peak_ccu for bucket_date in selected window)`
- period delta는 selected period와 previous same-length period를 비교한다.
    - `delta_period_avg_ccu_Nd_abs = period_avg_ccu_Nd(selected) - period_avg_ccu_Nd(previous)`
    - `delta_period_avg_ccu_Nd_pct = delta_period_avg_ccu_Nd_abs / NULLIF(period_avg_ccu_Nd(previous), 0)`
    - `delta_period_peak_ccu_Nd_abs = period_peak_ccu_Nd(selected) - period_peak_ccu_Nd(previous)`
    - `delta_period_peak_ccu_Nd_pct = delta_period_peak_ccu_Nd_abs / NULLIF(period_peak_ccu_Nd(previous), 0)`
- selected window와 previous same-length window 모두에 N개의 daily rollup row가 있어야 한다.
- 둘 중 하나라도 full-window 조건을 만족하지 못하면 delta는 null이다. selected window가 부족하면 period value 자체도 null이다.
- percent delta의 previous baseline이 0이면 percent delta는 null이다.
- 이 period delta는 `srv_game_latest_ccu` / latest CCU API의 전일 동일 KST bucket delta와 별개다.

### 3.4 Explore Estimated Player-Hours

- `Estimated Player-Hours` 는 Steam public CCU snapshot 기반 derived activity metric이다.
- 해석: 기간 동안 Steam public CCU로 관측된 동시접속자 수를 시간으로 적분한 근사 플레이어-아워다. 실제 unique players, sales, ownership, playtime telemetry가 아니다.
- strict canonical formula는 raw 30분 CCU bucket 기준이다.
    - `estimated_player_hours_Nd = SUM(ccu * bucket_duration_hours for each raw CCU bucket in selected window)`
    - 현재 Steam CCU bucket duration은 30분이므로 `bucket_duration_hours = 0.5` 이다.
- strict metric의 source of truth는 `fact_steam_ccu_30m` 같은 raw half-hour bucket series다.
- serving anchor는 metric-wide latest complete raw KST date다. Complete raw KST date의 현재 minimum 기준은 해당 KST date에 distinct half-hour bucket timestamp 48개가 있는 것이다.
- selected N-day window의 expected KST half-hour bucket `48 * N` 개가 모두 있어야 `estimated_player_hours_Nd` 를 계산한다.
- selected window에 missing bucket이 하나라도 있으면 `estimated_player_hours_Nd` 는 null이다.
- `observed_player_hours_Nd` 가 노출되는 serving surface에서는 selected window에 실제 존재하는 raw bucket만 합산한다. 이 field는 missing bucket을 메우거나 expected coverage로 외삽하지 않으며, strict `estimated_player_hours_Nd` 의 대체값이나 정렬 key가 아니다.
- observed coverage companion fields는 `estimated_player_hours_Nd_observed_bucket_count`, `estimated_player_hours_Nd_expected_bucket_count`, `estimated_player_hours_Nd_coverage_ratio` 형태를 따른다.
- previous same-length comparison도 previous window의 expected bucket `48 * N` 개가 모두 있어야 한다.
- Estimated Player-Hours previous same-length delta의 canonical serving field name은 `delta_estimated_player_hours_Nd_abs` / `delta_estimated_player_hours_Nd_pct` 로 둔다.
    - `delta_estimated_player_hours_Nd_abs = estimated_player_hours_Nd(selected) - estimated_player_hours_Nd(previous)`
    - `delta_estimated_player_hours_Nd_pct = delta_estimated_player_hours_Nd_abs / NULLIF(estimated_player_hours_Nd(previous), 0) * 100`
    - selected 또는 previous value가 null이면 두 delta 모두 null이다.
    - previous value가 0이면 absolute delta는 계산할 수 있지만 percent delta는 null이다.
- 현재 `/games/explore/overview` 는 7d strict fields인 `estimated_player_hours_7d`, `delta_estimated_player_hours_7d_abs`, `delta_estimated_player_hours_7d_pct` 와 selected-window observed/coverage fields인 `observed_player_hours_7d`, `estimated_player_hours_7d_observed_bucket_count`, `estimated_player_hours_7d_expected_bucket_count`, `estimated_player_hours_7d_coverage_ratio` 를 노출한다.
- 현재 `agg_steam_ccu_daily` 는 daily `avg_ccu` / `peak_ccu` 만 제공하고 하루 내부 30분 bucket coverage completeness metadata가 없다.
- 따라서 `SUM(avg_ccu * 24)` 또는 `AVG(avg_ccu) * 24 * N` 은 strict `estimated_player_hours_Nd` 의 현재 source of truth로 사용하지 않는다.
- daily `avg_ccu * 24` path는 향후 approximation으로 별도 caveat/name을 붙이거나, daily rollup에 raw bucket coverage completeness metadata가 추가되어 strict coverage를 증명할 수 있을 때만 derived path로 검토한다.
- fake fallback, gap fill, per-game older anchor fallback, synthetic activity score는 금지한다.

### 3.5 Most Played list context windows

- `Top Ranked` 의 Most Played window는 row payload meaning을 바꾸지 않고, 어떤 게임이 리스트에 들어오고 어떤 순서로 보이는지만 바꾼다.
- `/games/ccu/latest` 는 `window=1d|7d|30d|90d` 를 받는다.
- `window=1d`:
    - `srv_game_latest_ccu` 최신 행을 `latest_ccu DESC` 기준으로 정렬한 live list다.
- `window=7d|30d|90d`:
    - `agg_steam_ccu_daily` 의 latest available `bucket_date` 를 anchor로 잡고, full-window daily row가 있는 게임만 남긴 뒤 그 기간의 `avg_ccu` 평균으로 리스트 컨텍스트를 정한다.
    - 응답 payload는 여전히 같은 latest CCU row shape를 반환한다.
- 현재 slice는 fake score, gap fill, synthetic timeline을 추가하지 않는다.
- 따라서 full-window daily row가 없는 게임은 해당 window list에서 제외되고, longer window는 빈 리스트가 될 수 있다.

## 4. 스트리밍 요약(화제인가) — Chzzk category evidence browser 기준

현재 repo runtime에는 Chzzk streaming metric scheduler/UI 구현이 없다. Chzzk live-list sanitized fixture, category parser/upsert, `fact_chzzk_category_30m` DDL, category-result artifact-to-Postgres write path, `fact_chzzk_category_channel_30m` observed channel fact DDL/write path, and read-only category overview API가 있다. 이 장은 첫 Chzzk source view를 category-only evidence browser로 시작하기 위한 metric 의미를 고정한다.

- 첫 후보: Chzzk category live-list source.
- metric grain 후보: `(chzzk_category_id, bucket_time)` category-level 30분 KST bucket.
- source boundary: Chzzk live/category payload에서 category type/id/name, live concurrent, channel id/name만 읽는다.
- sample payload/fixture: public에는 sanitized representative payload만 둔다.
- 해석 boundary: category evidence browser로만 본다. `categoryType=GAME` 이 있어도 canonical game semantics, Steam mapping, Combined semantics로 확장하지 않는다.
- DB write boundary: local/private `category-result.jsonl` 의 strict category rows는
  `fact_chzzk_category_30m` 에 upsert하고, local/private `channel-result.jsonl`
  의 observed category-channel rows는 `fact_chzzk_category_channel_30m` 에
  upsert한다. Inserted vs updated rows는 `ON CONFLICT` upsert 특성상 loader
  summary에서 구분하지 않는다.
- 제외: canonical game mapping, Twitch fallback, provider abstraction, web dashboard streaming UI wiring, Combined/relationship KPI.
- access status: official docs 기준 `/open/v1/lives` 는 Client 인증이 필요하다. quota behavior와 runtime error behavior는 아직 public contract가 아니다.

원천은 “동시 시청자(concurrent)”를 30분 단위 category bucket으로 수집하는 방향이다. missing bucket은 gap fill이나 synthetic score로 채우지 않는다.

local/private probe 결과는 bounded observed sample evidence다. First source view에서 노출 가능한 Chzzk metric은 `observed` 이름 또는 caveat를 유지해야 하며, full 1d/7d metric을 대체하지 않는다. 1d/7d streaming metric은 category별 distinct KST 30분 bucket이 각각 48/336개 있을 때만 full metric 후보로 해석한다. Blank category row는 viewer-hours, avg viewers, peak viewers, live count 후보에서 제외하고 skip evidence로만 남긴다.

### 4.0 Chzzk metric 후보 검증 기준

계산 가능한 값은 category-fact-eligible row에 한정한다.

- category-fact-eligible live row:
    - `categoryType`, `liveCategory`, `liveCategoryValue`, `concurrentUserCount`, `channelId`, `channelName` 이 present이고, 문자열 required field가 blank가 아니다.
    - `liveCategory` 는 candidate category id, `liveCategoryValue` 는 candidate category display name으로만 본다.
    - 현재 허용 category type 후보는 `GAME`, `SPORTS`, `ENTERTAINMENT`, `ETC` 이다.
    - `categoryType=GAME` 은 category type evidence일 뿐 canonical game identity가 아니다.
- category-fact-ineligible live row:
    - blank `categoryType` / `liveCategory` / `liveCategoryValue` row는 synthetic unknown category로 만들지 않는다.
    - 현재 candidate metric 계산에는 넣지 않고, summary의 skipped evidence로만 남긴다.
- pagination caveat:
    - bounded probe는 전체 live-list population이나 final page exhaustion 근거가 아니다.
    - bounded page cutoff 또는 last-page next cursor가 남아 있으면 public/product surface는 full population metric처럼 표현하지 않고 bounded observed sample caveat를 표시한다.
    - category union/intersection과 observed metric 값은 bounded sample 안의 evidence로만 본다.
- full coverage:
    - 30분 category bucket 하나는 category별 `concurrent_sum`, `live_count`, `top_channel_*` snapshot candidate를 만들 수 있다.
    - 1d selected window는 같은 category에 대해 KST 기준 distinct 30분 bucket 48개가 모두 있어야 full coverage다.
    - 7d selected window는 같은 category에 대해 KST 기준 distinct 30분 bucket 336개가 모두 있어야 full coverage다.
    - previous same-length delta가 필요하면 previous window도 같은 full coverage를 만족해야 한다.
    - `coverage.status=observed_bucket_only` 는 bucket candidate는 있지만 1d/7d full coverage는 없음을 뜻한다.
    - failed/partial run은 `run_status` / `result_status` / `failure` 로만 남기고 category window coverage 계산에는 포함하지 않는다.
    - top-level temporal `bucket_times` 와 observed bucket coverage는 successful comparable run의 readable category result artifact에서만 계산한다.

### 4.0.1 First Chzzk source-view observed metrics

First Chzzk source view는 category-only evidence browser다. 아래 metric은 successful comparable observed category bucket 위에서만 계산하고, `observed` naming/caveat 없이 full 1d/7d value처럼 노출하지 않는다.

| Metric | Source artifact | Grain | Formula | Unit | Null rule | Coverage rule | Full 1d/7d claim |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `viewer_hours_observed` | `category-result.jsonl` via local temporal summary | category over observed buckets | `SUM(concurrent_sum * 0.5)` | viewer-hours | no successful comparable category bucket이면 null/absent | successful comparable category-result rows only | no; 48/336 buckets required |
| `avg_viewers_observed` | `category-result.jsonl` via local temporal summary | category over observed buckets | `AVG(concurrent_sum)` | viewers | no successful comparable category bucket이면 null/absent | successful comparable category-result rows only | no; 48/336 buckets required |
| `peak_viewers_observed` | `category-result.jsonl` via local temporal summary | category over observed buckets | `MAX(concurrent_sum)` | viewers | no successful comparable category bucket이면 null/absent | successful comparable category-result rows only | no; 48/336 buckets required |
| `latest_viewers_observed` | `category-result.jsonl` / `fact_chzzk_category_30m` | category at latest observed bucket | latest deterministic fact row의 `concurrent_sum` | viewers | category row가 없으면 absent | latest row by `bucket_time DESC, collected_at DESC, ingested_at DESC` | no; bounded latest observed bucket only |
| `live_count_observed_total` | `category-result.jsonl` via local temporal summary | category over observed buckets | `SUM(live_count)` | live rows/channels in bounded sample | no successful comparable category bucket이면 null/absent | successful comparable category-result rows only | no; 48/336 buckets required |
| `viewer_per_channel_observed` | `category-result.jsonl` / `fact_chzzk_category_30m` | category over observed buckets | `SUM(concurrent_sum) / NULLIF(SUM(live_count), 0)` | viewers per observed live row | denominator 0 or non-finite output이면 null | successful comparable category-result rows only | no; not unique channels |
| `unique_channels_observed` | `fact_chzzk_category_channel_30m` where available | category over observed buckets | `COUNT(DISTINCT channel_id)` matched by `(chzzk_category_id, bucket_time)` | channels | channel fact relation/evidence가 없으면 API/web null | successful comparable observed category buckets with matching channel fact rows only | no; 48/336 buckets plus channel evidence required |

viewer_hours_1d/7d, avg_viewers_1d/7d, peak_viewers_1d/7d, live-count 기간 지표 및 각 delta는 필요한 category bucket coverage가 런타임/서빙 slice에서 입증되고 API/UI 네이밍이 정리되기 전까지 계속 비노출 상태로 둔다.

### 4.0.2 Chzzk category overview API serving shape

- Endpoint: `/chzzk/categories/overview`
- Grain: 관측된 fact bucket 기준으로 `chzzk_category_id`마다 1개 row를 반환한다.
- Source: row 생성과 window 해석은 `fact_chzzk_category_30m`를 기준으로 한다. `unique_channels_observed`는 매칭되는 `fact_chzzk_category_channel_30m` 근거가 있는 경우에만 제공한다.
- Category metadata: 각 `chzzk_category_id`의 최신 `bucket_time` row에서 `category_name` / `category_type`을 선택한다.
- API는 observed sample metrics만 노출한다.
  - `viewer_hours_observed = SUM(concurrent_sum * 0.5)`
  - `avg_viewers_observed = AVG(concurrent_sum)`
  - `peak_viewers_observed = MAX(concurrent_sum)`
  - `latest_viewers_observed = latest deterministic category row의 concurrent_sum`
  - `live_count_observed_total = SUM(live_count)`
  - `avg_channels_observed = AVG(live_count)`
  - `peak_channels_observed = MAX(live_count)`
  - `viewer_per_channel_observed = SUM(concurrent_sum) / NULLIF(SUM(live_count), 0)`
  - `unique_channels_observed = COUNT(DISTINCT channel_id)` from channel fact rows matching category observed buckets by `(chzzk_category_id, bucket_time)`
- `latest_viewers_observed`, `latest_bucket_time`, `category_name`, `category_type`
  는 같은 latest fact row에서 선택한다. Latest row ordering은 `bucket_time DESC, collected_at DESC, ingested_at DESC` 이다.
- `bucket_time_max` 는 observed aggregate window의 max bucket이고, `latest_bucket_time` 은 `latest_viewers_observed` 의 기준 bucket이다. 현재 API에서는 같은 값일 수 있지만 의미는 분리한다.
- `latest_viewers_observed` 는 full live-list current population이 아니라 bounded latest observed bucket snapshot이다. 이 이유로 `current_viewers_observed` 대신 `latest_viewers_observed` 이름을 사용한다.
- `viewer_per_channel_observed` 는 unique channel count가 아니다. Category fact의 observed `live_count` 를 분모로 한 ratio이며, denominator 0 또는 non-finite serving output은 null이다.
- `unique_channels_observed` 는 nullable observed metric이다. Optional channel fact relation 또는 matching channel evidence가 없으면 API/web payload에 null로 남긴다. Channel fact만 있는 category/bucket은 category overview row를 만들거나 count를 늘리지 않는다.
- `observed_bucket_count`는 해당 category에서 관측된 distinct 30-minute bucket 수다.
- `full_1d_candidate_available`은 `observed_bucket_count >= 48`일 때만 true다.
- `full_7d_candidate_available`은 `observed_bucket_count >= 336`일 때만 true다.
- `missing_1d_bucket_count = max(0, 48 - observed_bucket_count)`.
- `missing_7d_bucket_count = max(0, 336 - observed_bucket_count)`.
- `coverage_status`는 category별 bucket coverage 상태이며, 아래 값만 사용한다.
  - `observed_bucket_only`
  - `partial_window`
  - `full_1d_candidate_available`
  - `full_7d_candidate_available`
- 첫 API slice에서 `bounded_sample_caveat`은 항상 `"bounded_sample"` 문자열이다.
- `bounded_sample_caveat`은 bucket coverage 상태와 독립적이며, bounded pagination / live-list completeness caveat만 표시한다.
  - 즉, 이 API는 full live-list population이나 pagination exhaustion을 claim하지 않는다.
- API는 strict/full 1d/7d metrics, coverage-adjusted estimates, gap fill, interpolation, extrapolation, deltas, Steam game mapping, Combined semantics를 노출하지 않는다.

### 4.1 Avg concurrent (기본 표시)

- 정의: 기간 내 concurrent의 평균
    - avg_concurrent = AVG(concurrent_bucket)
- 현재 Chzzk 후보 조건:
    - `concurrent_bucket` 은 category-fact-eligible live rows를 category별로 합산한 `concurrent_sum` 이다.
    - bounded sample에서는 `avg_viewers_observed` 만 계산 가능하다.
    - 1d/7d avg viewers는 category별 48/336 distinct bucket full coverage 전에는 public/API/UI metric으로 승격하지 않는다.

### 4.2 Total (파생: viewer-hours)

- 정의: viewer_hours = Σ (concurrent_bucket * bucket_hours)
    - 30분 버킷이면 bucket_hours = 0.5
- 해석: “기간 동안 소비된 총 시청량(근사)”
- 현재 Chzzk 후보 조건:
    - observed sample viewer-hours는 successful comparable observed category bucket에서 `SUM(concurrent_sum * 0.5)` 로 계산한다.
    - 1d viewer-hours 후보는 category별 48개 bucket 모두가 있을 때 `SUM(concurrent_sum * 0.5)` 로 계산한다.
    - 7d viewer-hours 후보는 category별 336개 bucket 모두가 있을 때 `SUM(concurrent_sum * 0.5)` 로 계산한다.
    - bounded sample의 observed value는 1d/7d total로 해석하지 않는다.

### 4.3 Total streams (방송 수)

- 정의: 해당 bucket_time에서 라이브 채널 수(또는 카테고리 내 라이브 수)의 합/평균
- MVP에서는 bucket_time 스냅샷 기준의 live_count를 저장하고, 기간 합계/평균은 파생
- 현재 Chzzk 후보 조건:
    - bucket-level `live_count` 는 category-fact-eligible live rows의 category별 count다.
    - blank category row는 count 대상이 아니라 skipped evidence다.
    - first source view에서 기간형 live count는 `live_count_observed_total = SUM(live_count)` 로만 bounded observed sample caveat와 함께 둘 수 있다.
    - 1d/7d 기간 live count 후보도 category별 48/336 distinct bucket full coverage 전에는 public/API/UI metric으로 승격하지 않는다.
- local/private observed 후보:
    - `temporal-summary.json` category entry는 `peak_channels_observed = MAX(live_count)`, `avg_channels_observed = AVG(live_count)` 를 담을 수 있다.
    - `viewer_per_channel_observed = SUM(concurrent_sum) / NULLIF(SUM(live_count), 0)` 는 category aggregate bucket 위의 observed ratio이며, unique channels가 아니라 observed `live_count` 기반이다.
    - `unique_channels` 는 `category-result.jsonl` 만으로 계산하지 않는다. full per-live `channelId` set이 없고 `top_channel_id` 는 충분하지 않다.
    - 반복 가능한 unique-channel 계산은 persisted observed channel fact인 `fact_chzzk_category_channel_30m` 을 사용한다. 이 slice에서 public/API/UI metric으로 승격되었지만 nullable observed metric으로만 노출한다.
    - 최소 그레인: `(chzzk_category_id, bucket_time, channel_id)` category-bucket-channel evidence row.
    - Formula: `unique_channels_observed = COUNT(DISTINCT channel_id)`.
    - API/web count는 category observed bucket set에 matching되는 channel fact row만 대상으로 하며, channel-only category/bucket evidence는 overview row를 만들거나 count를 늘리지 않는다.
    - local/private input에 channel display name이 있더라도 persisted fact, summary,
      API, web surface에는 저장하거나 노출하지 않는다.
    - Blank category / category-fact-ineligible row는 channel artifact에 넣지 않고 summary skip evidence로만 남긴다.
    - observed channel fact evidence가 없으면 `unique_channels_observed` 는 API/web에서 null로 둔다. raw page를 다시 읽어 public contract를 만들지 않는다.

### 4.4 Peak viewers

- 정의: 기간 내 category bucket concurrent의 최댓값
    - peak_viewers = MAX(concurrent_bucket)
- 현재 Chzzk 후보 조건:
    - `concurrent_bucket` 은 category별 `concurrent_sum` 이다.
    - bounded sample에서는 observed bucket 안의 `peak_viewers_observed` 만 계산한다.
    - observed same-bucket 값은 1d/7d peak viewers로 해석하지 않는다.
    - 1d/7d peak viewers 후보는 category별 48/336 distinct bucket full coverage가 있을 때만 기간 metric 후보가 된다.

### 4.5 Top streamer (입구)

- 정의: bucket_time에서 concurrent가 가장 큰 채널(또는 스트리머)
- 저장: top_channel_id, top_channel_name, top_channel_concurrent

### 4.6 시청 모멘텀(Δ)

- 30분 버킷 기준으로 전일 동일 버킷 대비:
    - Δ_avg_concurrent: 동일 버킷 비교 또는 기간 평균 비교(표현 방식은 UI에서 선택)
    - Δ_viewer_hours: 일 단위 rollup이 생기면 일 스냅샷 Δ로 전환 가능
- 현재 Chzzk 후보 metric에는 delta contract가 없다. 1d/7d selected/previous window coverage와 API/UI naming이 별도 slice에서 고정되기 전까지 Combined 또는 relationship KPI로 연결하지 않는다.

## 5. 가격/할인(구매 타이밍)

### 5.1 price field

- initial_price_minor: paid price row의 할인 전 가격(최소 단위). grounded free row에서는 source가 numeric price field를 제공하지 않으므로 null을 유지한다.
- final_price_minor: paid price row의 현재 가격(최소 단위). grounded free row에서는 source가 numeric price field를 제공하지 않으므로 null을 유지한다.
- discount_percent: paid price row의 할인율(0~100). grounded free row에서는 source가 discount field를 제공하지 않으므로 null을 유지한다.
- region: MVP는 KR만. write path와 public API는 `KR` casing으로 고정하며, serving view는 legacy lowercase `kr` fact도 KR price evidence로 읽는다.
- currency_code: paid price row의 currency. grounded free row에서는 source가 currency를 제공하지 않으므로 null을 유지한다.
- is_free: filtered `price_overview` primary가 성공했지만 `price_overview` 를 제공하지 않고, no-filter full `appdetails` fallback의 `data.is_free is true` 로 확인된 free title evidence만 true로 저장한다. `is_free=false`, missing, invalid fallback payload는 free/unavailable/region-blocked/delisted 의미로 해석하지 않는다.

### 5.2 할인 이벤트(관계 KPI에 사용)

- 할인 시작: discount_percent가 0 → 양수로 전환되는 시점(또는 final < initial)
- 할인 종료: discount_percent가 양수 → 0으로 전환

### 5.3 Latest price API 서빙 형태

- latest price API는 `srv_game_latest_price`를 직접 읽는다.
- 현재 minimum path는 `tracked_game.is_active = true` 인 게임의 최신 KR 가격 행만 다룬다.
- list endpoint는 `/games/price/latest`, single-game endpoint는 `/games/{canonical_game_id}/price/latest` 이다.
- `region`은 현재 slice에서 항상 `KR` 이고, generalized region query param은 아직 없다.
- 기존 fact에 lowercase `kr`이 남아 있어도 latest price serving과 Explore price evidence에서는 누락하지 않고 `KR`로 노출한다.
- `is_free=true` row는 nullable price fields를 그대로 노출한다. latest price API와 Explore API는 free title을 fake `KRW` / `0` / `0%` 로 채우지 않는다.
- paid row는 기존처럼 `currency_code`, `initial_price_minor`, `final_price_minor`, `discount_percent` 를 제공한다.
- `price_overview` 없음 자체는 free/unavailable/region-blocked/delisted 의미가 아니다. fallback full payload에서 `data.is_free is true` 로 확인된 경우만 free evidence다.
- 현재 minimum price surface는 전일 대비 Δ 필드를 노출하지 않는다.
- 현재 minimum UI surface는 latest `bucket_time`을 `Price snapshot` 시각으로만 노출하고, sale-end timing은 API가 없어 표시하지 않는다.
- price timing/history interpretation은 별도 thin slice에서 필요성이 확인될 때만 확장한다.
- 현재 wire 예시(`/games/{id}/price/latest`):

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

Grounded free row 예시:

```json
{
  "canonical_game_id": 2,
  "canonical_name": "Free Example",
  "bucket_time": "2026-03-29T14:00:00+09:00",
  "region": "KR",
  "currency_code": null,
  "initial_price_minor": null,
  "final_price_minor": null,
  "discount_percent": null,
  "is_free": true
}
```

## 6. 랭킹(추적 유니버스 seed)

- 시장(market): KR, global 둘 다 저장
- rank_type: top_selling / top_played 등(정의는 파서에서 고정)
- rank_position: 1..N
- 사용처:
    - 대시보드 “오늘의 상위”
    - tracked_universe 자동 갱신(seed)

### 6.1 Latest rankings API 서빙 형태

- latest rankings API는 `srv_rank_latest_kr_top_selling` 를 직접 읽는다.
- 현재 minimum path는 latest KR top-selling weekly list만 다루며, generalized market/rank_type query param은 아직 없다.
- list endpoint는 `/games/rankings/latest` 이다.
- `Top Ranked` window는 list context만 바꾸고 row payload meaning은 바꾸지 않는다.
- 현재 Top Selling contract는 `window=7d` 만 지원한다.
- `window=1d|30d|90d` 는 현재 repo에 daily/monthly/quarterly topsellers source가 없어 `400` 으로 명시적으로 거절한다.
- `canonical_game_id`, `canonical_name` 은 현재 Steam mapping이 없으면 `null` 이다.
- 현재 wire 예시(`/games/rankings/latest` item):

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

## 8. Steam Observability Metrics

이 섹션은 local Prometheus exporter가 노출하는 durable metric semantics만 고정한다.
host, port, Docker Compose, local artifact path, credentials, smoke commands는 public contract가 아니며 `docs/local/` runbook에서 관리한다.

### 8.1 Scheduler latest-run metrics

- source: cadence job의 latest scheduler result evidence.
- cadence labels:
    - `ccu-30m`
    - `price-1h`
    - `daily`
    - `app-catalog-weekly`
- status labels:
    - `success`
    - `partial_success`
    - `lock_busy`
    - `hard_failure`
    - `missing`
    - `unknown`
- `steam_scheduler_latest_run_present{cadence}`:
    - latest readable result evidence가 있으면 `1`, 없으면 `0`.
- `steam_scheduler_latest_run_timestamp_seconds{cadence}`:
    - latest result의 `finished_at_utc`를 Unix timestamp seconds로 변환한다.
    - result가 없거나 timestamp를 파싱할 수 없으면 sample을 내지 않는다.
- `steam_scheduler_latest_run_status{cadence,status}`:
    - active status label만 `1`, 나머지는 `0`.
    - result가 없으면 `status="missing"` 만 `1`.
    - 알 수 없는 status value는 `status="unknown"` 으로 보존한다.
- `steam_scheduler_latest_run_duration_seconds{cadence}`:
    - latest result의 `duration_ms / 1000`.
- `steam_scheduler_latest_run_partial_success{cadence}`:
    - latest result의 `partial_success` boolean을 `1` 또는 `0`으로 변환한다.

### 8.2 Partial-success triage metrics

- `steam_scheduler_latest_ccu_missing_evidence_records{cadence="ccu-30m"}`:
    - latest `ccu-30m` result triage의 `missing_evidence_records`.
    - per-app missing evidence는 hard job failure가 아니며, partial-success triage 신호다.
- `steam_scheduler_latest_daily_reviews_skipped_records{cadence="daily"}`:
    - latest `daily` result triage의 `reviews_skipped_records`.
    - skipped review evidence는 hard job failure가 아니며, partial-success triage 신호다.

### 8.3 DB freshness metrics

- source: 현재 Postgres serving/metadata baseline.
- dataset labels:
    - `rank_daily`: `fact_steam_rank_daily.snapshot_date`
    - `reviews_daily`: `fact_steam_reviews_daily.snapshot_date`
    - `price_1h`: `fact_steam_price_1h.bucket_time`
    - `ccu_30m`: `fact_steam_ccu_30m.bucket_time`
    - `ccu_daily_rollup`: `agg_steam_ccu_daily.bucket_date`
- `steam_db_freshness_query_success`:
    - all configured freshness queries succeeded during the scrape이면 `1`, 아니면 `0`.
- `steam_db_dataset_freshness_available{dataset}`:
    - dataset latest timestamp가 query result에서 확인되면 `1`, 아니면 `0`.
- `steam_db_dataset_latest_timestamp_seconds{dataset}`:
    - dataset latest timestamp를 Unix timestamp seconds로 변환한다.
    - DATE column은 KST date의 day start로 해석한다.
- `steam_db_dataset_freshness_age_seconds{dataset}`:
    - scrape timestamp와 dataset latest timestamp 사이의 seconds.
    - clock skew 등으로 음수가 되면 `0`으로 floor 처리한다.

### 8.4 App Catalog latest summary metrics

- source: optional App Catalog latest summary handoff artifact.
- summary status labels:
    - `completed`
    - `missing`
    - `invalid`
    - `other`
- `steam_app_catalog_latest_summary_exists`:
    - summary artifact가 존재하고 valid JSON object이면 `1`, 아니면 `0`.
- `steam_app_catalog_latest_summary_status{status}`:
    - active status label만 `1`, 나머지는 `0`.
    - artifact가 없으면 `status="missing"` 이 `1`.
    - unreadable or invalid JSON이면 `status="invalid"` 이 `1`.
    - `completed` 외 status value는 `status="other"` 로 묶는다.
- `steam_app_catalog_latest_summary_finished_timestamp_seconds`:
    - summary의 `finished_at_utc`를 Unix timestamp seconds로 변환한다.
    - timestamp가 없거나 파싱할 수 없으면 sample을 내지 않는다.
- `steam_app_catalog_latest_summary_app_count`:
    - summary excerpt의 `app_count`가 integer일 때만 노출한다.
