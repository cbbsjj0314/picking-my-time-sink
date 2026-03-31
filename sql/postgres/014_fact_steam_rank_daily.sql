-- fact_steam_rank_daily stores daily Steam ranking snapshots from runtime payload artifacts.
CREATE TABLE IF NOT EXISTS fact_steam_rank_daily (
    snapshot_date DATE NOT NULL,
    market TEXT NOT NULL,
    rank_type TEXT NOT NULL,
    rank_position INTEGER NOT NULL,
    steam_appid BIGINT NOT NULL,
    canonical_game_id BIGINT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces one ranking row per KST snapshot date, market, chart, and position.
    CONSTRAINT fact_steam_rank_daily_pk PRIMARY KEY (
        snapshot_date,
        market,
        rank_type,
        rank_position
    ),
    CONSTRAINT fact_steam_rank_daily_market_non_empty
        CHECK (BTRIM(market) <> ''),
    CONSTRAINT fact_steam_rank_daily_rank_type_non_empty
        CHECK (BTRIM(rank_type) <> ''),
    CONSTRAINT fact_steam_rank_daily_rank_position_positive
        CHECK (rank_position > 0),
    CONSTRAINT fact_steam_rank_daily_steam_appid_positive
        CHECK (steam_appid > 0),
    CONSTRAINT fact_steam_rank_daily_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE SET NULL
);

-- Index supports latest ranking list scans by fixed market/chart slice.
CREATE INDEX IF NOT EXISTS idx_fact_steam_rank_daily_market_rank_type_snapshot_date_desc
    ON fact_steam_rank_daily (market, rank_type, snapshot_date DESC, rank_position ASC);

-- Index supports current Steam id mapping lookups for ranking facts.
CREATE INDEX IF NOT EXISTS idx_fact_steam_rank_daily_steam_appid_snapshot_date_desc
    ON fact_steam_rank_daily (steam_appid, snapshot_date DESC);
