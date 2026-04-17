-- srv_game_latest_price serves the latest KR price snapshot for active tracked games.
CREATE OR REPLACE VIEW srv_game_latest_price AS
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
        'KR'::TEXT AS region,
        f.currency_code,
        f.initial_price_minor,
        f.final_price_minor,
        f.discount_percent,
        f.is_free,
        f.collected_at
    FROM fact_steam_price_1h AS f
    INNER JOIN active_games AS ag
        ON ag.canonical_game_id = f.canonical_game_id
    WHERE UPPER(f.region) = 'KR'
    ORDER BY
        f.canonical_game_id,
        f.bucket_time DESC,
        f.collected_at DESC,
        CASE WHEN f.region = 'KR' THEN 0 ELSE 1 END
)
SELECT
    l.canonical_game_id,
    dg.canonical_name,
    gei.external_id AS steam_external_id,
    ag.priority,
    ag.sources,
    l.bucket_time,
    l.region,
    l.currency_code,
    l.initial_price_minor,
    l.final_price_minor,
    l.discount_percent,
    l.is_free,
    l.collected_at
FROM latest_per_game AS l
INNER JOIN active_games AS ag
    ON ag.canonical_game_id = l.canonical_game_id
INNER JOIN dim_game AS dg
    ON dg.canonical_game_id = l.canonical_game_id
LEFT JOIN game_external_id AS gei
    ON gei.canonical_game_id = l.canonical_game_id
   AND gei.source = 'steam';
