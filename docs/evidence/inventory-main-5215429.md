# Inventory Evidence Snapshot: main @ 5215429

작성일: 2026-05-14 (KST)  
Snapshot date: 2026-05-14 (KST)  
`tracked_game` query timestamp: 2026-05-14 14:24:37 KST

이 문서는 product feature list가 아니라, 면접/review에서 inventory count 산출 기준을 확인하기 위한 최소 evidence snapshot이다.

## 기준 repo/ref

- repo: `cbbsjj0314/picking-my-time-sink`
- branch/ref: `main`
- SHA: `521542909b54e5d6a7c299f38a77f85b80a8ab5f`

## Summary

| Item | Count | Basis |
| --- | ---: | --- |
| API endpoints | 10 | automatic docs endpoint를 제외하고 FastAPI에 등록된 `method + path` |
| PostgreSQL tables | 10 | `sql/postgres/*.sql`에 정의된 `CREATE TABLE IF NOT EXISTS` DDL object |
| PostgreSQL views | 5 | `sql/postgres/*.sql`에 정의된 `CREATE OR REPLACE VIEW` DDL object |
| PostgreSQL tables + views | 15 | table + view 합계 |
| pytest test items | 337 | `pytest --collect-only -q` collection 결과 |
| test files | 52 | `tests/` 아래에서 pytest가 collect한 test file |
| `tracked_game` total rows | 146 | `.env`가 선택한 Postgres target에 대한 read-only query |
| `tracked_game` active rows | 135 | `tracked_game.is_active = true` |
| `tracked_game` inactive rows | 11 | `tracked_game.is_active = false` |

## Counting criteria

- API endpoint count는 FastAPI app에 등록된 `method + path` route 기준이다.
- FastAPI automatic docs endpoint인 `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`는 제외한다.
- PostgreSQL table/view count는 `sql/postgres/*.sql`에 정의된 DDL object 기준이다.
- PostgreSQL table/view count는 live `information_schema` inventory가 아니다.
- test count는 pytest collect-only output 기준이다.
- `tracked_game` count는 위 query timestamp에 `.env`가 선택한 Postgres DB의 live read-only snapshot이다.
- `tracked_game` count는 repo file만으로 정적으로 재현할 수 없으며, 시간이 지나면 달라질 수 있다.

## Representative command/query

```bash
PYTHONPATH=src poetry run pytest --capture=no --collect-only -q
```

```sql
select 'tracked_game_total', count(*) from tracked_game
union all
select 'tracked_game_active_true', count(*) from tracked_game where is_active = true
union all
select 'tracked_game_active_false', count(*) from tracked_game where is_active = false;
```

## API endpoints

- GET `/chzzk/categories/overview`
- GET `/games/explore/overview`
- GET `/games/ccu/latest`
- GET `/games/{canonical_game_id}/ccu/latest`
- GET `/games/{canonical_game_id}/ccu/daily-90d`
- GET `/games/price/latest`
- GET `/games/{canonical_game_id}/price/latest`
- GET `/games/reviews/latest`
- GET `/games/rankings/latest`
- GET `/games/{canonical_game_id}/reviews/latest`

## PostgreSQL DDL objects

Tables:

- `dim_game`
- `game_external_id`
- `tracked_game`
- `fact_steam_ccu_30m`
- `fact_steam_reviews_daily`
- `fact_steam_price_1h`
- `agg_steam_ccu_daily`
- `fact_steam_rank_daily`
- `fact_chzzk_category_30m`
- `fact_chzzk_category_channel_30m`

Views:

- `srv_game_latest_ccu`
- `srv_game_latest_reviews`
- `srv_game_latest_price`
- `srv_rank_latest_kr_top_selling`
- `srv_game_explore_period_metrics`

## Caveats

- 이 문서는 inventory evidence snapshot이지 README claim이나 product readiness statement가 아니다.
- API, DDL, pytest count는 위 target SHA를 기준으로 한다.
- 이 문서를 작성할 당시 target SHA와 current `main` 사이의 committed difference는 `README.md` 변경뿐이었다.
- `tracked_game` count는 live DB snapshot evidence일 뿐이며, 이후 DB state는 달라질 수 있다.
- 이 문서에는 DB host, credential, `.env` value, private path, raw provider payload, UGC-heavy content를 포함하지 않는다.
