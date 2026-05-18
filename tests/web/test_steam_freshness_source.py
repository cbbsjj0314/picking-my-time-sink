from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
STEAM_TYPES_PATH = Path("web/src/types.ts")
STEAM_VIEW_MODEL_PATH = Path("web/src/lib/steamViewModel.ts")
GAMES_API_PATH = Path("web/src/api/games.ts")
STEAM_OVERVIEW_HOOK_PATH = Path("web/src/hooks/useSteamOverview.ts")
MODE_SHELL_ROW_PATH = Path("web/src/components/ModeShellRow.tsx")
STEAM_DISCOVER_MODE_ROW_PATH = Path("web/src/components/SteamDiscoverModeRow.tsx")
STEAM_EXPLORE_VIEW_MODEL_PATH = Path("web/src/lib/steamExploreViewModel.ts")
STEAM_EXPLORE_TABLE_PATH = Path("web/src/components/SteamExploreTable.tsx")
STEAM_RANKING_LIST_PATH = Path("web/src/components/SteamRankingList.tsx")


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


def test_mode_shell_row_exposes_selected_state_semantics() -> None:
    mode_shell_source = MODE_SHELL_ROW_PATH.read_text(encoding="utf-8")
    steam_mode_row_source = STEAM_DISCOVER_MODE_ROW_PATH.read_text(encoding="utf-8")

    assert "export function ModeShellRow<T extends string>" in mode_shell_source
    assert "const isSelected = item.value === selected" in mode_shell_source
    assert "aria-pressed={isSelected}" in mode_shell_source
    assert "onClick={() => onChange(item.value)}" in mode_shell_source
    assert "isSelected\n                  ? 'bg-[#E8639B]" in mode_shell_source
    assert "item.description" in mode_shell_source
    assert 'role="tablist"' not in mode_shell_source
    assert 'role="tab"' not in mode_shell_source

    assert (
        "active tracked Steam universe를 7D 플레이, 리뷰, KR 가격 근거 테이블로 보기"
        in steam_mode_row_source
    )
    assert (
        "Steam weekly top sellers snapshot 기준으로 Top Selling 게임 보기"
        in steam_mode_row_source
    )


def test_explore_view_model_keeps_nulls_and_timestamp_fields_grounded() -> None:
    source = STEAM_EXPLORE_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "const EMPTY_CELL = '-'" in source
    assert "export const DEFAULT_STEAM_EXPLORE_SORT_STATE" in source
    assert "key: 'estimatedPlayerHours'" in source
    assert "direction: 'desc'" in source
    assert "currentCcuLabel: formatOptionalInteger(row.current_ccu)" in source
    assert "currentCcuTitle: formatKstDateTime(row.ccu_bucket_time)" in source
    assert "ccuAnchorLabel: formatKstDate(row.ccu_period_anchor_date)" in source
    assert "reviewAnchorLabel: formatKstDate(row.reviews_snapshot_date)" in source
    assert "priceTitle: formatKstDateTime(row.price_bucket_time)" in source
    assert "sortValues: buildSortValues(row)" in source
    assert "currentCcu: finiteNumberOrNull(row.current_ccu)" in source
    assert "estimatedPlayerHours: finiteNumberOrNull(row.estimated_player_hours_7d)" in source
    assert "observed_player_hours_7d" in source
    assert "estimatedPlayerHoursCaveatLabel" in source
    assert "price: finiteNumberOrNull(row.final_price_minor)" in source


def test_explore_period_null_state_uses_history_collection_copy() -> None:
    view_model_source = STEAM_EXPLORE_VIEW_MODEL_PATH.read_text(encoding="utf-8")
    table_source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "export const buildPeriodHistoryCollectingLabel" in view_model_source
    assert "periodLabel: '7 days'" in view_model_source
    assert "periodDays: 7" in view_model_source
    assert (
        "Collecting ${normalizedLabel.length > 0 ? normalizedLabel : fallbackLabel} of history"
        in view_model_source
    )
    assert "const formatPeriodMetricSupport" in view_model_source
    assert "const getEstimatedPlayerHoursDisplay" in view_model_source
    assert "Strict 7D estimate pending." in view_model_source
    assert "avgCcuSupportLabel: formatPeriodMetricSupport(" in view_model_source
    assert "peakCcuSupportLabel: formatPeriodMetricSupport(" in view_model_source
    assert (
        "estimatedPlayerHoursSupportLabel: estimatedPlayerHoursDisplay.supportLabel"
        in view_model_source
    )
    assert (
        "estimatedPlayerHoursCaveatLabel: estimatedPlayerHoursDisplay.caveatLabel"
        in view_model_source
    )
    assert "reviewsAddedSupportLabel: formatPeriodMetricSupport(" in view_model_source
    assert "positiveShareSupportLabel: formatPeriodMetricSupport(" in view_model_source
    assert "currentCcuSupportLabel: formatCurrentCcuSupport(row)" in view_model_source
    assert "priceSupportLabel: formatDiscountSupport(row)" in view_model_source
    assert (
        "periodHistoryCollectingLabel: periodMetricsCollecting "
        "? PERIOD_HISTORY_COLLECTING_LABEL : null"
        in view_model_source
    )

    assert "getPeriodHistoryCollectingNotice" in table_source
    assert "getCommonEstimatedPlayerHoursCaveatTitle" in table_source
    assert '<CaveatBadge label="Observed"' in table_source
    assert "rows.some((row) => !row.periodMetricsCollecting)" in table_source
    assert "Period metrics appear after the full window is available." in table_source


