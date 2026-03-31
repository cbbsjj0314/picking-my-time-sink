문서 목적: Steam-only scheduled pipeline minimum handoff를 current repo 기준으로 1개 문서에 고정
버전: v0.1 (manual handoff baseline)
작성일: 2026-03-31 (KST)

## 0. 현재 범위

- current runtime scope는 Steam-only 이다.
- 이 문서가 고정하는 minimum path는 아래까지다.
  - ranking payload refresh
  - tracked_universe update
  - ranking gold upsert
  - price / reviews / ccu fetch -> silver normalize -> gold upsert
- handoff 단위는 local runtime artifact(`tmp/steam/...`)와 Postgres update 이다.
- 새 scheduler automation / wrapper는 추가하지 않는다.

## 1. 선행조건

### 1.1 실행 환경

- repo root에서 실행한다.
- Python 의존성은 이미 `poetry install` 된 상태를 전제로 한다.
- 모든 entrypoint는 `poetry run python -m ...` 형태로 실행한다.
- `tmp/steam/...` 아래에 파일을 쓸 수 있어야 한다.
- Steam HTTP endpoint에 outbound network가 가능해야 한다.

### 1.2 환경변수

- 아래 환경변수는 DB를 읽거나 쓰는 단계에서 필수다.
  - `POSTGRES_HOST`
  - `POSTGRES_DB`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`
- `POSTGRES_PORT`는 없으면 기본 `5432`를 사용한다.
- `STEAM_API_KEY`는 이 runbook의 필수값이 아니다.
  - `fetch_ccu_30m`는 값이 있으면 함께 사용하고, 없어도 동작 가능하다.
  - `tmp/steam/app_catalog/latest.summary.json` 를 별도로 새로 만들고 싶다면 `fetch_app_catalog_weekly` 실행 시 `STEAM_API_KEY`가 필요하다.

### 1.3 DB 선행조건

- 아래 SQL은 이미 `POSTGRES_DB`에 적용되어 있어야 한다.
  - `sql/postgres/001_dim_game.sql`
  - `sql/postgres/002_game_external_id.sql`
  - `sql/postgres/003_tracked_game.sql`
  - `sql/postgres/010_fact_steam_ccu_30m.sql`
  - `sql/postgres/011_fact_steam_reviews_daily.sql`
  - `sql/postgres/012_fact_steam_price_1h.sql`
  - `sql/postgres/014_fact_steam_rank_daily.sql`
- latest serving까지 같이 확인하려면 아래 view도 적용되어 있어야 한다.
  - `sql/postgres/020_srv_game_latest_ccu.sql`
  - `sql/postgres/021_srv_game_latest_reviews.sql`
  - `sql/postgres/022_srv_game_latest_price.sql`
  - `sql/postgres/023_srv_rank_latest_kr_top_selling.sql`
- 이번 slice는 schema / API / data semantics를 바꾸지 않는다. 필요한 relation이 없으면 여기서 멈추고 별도 DB bootstrap로 해결한다.

### 1.4 Artifact 선행조건

- required ranking payload 4종은 1단계에서 직접 refresh 한다.
  - `tmp/steam/rankings/topsellers_global.payload.json`
  - `tmp/steam/rankings/topsellers_kr.payload.json`
  - `tmp/steam/rankings/mostplayed_global.payload.json`
  - `tmp/steam/rankings/mostplayed_kr.payload.json`
- `tmp/steam/app_catalog/latest.summary.json` 는 optional artifact다.
  - 없거나 읽기 실패여도 tracked_universe run은 warning만 남기고 계속 진행한다.
- 이 runbook은 operator ambiguity를 줄이기 위해 아래 scratch path를 고정해서 쓴다.
  - `tmp/steam/handoff/price.bronze.jsonl`
  - `tmp/steam/handoff/price.silver.jsonl`
  - `tmp/steam/handoff/price.gold-result.jsonl`
  - `tmp/steam/handoff/reviews.bronze.jsonl`
  - `tmp/steam/handoff/reviews.silver.jsonl`
  - `tmp/steam/handoff/reviews.gold-result.jsonl`
  - `tmp/steam/handoff/ccu.bronze.jsonl`
  - `tmp/steam/handoff/ccu.silver.jsonl`
  - `tmp/steam/handoff/ccu.gold-result.jsonl`
- 위 scratch file은 rerun 시 덮어쓴다. 어떤 단계가 hard-fail 하면 이전 run의 파일을 재사용하지 말고 그 단계부터 다시 실행한다.

## 2. 실행 순서

1. `run_tracked_universe_scheduled` 로 ranking payload 4종을 refresh 하고 tracked target을 갱신한다.
2. `payload_to_gold_rankings` 로 같은 payload를 `fact_steam_rank_daily`에 올린다.
3. `price`, `reviews`, `ccu`는 모두 updated `tracked_game`을 읽는다.
4. 3단계 이후 세 branch는 서로 독립이지만, minimum handoff 문서에서는 operator confusion을 줄이기 위해 `price -> reviews -> ccu` 순서로 직렬 실행한다.

## 3. 단계별 명령과 handoff

### 3.1 Ranking payload refresh + tracked_universe update

- 목적:
  - Steam ranking payload 4종을 current runtime artifact 경로에 refresh 한다.
  - merged ranking candidate를 기준으로 `dim_game`, `game_external_id`, `tracked_game`를 갱신한다.
- 명령:

```bash
poetry run python -m steam.ingest.run_tracked_universe_scheduled \
  --result-path tmp/steam/tracked_universe/update_result.jsonl
