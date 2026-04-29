from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
CHZZK_API_PATH = Path("web/src/api/chzzk.ts")
CHZZK_HOOK_PATH = Path("web/src/hooks/useChzzkCategoryOverview.ts")
CHZZK_VIEW_MODEL_PATH = Path("web/src/lib/chzzkCategoryViewModel.ts")
CHZZK_TABLE_PATH = Path("web/src/components/ChzzkCategoryTable.tsx")


def test_chzzk_api_client_reads_category_overview() -> None:
    source = CHZZK_API_PATH.read_text(encoding="utf-8")

    assert "export type ChzzkCategoryOverview" in source
    assert "latest_bucket_time: string" in source
    assert "latest_viewers_observed: number" in source
    assert "viewer_per_channel_observed: number | null" in source
    assert "function listCategoryOverview" in source
    assert "withQuery('/chzzk/categories/overview', { limit: options.limit ?? 50 })" in source


def test_chzzk_view_model_maps_new_api_fields_directly() -> None:
    source = CHZZK_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "latestViewersLabel: formatOptionalInteger(row.latest_viewers_observed)" in source
    assert "latestViewersTitle: formatKstDateTime(row.latest_bucket_time)" in source
    assert "viewersPerChannelLabel: formatDecimal(row.viewer_per_channel_observed)" in source
    assert "viewersPerChannel: finiteNumberOrNull(row.viewer_per_channel_observed)" in source
    assert "viewer_hours_observed / 0.5" not in source
    assert "viewer_hours_observed /" not in source
    assert "/ 0.5" not in source


def test_chzzk_source_view_is_connected_without_steam_or_combined_semantics() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    hook_source = CHZZK_HOOK_PATH.read_text(encoding="utf-8")
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "useChzzkCategoryOverview" in app_source
    assert "sourceTab === 'Chzzk'" in app_source
    assert "<ChzzkCategoryTable" in app_source
    assert "chzzkApi.listCategoryOverview({ limit, signal: controller.signal })" in hook_source
    assert "Combined" not in table_source
    assert "Steam game mapping" not in table_source
    assert "Unique Channels" not in table_source


def test_chzzk_table_uses_observed_sample_context_without_period_label() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "Observed Sample · KR / KST" in table_source
    assert "API context label only. Observed buckets; no full-window claim." in table_source
    assert "Latest Viewers" in table_source
    assert "Current Viewers" not in table_source
    assert "Last 7 Days" not in table_source
    assert "Category-only" in table_source
    assert "Bounded sample" in table_source
    assert "coverage_status" not in table_source


def test_chzzk_category_cell_stays_name_only() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")
    category_cell = (
        '<div className="font-semibold leading-snug text-[var(--text-primary)]">'
        "{row.categoryName}</div>"
    )

    assert category_cell in table_source
    assert "category_type" not in table_source