def test_web_price_types_allow_free_rows_without_numeric_fields() -> None:
    source = GAMES_API_PATH.read_text(encoding="utf-8")

    assert "observed_player_hours_7d: number | null" in source
    assert "estimated_player_hours_7d_observed_bucket_count: number | null" in source
    assert "estimated_player_hours_7d_expected_bucket_count: number | null" in source
    assert "estimated_player_hours_7d_coverage_ratio: number | null" in source
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


def test_top_selling_price_copy_omits_no_sale_label() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")
    price_line_source = source.split("const buildPriceLine", maxsplit=1)[1].split(
        "const formatDiscountValue",
        maxsplit=1,
    )[0]
    discount_value_source = source.split("const formatDiscountValue", maxsplit=1)[1].split(
        "const buildReviewSummary",
        maxsplit=1,
    )[0]

    assert "if (!price)" in price_line_source
    assert "return 'Pending'" in price_line_source
    assert "if (price.is_free === true || currentPrice === 'Pending')" in price_line_source
    assert "return currentPrice" in price_line_source
    assert "price.discount_percent !== null && price.discount_percent > 0" in price_line_source
    assert "return `${currentPrice} · -${price.discount_percent}%`" in price_line_source
    assert "No sale" not in price_line_source

    assert "if (!price)" in discount_value_source
    assert "return 'Pending'" in discount_value_source
    assert "if (price.is_free === true)" in discount_value_source
    assert "return '-'" in discount_value_source
    assert "if (price.discount_percent === null)" in discount_value_source
    assert (
        "return price.discount_percent > 0 ? `-${price.discount_percent}%` : '-'"
        in discount_value_source
    )
    assert "No sale" not in discount_value_source


def test_explore_table_summarizes_freshness_without_fake_fallback() -> None:
    source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "{ key: 'currentCcu', label: 'Current CCU' }" in source
    assert "{ key: 'estimatedPlayerHours', label: 'Estimated Player-Hours' }" in source
    assert "{ key: 'avgCcu', label: 'Avg CCU' }" in source
    assert "getUniformEvidenceLabel" in source
    assert "getAriaSort" in source
    assert "onClick={() => onSortChange(column.key)}" in source
    assert "Default sort follows Estimated Player-Hours" in source
    assert "return `${label} mixed snapshots`" in source
    assert "Current CCU" in source
    assert "CCU period anchor" in source
    assert "Reviews anchor" in source
    assert "Price snapshot" in source
    assert "const contextLabels = [resultCountLabel, ...freshnessLabels]" in source
    assert "contextLabels.join(' · ')" in source


def test_explore_table_includes_result_count_search_context() -> None:
    source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "const formatSteamExploreRowCount" in source
    assert "formatSteamExploreRowCount(totalRowCount)" in source
    assert "Steam Explore row" in source
    assert "rows.length.toLocaleString('en-US')" in source
    assert (
        "of ${formatSteamExploreRowCount(totalRowCount)} match current search"
        in source
    )
    assert "const contextLabels = [resultCountLabel, ...freshnessLabels]" in source
    assert "contextLabels.join(' · ')" in source
    assert "full Steam catalog" not in source
    assert "all Steam games" not in source
    assert "complete Steam catalog" not in source


def test_explore_table_non_table_states_use_tracked_source_copy() -> None:
    source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "Loading tracked Steam Explore evidence." in source
    assert "Steam Explore evidence could not be loaded." in source
    assert "<p>{error}</p>" in source
    assert "No tracked Steam Explore rows match the current search." in source
    assert "No tracked Steam Explore rows are available yet." in source
    assert "hasSearch && totalRowCount > 0" in source

    forbidden_claims = [
        "full Steam catalog",
        "all Steam games",
        "complete Steam catalog",
        "Combined",
        "category-to-game",
        "scheduler",
        "live fetch",
        "DB write",
    ]
    for forbidden_claim in forbidden_claims:
        assert forbidden_claim not in source


