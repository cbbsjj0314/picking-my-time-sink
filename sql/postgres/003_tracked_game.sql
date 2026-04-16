-- tracked_game stores current serving and fetch eligibility for monitored titles.
CREATE TABLE IF NOT EXISTS tracked_game (
    canonical_game_id BIGINT NOT NULL,
    -- is_active is not a lifecycle phase or warm grace state.
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    priority SMALLINT NOT NULL DEFAULT 3,
    sources TEXT[] NOT NULL DEFAULT ARRAY['steam']::TEXT[],
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK enforces a single tracking state row per canonical game.
    CONSTRAINT tracked_game_pk PRIMARY KEY (canonical_game_id),
    CONSTRAINT tracked_game_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE CASCADE,
    CONSTRAINT tracked_game_priority_range CHECK (priority BETWEEN 1 AND 5),
    CONSTRAINT tracked_game_sources_non_empty CHECK (CARDINALITY(sources) > 0)
);

-- Index supports active-serving scans ordered by priority.
CREATE INDEX IF NOT EXISTS idx_tracked_game_active_priority
    ON tracked_game (is_active, priority, canonical_game_id);
