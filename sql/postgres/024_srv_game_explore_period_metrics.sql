-- srv_game_explore_period_metrics serves the Steam Explore overview evidence table.
CREATE OR REPLACE VIEW srv_game_explore_period_metrics AS
WITH active_games AS (
    SELECT
        tg.canonical_game_id,
        dg.canonical_name,
        CASE
            WHEN gei.external_id ~ '^[0-9]+$' THEN gei.external_id::BIGINT
            ELSE NULL
        END AS steam_appid,
        tg.priority,
        tg.sources
    FROM tracked_game AS tg
    INNER JOIN dim_game AS dg
        ON dg.canonical_game_id = tg.canonical_game_id
    LEFT JOIN game_external_id AS gei
        ON gei.canonical_game_id = tg.canonical_game_id
       AND gei.source = 'steam'
    WHERE tg.is_active = TRUE
),
ccu_anchor AS (
    SELECT MAX(bucket_date) AS anchor_date
    FROM agg_steam_ccu_daily
),
ccu_window_rollups AS (
    SELECT
        ag.canonical_game_id,
        ca.anchor_date AS ccu_period_anchor_date,
        CASE
            WHEN COUNT(agg.bucket_date) FILTER (
                WHERE agg.bucket_date BETWEEN ca.anchor_date - 6 AND ca.anchor_date
            ) = 7
                THEN AVG(agg.avg_ccu) FILTER (
                    WHERE agg.bucket_date BETWEEN ca.anchor_date - 6 AND ca.anchor_date
                )
            ELSE NULL
        END AS period_avg_ccu_7d,
        CASE
            WHEN COUNT(agg.bucket_date) FILTER (
                WHERE agg.bucket_date BETWEEN ca.anchor_date - 6 AND ca.anchor_date
            ) = 7
                THEN MAX(agg.peak_ccu) FILTER (
                    WHERE agg.bucket_date BETWEEN ca.anchor_date - 6 AND ca.anchor_date
                )
            ELSE NULL
        END AS period_peak_ccu_7d,
        CASE
            WHEN COUNT(agg.bucket_date) FILTER (
                WHERE agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date - 7
            ) = 7
                THEN AVG(agg.avg_ccu) FILTER (
                    WHERE agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date - 7
                )
            ELSE NULL
        END AS previous_period_avg_ccu_7d,
        CASE
            WHEN COUNT(agg.bucket_date) FILTER (
                WHERE agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date - 7
            ) = 7
                THEN MAX(agg.peak_ccu) FILTER (
                    WHERE agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date - 7
                )
            ELSE NULL
        END AS previous_period_peak_ccu_7d
    FROM active_games AS ag
    CROSS JOIN ccu_anchor AS ca
    LEFT JOIN agg_steam_ccu_daily AS agg
        ON agg.canonical_game_id = ag.canonical_game_id
       AND agg.bucket_date BETWEEN ca.anchor_date - 13 AND ca.anchor_date
    GROUP BY ag.canonical_game_id, ca.anchor_date
),
ccu_period_metrics AS (
    SELECT
        canonical_game_id,
        ccu_period_anchor_date,
        period_avg_ccu_7d,
        period_peak_ccu_7d,
        CASE
            WHEN period_avg_ccu_7d IS NULL OR previous_period_avg_ccu_7d IS NULL
                THEN NULL
            ELSE period_avg_ccu_7d - previous_period_avg_ccu_7d
        END AS delta_period_avg_ccu_7d_abs,
        CASE
            WHEN period_avg_ccu_7d IS NULL
              OR previous_period_avg_ccu_7d IS NULL
              OR previous_period_avg_ccu_7d <= 0.0
                THEN NULL
            ELSE ((period_avg_ccu_7d - previous_period_avg_ccu_7d)
                / previous_period_avg_ccu_7d) * 100.0
        END AS delta_period_avg_ccu_7d_pct,
        CASE
            WHEN period_peak_ccu_7d IS NULL OR previous_period_peak_ccu_7d IS NULL
                THEN NULL
            ELSE period_peak_ccu_7d - previous_period_peak_ccu_7d
        END AS delta_period_peak_ccu_7d_abs,
        CASE
            WHEN period_peak_ccu_7d IS NULL
              OR previous_period_peak_ccu_7d IS NULL
              OR previous_period_peak_ccu_7d <= 0
                THEN NULL
            ELSE ((period_peak_ccu_7d - previous_period_peak_ccu_7d)::DOUBLE PRECISION
                / previous_period_peak_ccu_7d::DOUBLE PRECISION) * 100.0
        END AS delta_period_peak_ccu_7d_pct
    FROM ccu_window_rollups
),
review_anchor AS (
    SELECT MAX(snapshot_date) AS anchor_date
    FROM fact_steam_reviews_daily
),
review_boundaries AS (
    SELECT
        ag.canonical_game_id,
        current_reviews.snapshot_date AS reviews_snapshot_date,
        current_reviews.total_reviews,
        current_reviews.total_positive,
        current_reviews.total_negative,
        current_reviews.positive_ratio,
        boundary_7d.total_reviews AS boundary_7d_total_reviews,
        boundary_7d.total_positive AS boundary_7d_total_positive,
        boundary_30d.total_reviews AS boundary_30d_total_reviews,
        boundary_30d.total_positive AS boundary_30d_total_positive
    FROM active_games AS ag
    CROSS JOIN review_anchor AS ra
    LEFT JOIN fact_steam_reviews_daily AS current_reviews
        ON current_reviews.canonical_game_id = ag.canonical_game_id
       AND current_reviews.snapshot_date = ra.anchor_date
    LEFT JOIN fact_steam_reviews_daily AS boundary_7d
        ON boundary_7d.canonical_game_id = ag.canonical_game_id
       AND boundary_7d.snapshot_date = ra.anchor_date - 7
    LEFT JOIN fact_steam_reviews_daily AS boundary_30d
        ON boundary_30d.canonical_game_id = ag.canonical_game_id
       AND boundary_30d.snapshot_date = ra.anchor_date - 30
),
review_deltas AS (
    SELECT
        canonical_game_id,
        reviews_snapshot_date,
        total_reviews,
        total_positive,
        total_negative,
        positive_ratio,
        CASE
            WHEN total_reviews IS NULL OR boundary_7d_total_reviews IS NULL
                THEN NULL
            WHEN total_reviews - boundary_7d_total_reviews < 0
                THEN NULL
            ELSE total_reviews - boundary_7d_total_reviews
        END AS reviews_added_7d,
        CASE
            WHEN total_positive IS NULL OR boundary_7d_total_positive IS NULL
                THEN NULL
            WHEN total_positive - boundary_7d_total_positive < 0
                THEN NULL
            ELSE total_positive - boundary_7d_total_positive
        END AS positive_added_7d,
        CASE
            WHEN total_reviews IS NULL OR boundary_30d_total_reviews IS NULL
                THEN NULL
            WHEN total_reviews - boundary_30d_total_reviews < 0
                THEN NULL
            ELSE total_reviews - boundary_30d_total_reviews
        END AS reviews_added_30d,
        CASE
            WHEN total_positive IS NULL OR boundary_30d_total_positive IS NULL
                THEN NULL
            WHEN total_positive - boundary_30d_total_positive < 0
                THEN NULL
            ELSE total_positive - boundary_30d_total_positive
        END AS positive_added_30d
    FROM review_boundaries
),
review_period_metrics AS (
    SELECT
        canonical_game_id,
        reviews_snapshot_date,
        total_reviews,
        total_positive,
        total_negative,
        positive_ratio,
        reviews_added_7d,
        reviews_added_30d,
        CASE
            WHEN reviews_added_7d IS NULL
              OR reviews_added_7d <= 0
              OR positive_added_7d IS NULL
              OR positive_added_7d < 0
              OR positive_added_7d > reviews_added_7d
                THEN NULL
            ELSE positive_added_7d::DOUBLE PRECISION / reviews_added_7d::DOUBLE PRECISION
        END AS period_positive_ratio_7d,
        CASE
            WHEN reviews_added_30d IS NULL
              OR reviews_added_30d <= 0
              OR positive_added_30d IS NULL
              OR positive_added_30d < 0
              OR positive_added_30d > reviews_added_30d
                THEN NULL
            ELSE positive_added_30d::DOUBLE PRECISION / reviews_added_30d::DOUBLE PRECISION
        END AS period_positive_ratio_30d
    FROM review_deltas
)
SELECT
    ag.canonical_game_id,
    ag.canonical_name,
    ag.steam_appid,
    ag.priority,
    ag.sources,
    latest_ccu.bucket_time AS ccu_bucket_time,
    latest_ccu.latest_ccu AS current_ccu,
    latest_ccu.delta_ccu_day AS current_delta_ccu_abs,
    CASE
        WHEN latest_ccu.delta_ccu_day IS NULL
          OR latest_ccu.prev_day_same_bucket_ccu IS NULL
          OR latest_ccu.prev_day_same_bucket_ccu <= 0
            THEN NULL
        ELSE (latest_ccu.delta_ccu_day::DOUBLE PRECISION
            / latest_ccu.prev_day_same_bucket_ccu::DOUBLE PRECISION) * 100.0
    END AS current_delta_ccu_pct,
    (latest_ccu.prev_day_same_bucket_ccu IS NULL) AS current_ccu_missing_flag,
    cpm.ccu_period_anchor_date,
    cpm.period_avg_ccu_7d,
    cpm.period_peak_ccu_7d,
    cpm.delta_period_avg_ccu_7d_abs,
    cpm.delta_period_avg_ccu_7d_pct,
    cpm.delta_period_peak_ccu_7d_abs,
    cpm.delta_period_peak_ccu_7d_pct,
    rpm.reviews_snapshot_date,
    rpm.total_reviews,
    rpm.total_positive,
    rpm.total_negative,
    rpm.positive_ratio,
    rpm.reviews_added_7d,
    rpm.reviews_added_30d,
    rpm.period_positive_ratio_7d,
    rpm.period_positive_ratio_30d,
    latest_price.bucket_time AS price_bucket_time,
    latest_price.region,
    latest_price.currency_code,
    latest_price.initial_price_minor,
    latest_price.final_price_minor,
    latest_price.discount_percent,
    latest_price.is_free
FROM active_games AS ag
LEFT JOIN srv_game_latest_ccu AS latest_ccu
    ON latest_ccu.canonical_game_id = ag.canonical_game_id
LEFT JOIN ccu_period_metrics AS cpm
    ON cpm.canonical_game_id = ag.canonical_game_id
LEFT JOIN review_period_metrics AS rpm
    ON rpm.canonical_game_id = ag.canonical_game_id
LEFT JOIN srv_game_latest_price AS latest_price
    ON latest_price.canonical_game_id = ag.canonical_game_id;