def test_explore_hook_routes_sort_state_through_view_model() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    hook_source = Path("web/src/hooks/useSteamExploreOverview.ts").read_text(encoding="utf-8")

    assert (
        "const [sortState, setSortState] = useState<SteamExploreSortState>"
        "(DEFAULT_STEAM_EXPLORE_SORT_STATE)"
        in hook_source
    )
    assert (
        "rows: enabled ? buildSteamExploreTableRows(apiRows, searchQuery, sortState) : []"
        in hook_source
    )
    assert "setSortState((currentSort) => toggleSteamExploreSort(currentSort, key))" in hook_source
    assert "sortState: steamExploreSortState" in app_source
    assert "requestSort: requestSteamExploreSort" in app_source
    assert "onSortChange={requestSteamExploreSort}" in app_source


def test_top_selling_detail_7d_average_waits_for_full_history_window() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")
    average_row = (
        "{ label: '7D avg', value: sevenDayAverage !== null ? "
        "formatCompact(sevenDayAverage) : 'Pending' }"
    )

    assert "historyRows.length < HISTORY_POINT_LIMITS['7D']" in source
    assert "const recentRows = historyRows.slice(-HISTORY_POINT_LIMITS['7D'])" in source
    assert average_row in source


def test_top_selling_detail_uses_target_aware_evidence_copy() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")
    types_source = STEAM_TYPES_PATH.read_text(encoding="utf-8")
    card_states_source = source.split("const getCardStates", maxsplit=1)[1].split(
        "const getStatusBadge",
        maxsplit=1,
    )[0]

    assert (
        "export const steamDataStateKinds = ['Pending', 'Partial', 'Stale'] as const"
        in types_source
    )
    assert (
        "export const steamDataStateTargets = ['CCU', 'Reviews', 'Price'] as const"
        in types_source
    )
    assert "export interface SteamDataState {" in types_source
    assert "kind: SteamDataStateKind" in types_source
    assert "target: SteamDataStateTarget" in types_source
    assert "tooltip: string" in types_source

    assert (
        "const CCU_PENDING_TOOLTIP = "
        "'CCU evidence is still loading or unavailable for this ranked game.'"
        in source
    )
    assert (
        "const CCU_PARTIAL_TOOLTIP = "
        "'CCU evidence is partial until the selected game has enough 7D history.'"
        in source
    )
    assert (
        "const REVIEWS_PENDING_TOOLTIP = "
        "'Review snapshot evidence is still loading or unavailable for this ranked game.'"
        in source
    )
    assert (
        "const REVIEWS_PARTIAL_TOOLTIP = "
        "'Review delta evidence is partial for the current snapshot.'"
        in source
    )
    assert (
        "const PRICE_PENDING_TOOLTIP = "
        "'Price snapshot evidence is still loading or unavailable for this ranked game.'"
        in source
    )

    assert "buildCardState('CCU', 'Pending', CCU_PENDING_TOOLTIP)" in card_states_source
    assert "buildCardState('CCU', 'Partial', CCU_PARTIAL_TOOLTIP)" in card_states_source
    assert "buildCardState('Reviews', 'Pending', REVIEWS_PENDING_TOOLTIP)" in card_states_source
    assert "buildCardState('Reviews', 'Partial', REVIEWS_PARTIAL_TOOLTIP)" in card_states_source
    assert "buildCardState('Price', 'Pending', PRICE_PENDING_TOOLTIP)" in card_states_source
    assert "buildCardState('CCU', 'Pending', PENDING_TOOLTIP)" not in card_states_source
    assert "buildCardState('CCU', 'Partial', PARTIAL_TOOLTIP)" not in card_states_source
    assert "buildCardState('Reviews', 'Pending', PENDING_TOOLTIP)" not in card_states_source
    assert "buildCardState('Reviews', 'Partial', PARTIAL_TOOLTIP)" not in card_states_source
    assert "buildCardState('Price', 'Pending', PENDING_TOOLTIP)" not in card_states_source

    forbidden_claims = [
        "full Steam catalog",
        "complete Steam catalog",
        "recommendation score",
        "Combined",
        "category-to-game",
        "scheduler",
        "live fetch",
        "DB write",
    ]
    for forbidden_claim in forbidden_claims:
        assert forbidden_claim not in card_states_source


