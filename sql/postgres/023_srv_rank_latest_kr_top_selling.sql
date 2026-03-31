-- srv_rank_latest_kr_top_selling serves the latest KR top-selling ranking list.
CREATE OR REPLACE VIEW srv_rank_latest_kr_top_selling AS
WITH latest_snapshot AS (
    SELECT MAX(snapshot_date) AS snapshot_date
    FROM fact_steam_rank_daily
    WHERE market = 'kr'
      AND rank_type = 'top_selling'
),
latest_rows AS (
    SELECT
        f.snapshot_date,
        f.rank_position,
        f.steam_appid,
        COALESCE(f.canonical_game_id, gei.canonical_game_id) AS canonical_game_id
    FROM fact_steam_rank_daily AS f
    INNER JOIN latest_snapshot AS ls
        ON ls.snapshot_date = f.snapshot_date
    LEFT JOIN game_external_id AS gei
        ON gei.source = 'steam'
       AND gei.external_id = f.steam_appid::text
    WHERE f.market = 'kr'
      AND f.rank_type = 'top_selling'
)
SELECT
    lr.snapshot_date,
    lr.rank_position,
    lr.steam_appid,
    lr.canonical_game_id,
    dg.canonical_name
FROM latest_rows AS lr
LEFT JOIN dim_game AS dg
    ON dg.canonical_game_id = lr.canonical_game_id
ORDER BY lr.rank_position ASC;
