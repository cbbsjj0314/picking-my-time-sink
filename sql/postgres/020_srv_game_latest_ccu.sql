-- srv_game_latest_ccu serves latest snapshot + day-over-day same-bucket delta.
CREATE OR REPLACE VIEW srv_game_latest_ccu AS
WITH active_games AS (
    SELECT
        tg.canonical_game_id,
        tg.priority,
        tg.sources
    FROM tracked_game AS tg
    WHERE tg.is_active = TRUE
),
latest_per_game AS (
    SELECT DISTINCT ON (f.canonical_game_id)
        f.canonical_game_id,
        f.bucket_time,
        f.ccu AS latest_ccu,
        f.collected_at
    FROM fact_steam_ccu_30m AS f
    INNER JOIN active_games AS ag
        ON ag.canonical_game_id = f.canonical_game_id
    ORDER BY f.canonical_game_id, f.bucket_time DESC
)
SELECT
    l.canonical_game_id,
    dg.canonical_name,
    gei.external_id AS steam_external_id,
    ag.priority,
    ag.sources,
    l.bucket_time,
    l.collected_at,
    l.latest_ccu,
    prev.ccu AS prev_day_same_bucket_ccu,
    CASE
        WHEN prev.ccu IS NULL THEN NULL
        ELSE l.latest_ccu - prev.ccu
    END AS delta_ccu_day
FROM latest_per_game AS l
INNER JOIN active_games AS ag
    ON ag.canonical_game_id = l.canonical_game_id
INNER JOIN dim_game AS dg
    ON dg.canonical_game_id = l.canonical_game_id
LEFT JOIN game_external_id AS gei
    ON gei.canonical_game_id = l.canonical_game_id
   AND gei.source = 'steam'
LEFT JOIN fact_steam_ccu_30m AS prev
    ON prev.canonical_game_id = l.canonical_game_id
   AND prev.bucket_time = l.bucket_time - INTERVAL '1 day';
