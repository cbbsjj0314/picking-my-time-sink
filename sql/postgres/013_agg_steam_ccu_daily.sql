-- agg_steam_ccu_daily stores daily Steam CCU rollups by KST bucket date.
CREATE TABLE IF NOT EXISTS agg_steam_ccu_daily (
    canonical_game_id BIGINT NOT NULL,
    bucket_date DATE NOT NULL,
    avg_ccu DOUBLE PRECISION NOT NULL,
    peak_ccu INTEGER NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agg_steam_ccu_daily_pk PRIMARY KEY (canonical_game_id, bucket_date),
    CONSTRAINT agg_steam_ccu_daily_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE CASCADE,
    CONSTRAINT agg_steam_ccu_daily_avg_ccu_non_negative CHECK (avg_ccu >= 0.0),
    CONSTRAINT agg_steam_ccu_daily_peak_ccu_non_negative CHECK (peak_ccu >= 0)
);
