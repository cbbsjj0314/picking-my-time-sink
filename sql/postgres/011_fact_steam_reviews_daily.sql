-- fact_steam_reviews_daily stores daily Steam reviews snapshots.
CREATE TABLE IF NOT EXISTS fact_steam_reviews_daily (
    canonical_game_id BIGINT NOT NULL,
    snapshot_date DATE NOT NULL,
    total_reviews INTEGER NOT NULL,
    total_positive INTEGER NOT NULL,
    total_negative INTEGER NOT NULL,
    positive_ratio DOUBLE PRECISION NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces one snapshot row per game and KST date.
    CONSTRAINT fact_steam_reviews_daily_pk PRIMARY KEY (canonical_game_id, snapshot_date),
    CONSTRAINT fact_steam_reviews_daily_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE CASCADE,
    CONSTRAINT fact_steam_reviews_daily_total_reviews_non_negative
        CHECK (total_reviews >= 0),
    CONSTRAINT fact_steam_reviews_daily_total_positive_non_negative
        CHECK (total_positive >= 0),
    CONSTRAINT fact_steam_reviews_daily_total_negative_non_negative
        CHECK (total_negative >= 0),
    CONSTRAINT fact_steam_reviews_daily_positive_ratio_range
        CHECK (positive_ratio >= 0.0 AND positive_ratio <= 1.0)
);

-- Index supports latest-per-game snapshot lookups.
CREATE INDEX IF NOT EXISTS idx_fact_steam_reviews_daily_game_snapshot_date_desc
    ON fact_steam_reviews_daily (canonical_game_id, snapshot_date DESC);

-- Index supports newest snapshot-date scans across all games.
CREATE INDEX IF NOT EXISTS idx_fact_steam_reviews_daily_snapshot_date_desc
    ON fact_steam_reviews_daily (snapshot_date DESC);
