-- fact_chzzk_category_30m is a candidate provider-specific Chzzk category fact.
-- It is not wired into the current Steam-only runtime scheduler/API/UI path.
CREATE TABLE IF NOT EXISTS fact_chzzk_category_30m (
    chzzk_category_id TEXT NOT NULL,
    bucket_time TIMESTAMPTZ NOT NULL,
    category_type TEXT NOT NULL,
    category_name TEXT NOT NULL,
    concurrent_sum INTEGER NOT NULL,
    live_count INTEGER NOT NULL,
    top_channel_id TEXT NOT NULL,
    top_channel_name TEXT NOT NULL,
    top_channel_concurrent INTEGER NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces one category aggregate per 30-minute bucket.
    CONSTRAINT fact_chzzk_category_30m_pk PRIMARY KEY (chzzk_category_id, bucket_time),
    CONSTRAINT fact_chzzk_category_30m_category_type_known CHECK (
        category_type IN ('GAME', 'SPORTS', 'ETC')
    ),
    CONSTRAINT fact_chzzk_category_30m_category_id_non_empty CHECK (
        LENGTH(BTRIM(chzzk_category_id)) > 0
    ),
    CONSTRAINT fact_chzzk_category_30m_category_name_non_empty CHECK (
        LENGTH(BTRIM(category_name)) > 0
    ),
    CONSTRAINT fact_chzzk_category_30m_live_count_positive CHECK (live_count > 0),
    CONSTRAINT fact_chzzk_category_30m_concurrent_non_negative CHECK (
        concurrent_sum >= 0
        AND top_channel_concurrent >= 0
        AND top_channel_concurrent <= concurrent_sum
    ),
    -- KST alignment: bucket must be exactly HH:00 or HH:30 in Asia/Seoul.
    CONSTRAINT fact_chzzk_category_30m_kst_bucket_boundary CHECK (
        EXTRACT(MINUTE FROM (bucket_time AT TIME ZONE 'Asia/Seoul')) IN (0, 30)
        AND EXTRACT(SECOND FROM (bucket_time AT TIME ZONE 'Asia/Seoul')) = 0
    )
);

-- Index supports newest category-bucket scans when this provider path is promoted.
CREATE INDEX IF NOT EXISTS idx_fact_chzzk_category_30m_bucket_desc
    ON fact_chzzk_category_30m (bucket_time DESC);

