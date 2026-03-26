-- srv_game_latest_reviews serves the latest reviews snapshot with day-over-day deltas.
CREATE OR REPLACE VIEW srv_game_latest_reviews AS
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
        f.snapshot_date,
        f.total_reviews,
        f.total_positive,
        f.total_negative,
        f.positive_ratio,
        f.collected_at
    FROM fact_steam_reviews_daily AS f
    INNER JOIN active_games AS ag
        ON ag.canonical_game_id = f.canonical_game_id
    ORDER BY f.canonical_game_id, f.snapshot_date DESC
)
SELECT
    l.canonical_game_id,
    dg.canonical_name,
    gei.external_id AS steam_external_id,
    ag.priority,
    ag.sources,
    l.snapshot_date,
    l.collected_at,
    l.total_reviews,
    l.total_positive,
    l.total_negative,
    l.positive_ratio,
    prev.total_reviews AS prev_day_total_reviews,
    prev.positive_ratio AS prev_day_positive_ratio,
    CASE
        WHEN prev.total_reviews IS NULL THEN NULL
        ELSE l.total_reviews - prev.total_reviews
    END AS delta_total_reviews,
    CASE
        WHEN prev.positive_ratio IS NULL THEN NULL
        ELSE l.positive_ratio - prev.positive_ratio
    END AS delta_positive_ratio
FROM latest_per_game AS l
INNER JOIN active_games AS ag
    ON ag.canonical_game_id = l.canonical_game_id
INNER JOIN dim_game AS dg
    ON dg.canonical_game_id = l.canonical_game_id
LEFT JOIN game_external_id AS gei
    ON gei.canonical_game_id = l.canonical_game_id
   AND gei.source = 'steam'
LEFT JOIN fact_steam_reviews_daily AS prev
    ON prev.canonical_game_id = l.canonical_game_id
   AND prev.snapshot_date = l.snapshot_date - 1;
