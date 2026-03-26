-- fact_steam_price_1h stores hourly Steam price snapshots.
CREATE TABLE IF NOT EXISTS fact_steam_price_1h (
    canonical_game_id BIGINT NOT NULL,
    bucket_time TIMESTAMPTZ NOT NULL,
    region TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    initial_price_minor INTEGER NOT NULL,
    final_price_minor INTEGER NOT NULL,
    discount_percent INTEGER NOT NULL,
    is_free BOOLEAN NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces one price row per game, KST hour bucket, and region.
    CONSTRAINT fact_steam_price_1h_pk PRIMARY KEY (canonical_game_id, bucket_time, region),
    CONSTRAINT fact_steam_price_1h_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE CASCADE,
    CONSTRAINT fact_steam_price_1h_region_non_empty
        CHECK (BTRIM(region) <> ''),
    CONSTRAINT fact_steam_price_1h_currency_code_non_empty
        CHECK (BTRIM(currency_code) <> ''),
    CONSTRAINT fact_steam_price_1h_initial_price_minor_non_negative
        CHECK (initial_price_minor >= 0),
    CONSTRAINT fact_steam_price_1h_final_price_minor_non_negative
        CHECK (final_price_minor >= 0),
    CONSTRAINT fact_steam_price_1h_discount_percent_range
        CHECK (discount_percent >= 0 AND discount_percent <= 100)
);
