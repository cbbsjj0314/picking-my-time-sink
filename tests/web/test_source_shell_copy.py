from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
SOURCE_TABS_ROW_PATH = Path("web/src/components/SourceTabsRow.tsx")
COMBINED_API_PATH = Path("web/src/api/combined.ts")
COMBINED_HOOK_PATH = Path("web/src/hooks/useCombinedGameOverview.ts")
COMBINED_TABLE_PATH = Path("web/src/components/CombinedGameOverviewTable.tsx")
COMBINED_VIEW_MODEL_PATH = Path("web/src/lib/combinedGameOverviewViewModel.ts")
WEB_SRC_PATH = Path("web/src")
API_SRC_PATH = Path("src/api")
SQL_POSTGRES_PATH = Path("sql/postgres")


def _read_tree(path: Path, pattern: str) -> str:
    return "\n".join(
        file_path.read_text(encoding="utf-8")
        for file_path in sorted(path.rglob(pattern))
        if file_path.is_file()
    )


def _combined_web_surface_source() -> str:
    return "\n".join(
        [
            APP_PATH.read_text(encoding="utf-8"),
            SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8"),
            COMBINED_API_PATH.read_text(encoding="utf-8"),
            COMBINED_HOOK_PATH.read_text(encoding="utf-8"),
            COMBINED_TABLE_PATH.read_text(encoding="utf-8"),
            COMBINED_VIEW_MODEL_PATH.read_text(encoding="utf-8"),
        ]
    )


def test_chzzk_route_stays_connected_to_observed_source_view() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "sourceTab === 'Chzzk'" in source
    assert "<ChzzkCategoryTable" in source
    assert "enabled: sourceTab === 'Chzzk'" in source


def test_combined_route_uses_minimal_backend_overview_surface() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    api_source = COMBINED_API_PATH.read_text(encoding="utf-8")
    hook_source = COMBINED_HOOK_PATH.read_text(encoding="utf-8")

    assert "sourceTab === 'Combined'" in app_source
    assert "<CombinedGameOverviewTable" in app_source
    assert "PendingSourcePanel" not in app_source
    assert "'/combined/games/overview'" in api_source
    assert "requestJson<CombinedGameOverview[]>" in api_source
    assert "limit: options.limit ?? 50" in api_source
    assert "enabled: sourceTab === 'Combined'" in app_source
    assert "combinedApi.listGameOverview" in hook_source


def test_source_tabs_explain_current_source_boundaries() -> None:
    source = SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8")

    assert "Combined minimal identity/source availability view." in source
    assert "Steam source view" in source
    assert "Chzzk observed source view" in source
    assert "aria-label={boundaryCopy}" in source
    assert "title={boundaryCopy}" in source


def test_source_tabs_expose_selected_state_semantics() -> None:
    source = SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8")

    assert "const selected = tab === sourceTab" in source
    assert "aria-pressed={selected}" in source
    assert "aria-label={boundaryCopy}" in source
    assert "title={boundaryCopy}" in source
    assert "onClick={() => onChange(tab)}" in source
    assert "{tab}" in source
    assert "selected\n                  ? 'bg-[#E8639B]" in source
    assert 'role="tablist"' not in source
    assert 'role="tab"' not in source


def test_combined_web_api_exposes_only_approved_fields() -> None:
    source = COMBINED_API_PATH.read_text(encoding="utf-8")

    for field in [
        "canonical_game_id",
        "canonical_name",
        "steam_appid",
        "steam_source_available",
        "chzzk_mapping_available",
        "chzzk_category_id",
        "category_name",
        "category_type",
        "latest_bucket_time",
    ]:
        assert field in source

    for forbidden_field in [
        "mapping_status",
        "source_kind",
        "reviewed_by",
        "reviewed_at",
        "candidate_id",
        "candidate_status",
        "latest_viewers_observed",
        "viewer_hours_observed",
        "avg_viewers_observed",
        "peak_viewers_observed",
        "viewer_per_channel_observed",
        "unique_channels_observed",
        "rank",
        "ranking",
        "kpi",
        "score",
        "recommendation",
        "mapping_coverage",
        "fallback_mapping",
        "unresolved_mapping",
        "rejected_mapping",
    ]:
        assert forbidden_field not in source


def test_combined_web_surface_uses_only_combined_overview_endpoint() -> None:
    source = _combined_web_surface_source()

    assert "/combined/games/overview" in source
    for forbidden_endpoint in [
        "/chzzk/category-game-mappings",
        "/chzzk/categories/overview",
        "/games/explore/overview",
        "/games/rankings/latest",
        "/games/ccu/latest",
        "/games/price/latest",
        "/games/reviews/latest",
    ]:
        assert forbidden_endpoint not in source


def test_combined_web_surface_does_not_expose_metrics_or_product_semantics() -> None:
    source = _combined_web_surface_source().lower()

    for needle in [
        "latest_viewers_observed",
        "viewer_hours_observed",
        "avg_viewers_observed",
        "peak_viewers_observed",
        "viewer_per_channel_observed",
        "unique_channels_observed",
        "mapping coverage",
        "mapping_coverage",
        "candidate mapping",
        "unresolved mapping",
        "rejected mapping",
        "fallback mapping",
        "candidate_status",
        "categorytype=game",
        "inferred mapping",
        "guessed mapping",
        "kpi",
        "score",
        "recommendation",
        "recommended",
        "ranked combined",
        "combined ranking",
        "popularity",
        "freshness score",
    ]:
        assert needle not in source


def test_combined_backend_surface_remains_minimal() -> None:
    api_source = _read_tree(API_SRC_PATH, "*.py")
    sql_source = _read_tree(SQL_POSTGRES_PATH, "*.sql")
    combined_sql = Path("sql/postgres/028_srv_combined_game_overview.sql").read_text(
        encoding="utf-8"
    )

    assert 'prefix="/combined"' in api_source
    assert '"/games/overview"' in api_source
    assert "srv_combined_game_overview" in sql_source

    for needle in ["combined_source", "CombinedSource", "MappingCoverage"]:
        assert needle not in api_source

    for needle in [
        "combined_source",
        "create or replace view combined",
        "create or replace view srv_game_combined",
        "mapping_coverage",
        "latest_viewers_observed",
        "viewer_hours_observed",
        "candidate_status",
    ]:
        assert needle not in combined_sql.lower()


def test_no_legacy_pending_combined_shell_remains_wired() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    web_source = _read_tree(WEB_SRC_PATH, "*.tsx") + "\n" + _read_tree(WEB_SRC_PATH, "*.ts")

    assert "PendingSourcePanel" not in app_source
    assert "Combined 소스는 아직 준비 중" not in web_source
    assert "CombinedWhySurfacedNow" not in app_source
