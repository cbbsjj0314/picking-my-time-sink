-- chzzk_category_game_mapping stores trusted Chzzk category-to-game mappings.
CREATE TABLE IF NOT EXISTS chzzk_category_game_mapping (
    chzzk_category_id TEXT NOT NULL,
    canonical_game_id BIGINT NOT NULL,
    mapping_status TEXT NOT NULL DEFAULT 'trusted',
    source_kind TEXT NOT NULL,
    reviewed_by TEXT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chzzk_category_game_mapping_pk PRIMARY KEY (chzzk_category_id),
    CONSTRAINT chzzk_category_game_mapping_category_id_non_empty CHECK (
        LENGTH(BTRIM(chzzk_category_id)) > 0
    ),
    CONSTRAINT chzzk_category_game_mapping_status_trusted_only CHECK (
        mapping_status IN ('trusted')
    ),
    CONSTRAINT chzzk_category_game_mapping_source_kind_non_empty CHECK (
        LENGTH(BTRIM(source_kind)) > 0
    ),
    CONSTRAINT chzzk_category_game_mapping_canonical_game_fk
        FOREIGN KEY (canonical_game_id)
        REFERENCES dim_game (canonical_game_id)
);
