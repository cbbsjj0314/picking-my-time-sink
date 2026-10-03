-- Activity dimensions use persisted evidence within the Steam-anchored KST window.
CREATE OR REPLACE VIEW srv_combined_game_activity_7d AS
WITH trusted_categories AS (
    SELECT DISTINCT mapped_canonical_game_id, chzzk_category_id
    FROM srv_chzzk_category_game_mapping
),
mapped_games AS (
    SELECT mapped_canonical_game_id, COUNT(DISTINCT chzzk_category_id) AS category_count
    FROM trusted_categories
    GROUP BY mapped_canonical_game_id
),
shared_windows AS (
    SELECT DISTINCT ccu_period_anchor_date AS anchor_date
    FROM srv_game_explore_period_metrics
    WHERE ccu_period_anchor_date IS NOT NULL
),
window_facts AS (
    SELECT shared_window.anchor_date, fact.chzzk_category_id, fact.bucket_time, fact.concurrent_sum
    FROM shared_windows AS shared_window
    INNER JOIN fact_chzzk_category_30m AS fact
        ON fact.bucket_time >= ((shared_window.anchor_date - 6)::TIMESTAMP AT TIME ZONE 'Asia/Seoul')
       AND fact.bucket_time < ((shared_window.anchor_date + 1)::TIMESTAMP AT TIME ZONE 'Asia/Seoul')
),
collection_buckets AS (
    SELECT anchor_date, COUNT(DISTINCT bucket_time) AS collection_bucket_count
    FROM window_facts
    GROUP BY anchor_date
),
game_buckets AS (
    SELECT
        mapping.mapped_canonical_game_id AS canonical_game_id,
        fact.anchor_date,
        fact.bucket_time,
        SUM(fact.concurrent_sum) AS game_bucket_observed_viewers
    FROM window_facts AS fact
    INNER JOIN trusted_categories AS mapping
        ON mapping.chzzk_category_id = fact.chzzk_category_id
    GROUP BY mapping.mapped_canonical_game_id, fact.anchor_date, fact.bucket_time
),
game_activity AS (
    SELECT
        canonical_game_id,
        anchor_date,
        SUM(game_bucket_observed_viewers * 0.5) AS viewer_hours,
        MAX(game_bucket_observed_viewers) AS peak_viewers,
        COUNT(DISTINCT bucket_time) AS observed_bucket_count,
        MAX(bucket_time) AS latest_observed_bucket
    FROM game_buckets
    GROUP BY canonical_game_id, anchor_date
)
SELECT
    steam.canonical_game_id,
    steam.canonical_name,
    steam.steam_appid,
    steam.ccu_period_anchor_date,
    steam.period_avg_ccu_7d,
    steam.period_peak_ccu_7d,
    mapping.category_count AS chzzk_mapped_category_count,
    activity.viewer_hours AS chzzk_viewer_hours_observed_7d,
    activity.peak_viewers AS chzzk_peak_viewers_observed_7d,
    CASE WHEN steam.ccu_period_anchor_date IS NOT NULL
        THEN COALESCE(activity.observed_bucket_count, 0)
    END AS chzzk_observed_bucket_count_7d,
    CASE WHEN steam.ccu_period_anchor_date IS NOT NULL
        THEN COALESCE(collection.collection_bucket_count, 0)
    END AS chzzk_collection_bucket_count_7d,
    CASE WHEN collection.collection_bucket_count > 0
        THEN COALESCE(activity.observed_bucket_count, 0)::DOUBLE PRECISION
            / collection.collection_bucket_count
    END AS chzzk_observation_ratio_7d,
    activity.latest_observed_bucket AS chzzk_latest_observed_bucket_7d,
    'bounded_sample'::TEXT AS bounded_sample_caveat
FROM srv_game_explore_period_metrics AS steam
INNER JOIN mapped_games AS mapping
    ON mapping.mapped_canonical_game_id = steam.canonical_game_id
LEFT JOIN game_activity AS activity
    ON activity.canonical_game_id = steam.canonical_game_id
   AND activity.anchor_date = steam.ccu_period_anchor_date
LEFT JOIN collection_buckets AS collection
    ON collection.anchor_date = steam.ccu_period_anchor_date;