```

- 읽는 입력:
  - Steam rankings service 4종
  - optional `tmp/steam/app_catalog/latest.summary.json`
  - Postgres `dim_game`, `game_external_id`, `tracked_game`
- 쓰는 산출물:
  - `tmp/steam/rankings/topsellers_global.payload.json`
  - `tmp/steam/rankings/topsellers_kr.payload.json`
  - `tmp/steam/rankings/mostplayed_global.payload.json`
  - `tmp/steam/rankings/mostplayed_kr.payload.json`
  - `tmp/steam/tracked_universe/update_result.jsonl`
  - Postgres `dim_game`, `game_external_id`, `tracked_game`
- 실패 시 중단 지점:
  - ranking fetch 실패
  - ranking payload decode 실패 또는 zero-row payload
  - DB env 누락 / DB 연결 실패
- 현재 의도된 한계:
  - optional App Catalog summary는 metadata log 용도만 있고, missing/unreadable 이어도 run을 막지 않는다.
  - `tracked_game.sources` 는 current-run attribution만 유지한다.
  - current slice에는 deactivate / cull / catalog-driven filtering이 없다.

### 3.2 Ranking gold upsert

- 목적:
  - refreshed ranking payload를 `fact_steam_rank_daily`에 적재한다.
  - 이 단계는 `game_external_id` current mapping을 읽으므로, 같은 run에서 새 매핑을 최대한 반영하려고 3.1 다음에 둔다.
- 명령:

```bash
poetry run python -m steam.normalize.payload_to_gold_rankings \
  --result-path tmp/steam/rankings/payload_to_gold_result.jsonl
