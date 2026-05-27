-- srv_chzzk_category_game_mapping serves trusted Chzzk category-to-game mappings for internal DB consumers.
CREATE OR REPLACE VIEW srv_chzzk_category_game_mapping AS
WITH latest_category_rows AS (
    SELECT DISTINCT ON (chzzk_category_id)
        chzzk_category_id,
        category_name,
        category_type,
        bucket_time AS latest_bucket_time
    FROM fact_chzzk_category_30m
    ORDER BY chzzk_category_id, bucket_time DESC, collected_at DESC, ingested_at DESC
)
SELECT
    mapping.chzzk_category_id,
    latest.category_name,
    latest.category_type,
    latest.latest_bucket_time,
    mapping.canonical_game_id AS mapped_canonical_game_id,
    game.canonical_name AS mapped_canonical_game_name
FROM chzzk_category_game_mapping AS mapping
INNER JOIN dim_game AS game
    ON game.canonical_game_id = mapping.canonical_game_id
LEFT JOIN latest_category_rows AS latest
    ON latest.chzzk_category_id = mapping.chzzk_category_id
WHERE mapping.mapping_status = 'trusted'
ORDER BY mapping.chzzk_category_id ASC;
