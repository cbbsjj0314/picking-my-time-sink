-- srv_combined_game_overview serves the minimal backend-only Combined overview.
CREATE OR REPLACE VIEW srv_combined_game_overview AS
WITH trusted_mapping_guard AS (
    SELECT
        mapping.chzzk_category_id,
        mapping.category_name,
        mapping.category_type,
        mapping.latest_bucket_time,
        mapping.mapped_canonical_game_id,
        ROW_NUMBER() OVER (
            PARTITION BY mapping.mapped_canonical_game_id
            ORDER BY mapping.chzzk_category_id ASC
        ) AS mapping_guard_rank
    FROM srv_chzzk_category_game_mapping AS mapping
)
SELECT
    steam.canonical_game_id,
    steam.canonical_name,
    steam.steam_appid,
    TRUE AS steam_source_available,
    mapping.chzzk_category_id IS NOT NULL AS chzzk_mapping_available,
    mapping.chzzk_category_id,
    mapping.category_name,
    mapping.category_type,
    mapping.latest_bucket_time
FROM srv_game_explore_period_metrics AS steam
LEFT JOIN trusted_mapping_guard AS mapping
    ON mapping.mapped_canonical_game_id = steam.canonical_game_id
   AND mapping.mapping_guard_rank = 1;
