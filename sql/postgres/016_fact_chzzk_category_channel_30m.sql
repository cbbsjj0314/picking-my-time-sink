-- fact_chzzk_category_channel_30m stores provider-specific observed channel facts.
-- It supports later unique-channel observed metrics without API/UI exposure here.
CREATE TABLE IF NOT EXISTS fact_chzzk_category_channel_30m (
    chzzk_category_id TEXT NOT NULL,
    bucket_time TIMESTAMPTZ NOT NULL,
    channel_id TEXT NOT NULL,
    category_type TEXT NOT NULL,
    category_name TEXT NOT NULL,
    concurrent_user_count INTEGER NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces one observed category-channel row per 30-minute bucket.
    CONSTRAINT fact_chzzk_category_channel_30m_pk PRIMARY KEY (
        chzzk_category_id,
        bucket_time,
        channel_id
    ),
    CONSTRAINT fact_chzzk_category_channel_30m_category_type_known CHECK (
        category_type IN ('GAME', 'SPORTS', 'ENTERTAINMENT', 'ETC')
    ),
    CONSTRAINT fact_chzzk_category_channel_30m_category_id_non_empty CHECK (
        LENGTH(BTRIM(chzzk_category_id)) > 0
    ),
    CONSTRAINT fact_chzzk_category_channel_30m_category_name_non_empty CHECK (
        LENGTH(BTRIM(category_name)) > 0
    ),
    CONSTRAINT fact_chzzk_category_channel_30m_channel_id_non_empty CHECK (
        LENGTH(BTRIM(channel_id)) > 0
    ),
    CONSTRAINT fact_chzzk_category_channel_30m_concurrent_non_negative CHECK (
        concurrent_user_count >= 0
    ),
    -- KST alignment: bucket must be exactly HH:00 or HH:30 in Asia/Seoul.
    CONSTRAINT fact_chzzk_category_channel_30m_kst_bucket_boundary CHECK (
        EXTRACT(MINUTE FROM (bucket_time AT TIME ZONE 'Asia/Seoul')) IN (0, 30)
        AND EXTRACT(SECOND FROM (bucket_time AT TIME ZONE 'Asia/Seoul')) = 0
    )
);

-- Index supports newest observed channel fact scans when promoted to serving.
CREATE INDEX IF NOT EXISTS idx_fact_chzzk_category_channel_30m_bucket_desc
    ON fact_chzzk_category_channel_30m (bucket_time DESC);