```

- 읽는 입력:
  - `tmp/steam/rankings/*.payload.json`
  - Postgres `game_external_id`
- 쓰는 산출물:
  - Postgres `fact_steam_rank_daily`
  - `tmp/steam/rankings/payload_to_gold_result.jsonl`
  - `tmp/steam/run-meta/payload_to_gold_rankings/<timestamp>.meta.json`
- 실패 시 중단 지점:
  - required payload missing / unreadable / JSON decode failure
  - payload parse 결과 zero-row
  - DB env 누락 / DB 연결 실패
- 현재 의도된 한계:
  - `collected_at` 와 `snapshot_date` 는 payload file mtime 기준으로 고정된다.
  - 3.1 이후에도 미해결인 appid는 `canonical_game_id = null` 로 남을 수 있다.

### 3.3 Price branch

- 목적:
  - `tracked_game.is_active = true` 인 Steam target의 KR 가격을 1시간 bucket fact로 적재한다.
- 명령:

```bash
poetry run python -m steam.ingest.fetch_price_1h \
  --output-path tmp/steam/handoff/price.bronze.jsonl

poetry run python -m steam.normalize.bronze_to_silver_price \
  --input-path tmp/steam/handoff/price.bronze.jsonl \
  --output-path tmp/steam/handoff/price.silver.jsonl

poetry run python -m steam.normalize.silver_to_gold_price \
  --input-path tmp/steam/handoff/price.silver.jsonl \
  --result-path tmp/steam/handoff/price.gold-result.jsonl
```

- 읽는 입력:
  - fetch: Postgres `tracked_game`, `game_external_id`
  - normalize: `tmp/steam/handoff/price.bronze.jsonl`
  - gold: `tmp/steam/handoff/price.silver.jsonl`
- 쓰는 산출물:
  - `tmp/steam/handoff/price.bronze.jsonl`
  - `tmp/steam/handoff/price.silver.jsonl`
  - `tmp/steam/handoff/price.gold-result.jsonl`
  - Postgres `fact_steam_price_1h`
  - `tmp/steam/run-meta/fetch_price_1h/<timestamp>.meta.json`
  - `tmp/steam/run-meta/silver_to_gold_price/<timestamp>.meta.json`
- 실패 시 중단 지점:
  - fetch 단계의 DB env 누락 / DB 연결 실패 / unexpected runtime error
  - normalize 입력 JSONL 손상
  - gold 단계의 DB env 누락 / DB 연결 실패
- 현재 의도된 한계:
  - per-app HTTP 실패나 invalid payload는 bronze row로 남고, normalize 단계에서 loadable KR paid-price row만 통과한다.
  - current slice는 KR only 이고, `is_free` 는 `null` 유지다.

### 3.4 Reviews branch

- 목적:
  - `tracked_game.is_active = true` 인 Steam target의 daily reviews snapshot을 적재한다.
- 명령:

```bash
poetry run python -m steam.ingest.fetch_reviews_daily \
  --output-path tmp/steam/handoff/reviews.bronze.jsonl

poetry run python -m steam.normalize.bronze_to_silver_reviews \
  --input-path tmp/steam/handoff/reviews.bronze.jsonl \
  --output-path tmp/steam/handoff/reviews.silver.jsonl

poetry run python -m steam.normalize.silver_to_gold_reviews \
  --input-path tmp/steam/handoff/reviews.silver.jsonl \
  --result-path tmp/steam/handoff/reviews.gold-result.jsonl
```

- 읽는 입력:
  - fetch: Postgres `tracked_game`, `game_external_id`
  - normalize: `tmp/steam/handoff/reviews.bronze.jsonl`
  - gold: `tmp/steam/handoff/reviews.silver.jsonl`
- 쓰는 산출물:
  - `tmp/steam/handoff/reviews.bronze.jsonl`
  - `tmp/steam/handoff/reviews.silver.jsonl`
  - `tmp/steam/handoff/reviews.gold-result.jsonl`
  - Postgres `fact_steam_reviews_daily`
  - `tmp/steam/run-meta/fetch_reviews_daily/<timestamp>.meta.json`
  - `tmp/steam/run-meta/silver_to_gold_reviews/<timestamp>.meta.json`
- 실패 시 중단 지점:
  - fetch 단계의 DB env 누락 / DB 연결 실패 / unexpected runtime error
  - normalize 입력 JSONL 손상
  - gold 단계의 DB env 누락 / DB 연결 실패
- 현재 의도된 한계:
  - per-app HTTP 실패나 invalid review count는 bronze/silver에 남을 수 있고, gold 단계에서 `skipped_reason` row로 건너뛴다.
  - current slice는 latest snapshot only 이고, broader history / filter generalization은 포함하지 않는다.

### 3.5 CCU branch

- 목적:
  - `tracked_game.is_active = true` 인 Steam target의 30분 CCU snapshot을 적재한다.
- 명령:

```bash
poetry run python -m steam.ingest.fetch_ccu_30m \
  --output-path tmp/steam/handoff/ccu.bronze.jsonl

poetry run python -m steam.normalize.bronze_to_silver_ccu \
  --input-path tmp/steam/handoff/ccu.bronze.jsonl \
  --output-path tmp/steam/handoff/ccu.silver.jsonl

poetry run python -m steam.normalize.silver_to_gold_ccu \
  --input-path tmp/steam/handoff/ccu.silver.jsonl \
  --result-path tmp/steam/handoff/ccu.gold-result.jsonl
```

- 읽는 입력:
  - fetch: Postgres `tracked_game`, `game_external_id`
  - normalize: `tmp/steam/handoff/ccu.bronze.jsonl`
  - gold: `tmp/steam/handoff/ccu.silver.jsonl`
- 쓰는 산출물:
  - `tmp/steam/handoff/ccu.bronze.jsonl`
  - `tmp/steam/handoff/ccu.silver.jsonl`
  - `tmp/steam/handoff/ccu.gold-result.jsonl`
  - Postgres `fact_steam_ccu_30m`
  - `tmp/steam/run-meta/fetch_ccu_30m/<timestamp>.meta.json`
  - `tmp/steam/run-meta/silver_to_gold_ccu/<timestamp>.meta.json`
- 실패 시 중단 지점:
  - fetch 단계의 DB env 누락 / DB 연결 실패 / unexpected runtime error
  - normalize 입력 JSONL 손상
  - gold 단계의 DB env 누락 / DB 연결 실패
- 현재 의도된 한계:
  - 404 / empty / invalid payload는 bronze/silver row의 `missing_reason` 으로 남을 수 있다.
  - `fetch_ccu_30m` 는 이런 row가 있으면 execution meta `success=false` 일 수 있지만 bronze file은 쓴다.
  - `silver_to_gold_ccu` 는 `ccu` 가 없는 row를 skip 하고, previous-day same bucket delta는 existing gold row가 있을 때만 계산한다.

## 4. 최소 확인

- local artifact 확인:
  - `tmp/steam/tracked_universe/update_result.jsonl`
  - `tmp/steam/rankings/payload_to_gold_result.jsonl`
  - `tmp/steam/handoff/price.gold-result.jsonl`
  - `tmp/steam/handoff/reviews.gold-result.jsonl`
  - `tmp/steam/handoff/ccu.gold-result.jsonl`
- run-meta 확인:
  - `tmp/steam/run-meta/payload_to_gold_rankings/...`
  - `tmp/steam/run-meta/fetch_price_1h/...`
  - `tmp/steam/run-meta/silver_to_gold_price/...`
  - `tmp/steam/run-meta/fetch_reviews_daily/...`
  - `tmp/steam/run-meta/silver_to_gold_reviews/...`
  - `tmp/steam/run-meta/fetch_ccu_30m/...`
  - `tmp/steam/run-meta/silver_to_gold_ccu/...`
- DB spot check 예시:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h "$POSTGRES_HOST" \
  -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "select max(snapshot_date) as rank_snapshot_date, count(*) as rank_rows from fact_steam_rank_daily;"

PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h "$POSTGRES_HOST" \
  -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "select max(bucket_time) as price_bucket_time, count(*) as price_rows from fact_steam_price_1h;"

PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h "$POSTGRES_HOST" \
  -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "select max(snapshot_date) as reviews_snapshot_date, count(*) as reviews_rows from fact_steam_reviews_daily;"

PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h "$POSTGRES_HOST" \
  -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "select max(bucket_time) as ccu_bucket_time, count(*) as ccu_rows from fact_steam_ccu_30m;"
```

## 5. 이번 slice에서 명시적으로 defer한 것

- thin scheduler entrypoint 또는 single-command wrapper 추가
- App Catalog external scheduling 운영화
- App Catalog JSONL snapshot / latest summary의 weekly 운영 runbook 본문화
- Parquet / MinIO handoff
- tracked_universe deactivate / catalog-driven filtering semantics
- price free / unavailable semantics 확장
- reviews generalized history / parameter 확장
- CCU daily rollup / 90일 serving verification
