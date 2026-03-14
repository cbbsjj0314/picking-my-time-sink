-- fact_steam_ccu_30m stores 30-minute Steam CCU snapshots.
CREATE TABLE IF NOT EXISTS fact_steam_ccu_30m (
    canonical_game_id BIGINT NOT NULL,
    bucket_time TIMESTAMPTZ NOT NULL,
    ccu INTEGER NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces required grain: one snapshot per game and bucket.
    CONSTRAINT fact_steam_ccu_30m_pk PRIMARY KEY (canonical_game_id, bucket_time),
    CONSTRAINT fact_steam_ccu_30m_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE CASCADE,
    CONSTRAINT fact_steam_ccu_30m_ccu_non_negative CHECK (ccu >= 0),
    -- KST alignment: bucket must be exactly HH:00 or HH:30 in Asia/Seoul.
    CONSTRAINT fact_steam_ccu_30m_kst_bucket_boundary CHECK (
        EXTRACT(MINUTE FROM (bucket_time AT TIME ZONE 'Asia/Seoul')) IN (0, 30)
        AND EXTRACT(SECOND FROM (bucket_time AT TIME ZONE 'Asia/Seoul')) = 0
    )
);

-- Index supports latest-per-game lookup for serving queries.
CREATE INDEX IF NOT EXISTS idx_fact_steam_ccu_30m_game_bucket_desc
    ON fact_steam_ccu_30m (canonical_game_id, bucket_time DESC);

-- Index supports newest-bucket scans across all games.
CREATE INDEX IF NOT EXISTS idx_fact_steam_ccu_30m_bucket_desc
    ON fact_steam_ccu_30m (bucket_time DESC);
