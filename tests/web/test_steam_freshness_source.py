from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
STEAM_TYPES_PATH = Path("web/src/types.ts")
STEAM_VIEW_MODEL_PATH = Path("web/src/lib/steamViewModel.ts")
GAMES_API_PATH = Path("web/src/api/games.ts")
STEAM_OVERVIEW_HOOK_PATH = Path("web/src/hooks/useSteamOverview.ts")
STEAM_DISCOVER_MODE_ROW_PATH = Path("web/src/components/SteamDiscoverModeRow.tsx")
STEAM_EXPLORE_VIEW_MODEL_PATH = Path("web/src/lib/steamExploreViewModel.ts")
STEAM_EXPLORE_TABLE_PATH = Path("web/src/components/SteamExploreTable.tsx")


def test_steam_detail_view_surfaces_latest_evidence_timestamps() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "rankingSnapshotDate: string | null" in source
    assert "rankingSnapshotDate: row.snapshot_date" in source
    assert "Snapshot ${formatSnapshotDate(row.rankingSnapshotDate)}" in source
    assert "label: 'CCU snapshot'" in source
    assert "formatSnapshotDateTime(row.ccu.bucket_time)" in source
    assert "label: 'Review snapshot'" in source
    assert "formatSnapshotDate(row.reviews.snapshot_date)" in source
    assert "label: 'Price snapshot'" in source
    assert "formatSnapshotDateTime(row.price.bucket_time)" in source


def test_steam_source_view_is_fixed_to_explore_and_top_selling_modes() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    types_source = STEAM_TYPES_PATH.read_text(encoding="utf-8")
    mode_row_source = STEAM_DISCOVER_MODE_ROW_PATH.read_text(encoding="utf-8")
    overview_hook_source = STEAM_OVERVIEW_HOOK_PATH.read_text(encoding="utf-8")
    view_model_source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "export const steamDiscoverModes = ['Explore', 'Top Selling'] as const" in types_source
    assert "Most Played" not in types_source
    assert "Player Heat" not in types_source
    assert "Most Played" not in mode_row_source
    assert "Player Heat" not in mode_row_source
    assert "Most Played" not in app_source
    assert "Player Heat" not in app_source
    assert "getPlayerHeatContextSuffix" not in view_model_source
    assert "buildMostPlayedRows" not in view_model_source
    assert "API_WINDOW_BY_RANGE" not in overview_hook_source
    assert "window: API_WINDOW_BY_RANGE" not in overview_hook_source
    assert "window: '7d'" in overview_hook_source


def test_explore_view_model_keeps_nulls_and_timestamp_fields_grounded() -> None:
    source = STEAM_EXPLORE_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "const EMPTY_CELL = '-'" in source
    assert "currentCcuLabel: formatOptionalInteger(row.current_ccu)" in source
    assert "currentCcuTitle: formatKstDateTime(row.ccu_bucket_time)" in source
    assert "ccuAnchorLabel: formatKstDate(row.ccu_period_anchor_date)" in source
    assert "reviewAnchorLabel: formatKstDate(row.reviews_snapshot_date)" in source
    assert "priceTitle: formatKstDateTime(row.price_bucket_time)" in source


def test_web_price_types_allow_free_rows_without_numeric_fields() -> None:
    source = GAMES_API_PATH.read_text(encoding="utf-8")

    assert "currency_code: string | null" in source
    assert "initial_price_minor: number | null" in source
    assert "final_price_minor: number | null" in source
    assert "discount_percent: number | null" in source


def test_explore_price_display_distinguishes_free_and_missing_evidence() -> None:
    source = STEAM_EXPLORE_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "if (row.is_free === true)" in source
    assert "return 'Free'" in source
    assert "row.final_price_minor === null || row.currency_code === null" in source
    assert "return EMPTY_CELL" in source
    assert "row.is_free !== true && row.discount_percent !== null" in source


def test_detail_price_display_uses_free_without_discount_support() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "if (isFree === true)" in source
    assert "return 'Free'" in source
    assert "valueMinor === null || currencyCode === null" in source
    assert "return 'Pending'" in source
    assert "if (price.is_free === true || currentPrice === 'Pending')" in source
    assert "if (price.is_free === true)" in source
    assert "return '-'" in source
    assert "return `${currentPrice} · Free`" not in source


def test_explore_table_summarizes_freshness_without_fake_fallback() -> None:
    source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "getUniformEvidenceLabel" in source
    assert "return `${label} mixed snapshots`" in source
    assert "Current CCU" in source
    assert "CCU period anchor" in source
    assert "Reviews anchor" in source
    assert "Price snapshot" in source
    assert "freshnessLabels.join(' · ')" in source
