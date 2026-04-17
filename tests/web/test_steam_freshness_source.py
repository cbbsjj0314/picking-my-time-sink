from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
STEAM_TYPES_PATH = Path("web/src/types.ts")
STEAM_VIEW_MODEL_PATH = Path("web/src/lib/steamViewModel.ts")
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


def test_explore_table_summarizes_freshness_without_fake_fallback() -> None:
    source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "getUniformEvidenceLabel" in source
    assert "return `${label} mixed snapshots`" in source
    assert "Current CCU" in source
    assert "CCU period anchor" in source
    assert "Reviews anchor" in source
    assert "Price snapshot" in source
    assert "freshnessLabels.join(' · ')" in source