def test_top_selling_chart_fallback_copy_stays_history_evidence_bounded() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")
    chart_state_source = source.split("const getChartState", maxsplit=1)[1].split(
        "const getSevenDayAverage",
        maxsplit=1,
    )[0]

    assert (
        "const CHART_HISTORY_LOADING_MESSAGE = "
        "'선택한 게임의 CCU history evidence를 불러오는 중입니다.'"
        in source
    )
    assert (
        "const CHART_HISTORY_EMPTY_MESSAGE = "
        "'선택한 게임의 CCU history evidence가 아직 없습니다.'"
        in source
    )
    assert (
        "const CHART_HISTORY_ERROR_MESSAGE = "
        "'선택한 게임의 CCU history evidence를 불러오지 못했습니다.'"
        in source
    )
    assert (
        "const CHART_HISTORY_UNMAPPED_MESSAGE = "
        "'이 ranked Steam row는 CCU history evidence와 연결되지 않았습니다.'"
        in source
    )

    assert "row.canonicalGameId === null" in chart_state_source
    assert "message: CHART_HISTORY_UNMAPPED_MESSAGE" in chart_state_source
    assert "historyErrorCanonicalGameIds[row.canonicalGameId]" in chart_state_source
    assert "message: CHART_HISTORY_ERROR_MESSAGE" in chart_state_source
    assert (
        "historyLoadingCanonicalGameId === row.canonicalGameId && historyRows === undefined"
        in chart_state_source
    )
    assert "message: CHART_HISTORY_LOADING_MESSAGE" in chart_state_source
    assert "historyRows === undefined" in chart_state_source
    assert "historyRows.length === 0" in chart_state_source
    assert "message: CHART_HISTORY_EMPTY_MESSAGE" in chart_state_source
    assert "DELAYED_MESSAGE" not in chart_state_source

    forbidden_claims = [
        "trusted mapping",
        "Combined",
        "category-to-game",
        "scheduler",
        "live fetch",
        "DB write",
    ]
    for forbidden_claim in forbidden_claims:
        assert forbidden_claim not in chart_state_source


def test_top_selling_detail_history_keeps_fixed_daily_90d_read() -> None:
    api_source = GAMES_API_PATH.read_text(encoding="utf-8")
    overview_hook_source = STEAM_OVERVIEW_HOOK_PATH.read_text(encoding="utf-8")
    view_model_source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "function getGameCcuDaily90d" in api_source
    assert "`/games/${canonicalGameId}/ccu/daily-90d`" in api_source
    assert "withQuery(`/games/${canonicalGameId}/ccu/daily-90d`" not in api_source
    assert "gamesApi.getGameCcuDaily90d(canonicalGameId, controller.signal)" in overview_hook_source
    assert "'30D': buildTimelinePoints(historyRows, '30D')" in view_model_source
    assert "'90D': buildTimelinePoints(historyRows, '90D')" in view_model_source


def test_top_selling_expansion_limit_lives_in_overview_hook() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    overview_hook_source = STEAM_OVERVIEW_HOOK_PATH.read_text(encoding="utf-8")
    view_model_source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    build_steam_games_source = view_model_source.split(
        "export function buildSteamGames",
        maxsplit=1,
    )[1]

    assert ".slice(0, 4)" not in build_steam_games_source
    assert (
        "const baseRows = mode === 'Explore' ? [] : buildTopSellingRows(data)"
        in view_model_source
    )
    assert (
        "const games = rankingCardLimit === null ? allGames : allGames.slice(0, rankingCardLimit)"
        in overview_hook_source
    )
    assert "totalGameCount: allGames.length" in overview_hook_source
    assert "const DEFAULT_LIMIT = 12" in overview_hook_source
    assert "rankingCardLimit: showExpandedRanking ? null : 4" in app_source
    assert "canExpand={steamTotalGameCount > steamGames.length}" in app_source


def test_top_selling_list_includes_loaded_count_search_context() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    ranking_list_source = STEAM_RANKING_LIST_PATH.read_text(encoding="utf-8")

    assert "totalGameCount?: number" in ranking_list_source
    assert "searchQuery?: string" in ranking_list_source
    assert "const totalCount = totalGameCount ?? games.length" in ranking_list_source
    assert "const hasSearch = searchQuery.trim().length > 0" in ranking_list_source
    assert "loaded weekly top sellers match current search" in ranking_list_source
    assert "loaded weekly top sellers" in ranking_list_source
    assert "Showing all ${totalCountLabel} loaded weekly top sellers" in ranking_list_source
    assert (
        "Showing ${shownCountLabel} of ${totalCountLabel} loaded weekly top sellers"
        in ranking_list_source
    )
    assert "cursor-pointer text-sm text-[var(--text-secondary)]" in ranking_list_source
    assert "totalGameCount={steamTotalGameCount}" in app_source
    assert "searchQuery={deferredSearch}" in app_source

    forbidden_claims = [
        "full Steam catalog",
        "all Steam games",
        "complete Steam catalog",
        "full sales universe",
    ]
    for forbidden_claim in forbidden_claims:
        assert forbidden_claim not in ranking_list_source
