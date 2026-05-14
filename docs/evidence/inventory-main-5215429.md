# Inventory Evidence Snapshot: main @ 5215429

작성일: 2026-05-14 (KST)  
Snapshot date: 2026-05-14 (KST)  
`tracked_game` query timestamp: 2026-05-14 14:24:37 KST

이 문서는 product feature list가 아니라, 면접/리뷰 시 inventory count의
산출 기준을 확인하기 위한 최소 evidence snapshot이다.

## 기준 repo/ref

- repo: `cbbsjj0314/picking-my-time-sink`
- branch/ref: `main`
- SHA: `521542909b54e5d6a7c299f38a77f85b80a8ab5f`

## Summary

| Item | Count | Basis |
| --- | ---: | --- |
| API endpoints | 10 | Registered FastAPI `method + path`, excluding automatic docs endpoints |
| PostgreSQL tables | 10 | DDL-defined `CREATE TABLE IF NOT EXISTS` objects in `sql/postgres/*.sql` |
| PostgreSQL views | 5 | DDL-defined `CREATE OR REPLACE VIEW` objects in `sql/postgres/*.sql` |
| PostgreSQL tables + views | 15 | Tables + views |
| pytest test items | 337 | `pytest --collect-only -q` collection result |
| test files | 52 | pytest-collected files under `tests/` |
| `tracked_game` total rows | 146 | Read-only query against the `.env`-selected Postgres target |
| `tracked_game` active rows | 135 | `tracked_game.is_active = true` |
| `tracked_game` inactive rows | 11 | `tracked_game.is_active = false` |

## Counting criteria

- API endpoint count is based on `method + path` routes registered on the FastAPI app.
- FastAPI automatic docs endpoints are excluded: `/docs`, `/redoc`, `/openapi.json`, and `/docs/oauth2-redirect`.
- PostgreSQL table/view counts are based on DDL objects defined in `sql/postgres/*.sql`.
- PostgreSQL table/view counts are not a live `information_schema` inventory.
- Test count is based on pytest collect-only output.
- `tracked_game` counts are a live read-only snapshot from the Postgres DB selected by `.env` at the query timestamp above.
- `tracked_game` counts are not statically reproducible from repo files and may change over time.

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

- This is an inventory evidence snapshot, not a README claim or product readiness statement.
- API, DDL, and pytest counts are tied to the target SHA above.
- At the time this document was prepared, the committed difference from the target SHA to current `main` was limited to `README.md`.
- `tracked_game` counts are live DB snapshot evidence only; later DB state may differ.
- No DB host, credential, `.env` value, private path, raw provider payload, or UGC-heavy content is included here.
