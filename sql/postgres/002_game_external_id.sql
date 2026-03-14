-- game_external_id maps external identifiers (e.g. steam appid) to canonical games.
CREATE TABLE IF NOT EXISTS game_external_id (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    canonical_game_id BIGINT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK guarantees one row per external identity pair.
    CONSTRAINT game_external_id_pk PRIMARY KEY (source, external_id),
    CONSTRAINT game_external_id_source_non_empty CHECK (BTRIM(source) <> ''),
    CONSTRAINT game_external_id_external_id_non_empty CHECK (BTRIM(external_id) <> ''),
    CONSTRAINT game_external_id_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
        ON DELETE SET NULL
);

-- Partial unique index prevents multiple canonical mappings per source when linked.
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_external_id_canonical_source_not_null
    ON game_external_id (canonical_game_id, source)
    WHERE canonical_game_id IS NOT NULL;

-- Index speeds joins/filtering by internal key.
CREATE INDEX IF NOT EXISTS idx_game_external_id_canonical_game_id
    ON game_external_id (canonical_game_id);
