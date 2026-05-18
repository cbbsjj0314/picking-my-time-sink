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
    assert "unique_channels_observed: number | null" in source
    assert "function listCategoryOverview" in source
    assert "withQuery('/chzzk/categories/overview', { limit: options.limit ?? 50 })" in source


def test_chzzk_view_model_maps_new_api_fields_directly() -> None:
    source = CHZZK_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "latestViewersLabel: formatOptionalInteger(row.latest_viewers_observed)" in source
    assert "latestViewersTitle: composeLatestViewersTitle(row)" in source
    assert "const latestBucketTitle = formatKstDateTime(row.latest_bucket_time)" in source
    assert "viewersPerChannelLabel: formatDecimal(row.viewer_per_channel_observed)" in source
    assert (
        "viewersPerChannelSupport: getNullableChannelMetricSupport(row.viewer_per_channel_observed)"
        in source
    )
    assert "viewersPerChannel: finiteNumberOrNull(row.viewer_per_channel_observed)" in source
    assert "uniqueChannelsLabel: formatOptionalInteger(row.unique_channels_observed)" in source
    assert (
        "uniqueChannelsSupport: getNullableChannelMetricSupport(row.unique_channels_observed)"
        in source
    )
    assert "uniqueChannels: finiteNumberOrNull(row.unique_channels_observed)" in source
    assert "Channel evidence unavailable" in source
    assert "matching category-channel evidence is unavailable" in source
    assert "observed nullable metric, not a full-population claim" in source
    assert "No channel evidence" not in source
    assert "viewer_hours_observed / 0.5" not in source
    assert "viewer_hours_observed /" not in source
    assert "/ 0.5" not in source


def test_chzzk_view_model_humanizes_bucket_coverage_copy() -> None:
    source = CHZZK_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "observedBucketLabel: formatCoverageStatusLabel(row.coverage_status)" in source
    assert "observedBucketTitle: formatCoverageStatusTitle(row)" in source
    assert "Coverage state: ${row.coverage_status}" not in source
    assert "Observed bucket only" in source
    assert "Partial bucket window" in source
    assert "1d bucket coverage candidate" in source
    assert "7d bucket coverage candidate" in source
    assert "Bucket coverage status unavailable" in source
    assert (
        "Bucket coverage status from observed category buckets; "
        "not a full live-list population claim."
        in source
    )
    assert "Missing 1d buckets:" in source
    assert "missing 7d buckets:" in source
    assert "Coverage candidate only." in source
    assert "full product metric" not in source
    assert "full 1d" not in source
    assert "full 7d" not in source


def test_chzzk_view_model_preserves_latest_bucket_timestamp_title() -> None:
    source = CHZZK_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "const composeLatestViewersTitle = (row: ChzzkCategoryOverview)" in source
    assert "const latestBucketTitle = formatKstDateTime(row.latest_bucket_time)" in source
    assert "const coverageTitle = formatCoverageStatusTitle(row)" in source
    assert (
        "latestBucketTitle === null ? coverageTitle : "
        "`${latestBucketTitle}. ${coverageTitle}`"
        in source
    )


def test_chzzk_source_view_is_connected_without_steam_or_combined_semantics() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    hook_source = CHZZK_HOOK_PATH.read_text(encoding="utf-8")
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "useChzzkCategoryOverview" in app_source
    assert "sourceTab === 'Chzzk'" in app_source
    assert "<ChzzkCategoryTable" in app_source
    assert "chzzkApi.listCategoryOverview({ limit, signal: controller.signal })" in hook_source
    assert "Combined" not in table_source
    assert "<Steam" not in table_source
    assert "canonicalGame" not in table_source
    assert "canonical_game_id" not in table_source
    assert "mappingStatus" not in table_source
    assert "mappedSteam" not in table_source
    assert "Unique Channels" in table_source
    assert "channel_id" not in table_source
    assert "channel_name" not in table_source


def test_chzzk_table_uses_observed_sample_context_without_period_label() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "const accessibleLabel = title ? `${label}: ${title}` : label" in table_source
    assert "aria-label={accessibleLabel}" in table_source
    assert "title={title ?? undefined}" in table_source
    assert "Observed Sample · KR / KST" in table_source
    assert "API context label only. Observed buckets; no full-window claim." in table_source
    assert "Channel-derived metrics are nullable observed values" in table_source
    assert "matching category-channel" in table_source
    assert "Latest Viewers" in table_source
    assert "Current Viewers" not in table_source
    assert "Last 7 Days" not in table_source
    assert "Category-only" in table_source
    assert "Bounded sample" in table_source
    assert 'CaveatBadge label="Category-only"' in table_source
    assert 'CaveatBadge label="Bounded sample"' in table_source
    assert "coverage_status" not in table_source
    assert "Coverage state:" not in table_source


def test_chzzk_table_includes_bounded_result_count_context() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "formatObservedCategoryRowCount(totalRowCount)" in table_source
    assert "observed category row" in table_source
    assert "rows.length.toLocaleString('en-US')" in table_source
    assert (
        "of ${formatObservedCategoryRowCount(totalRowCount)} match current search"
        in table_source
    )


def test_chzzk_table_non_table_states_preserve_observed_source_boundary() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "Read-only observed Chzzk category source-view unavailable: {error}" in table_source
    assert "Loading Chzzk category observed evidence for this source-view." in table_source
    assert "No observed Chzzk category rows match the current search." in table_source
    assert (
        "No bounded observed Chzzk category rows are available in this source-view."
        in table_source
    )
    assert "Loading Chzzk category evidence." not in table_source
    assert "No Chzzk category rows match the current search." not in table_source
    assert "No Chzzk category rows are available." not in table_source


def test_chzzk_table_uses_nullable_channel_metric_support_from_view_model() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "support={row.viewersPerChannelSupport}" in table_source
    assert "support={row.uniqueChannelsSupport}" in table_source
    assert "No channel evidence" not in table_source


def test_chzzk_table_uses_readable_coverage_support_from_view_model() -> None:
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")

    assert "support={row.observedBucketLabel}" in table_source
    assert "supportTitle={row.observedBucketTitle}" in table_source
    assert "title={row.latestViewersTitle}" in table_source
    assert "Coverage state:" not in table_source


def test_chzzk_category_cell_shows_provider_category_type_evidence() -> None:
    view_model_source = CHZZK_VIEW_MODEL_PATH.read_text(encoding="utf-8")
    table_source = CHZZK_TABLE_PATH.read_text(encoding="utf-8")
    category_cell = (
        '<div className="font-semibold leading-snug text-[var(--text-primary)]">'
        "{row.categoryName}</div>"
    )

    assert category_cell in table_source
    assert "categoryTypeLabel: formatCategoryTypeLabel(row.category_type)" in view_model_source
    assert "categoryTypeTitle:" in view_model_source
    assert "Chzzk provider category type evidence" in view_model_source
    assert "not canonical game identity or trusted Steam mapping" in view_model_source
    assert "categoryTypeLabel" in view_model_source
    assert "categoryTypeTitle" in view_model_source
    assert "row.categoryTypeLabel" in table_source
    assert "aria-label={`${row.categoryTypeLabel}: ${row.categoryTypeTitle}`}" in table_source
    assert "title={row.categoryTypeTitle}" in table_source
    assert "canonical_game_id" not in table_source
    assert "canonicalGame" not in table_source
    assert "Combined" not in table_source
