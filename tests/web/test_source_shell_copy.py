from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
PENDING_SOURCE_PANEL_PATH = Path("web/src/components/PendingSourcePanel.tsx")
SOURCE_TABS_ROW_PATH = Path("web/src/components/SourceTabsRow.tsx")
WEB_SRC_PATH = Path("web/src")
API_SRC_PATH = Path("src/api")
SQL_POSTGRES_PATH = Path("sql/postgres")


def _read_tree(path: Path, pattern: str) -> str:
    return "\n".join(
        file_path.read_text(encoding="utf-8")
        for file_path in sorted(path.rglob(pattern))
        if file_path.is_file()
    )


def test_pending_source_panel_is_combined_only() -> None:
    source = PENDING_SOURCE_PANEL_PATH.read_text(encoding="utf-8")

    assert "sourceTab: Extract<SourceTab, 'Combined'>" in source
    assert (
        "Record<Extract<SourceTab, 'Combined'>, "
        "{ title: string; body: string; note: string }>"
        in source
    )
    assert "Combined 소스는 아직 준비 중" in source
    assert (
        "Steam과 Chzzk 관측 데이터를 하나의 판단 화면으로 합치는 기능은 아직 준비 중이다."
        in source
    )
    assert (
        "현재는 Steam source view와 Chzzk observed source view를 각각 분리해서 제공한다."
        in source
    )
    assert "Chzzk:" not in source


def test_stale_chzzk_pending_copy_is_removed() -> None:
    source = PENDING_SOURCE_PANEL_PATH.read_text(encoding="utf-8")

    stale_copy = [
        "Chzzk 소스는 아직 준비 중",
        "Chzzk 실데이터 경로는 아직 연결되지 않음",
        "현재는 Steam만 실제 데이터로 연결되어 있음",
    ]
    for copy in stale_copy:
        assert copy not in source


def test_chzzk_route_stays_connected_to_observed_source_view() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "sourceTab === 'Chzzk'" in source
    assert "<ChzzkCategoryTable" in source
    assert "<PendingSourcePanel sourceTab={sourceTab} />" in source


def test_source_tabs_explain_current_source_boundaries() -> None:
    source = SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8")

    assert "Combined source is planned." in source
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


def test_source_shell_copy_does_not_claim_deferred_work_is_implemented() -> None:
    shell_source = "\n".join(
        [
            PENDING_SOURCE_PANEL_PATH.read_text(encoding="utf-8"),
            SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8"),
        ]
    )

    forbidden_claims = [
        "Combined semantics",
        "Combined KPI",
        "trusted mapping",
        "category-to-game",
        "Steam-equivalent",
        "completed baseline",
        "scheduler",
        "live fetch",
        "DB write",
    ]
    for claim in forbidden_claims:
        assert claim not in shell_source


def test_combined_pending_shell_does_not_gain_mapping_fields() -> None:
    source = "\n".join(
        [
            APP_PATH.read_text(encoding="utf-8"),
            PENDING_SOURCE_PANEL_PATH.read_text(encoding="utf-8"),
            SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8"),
        ]
    )

    assert "<PendingSourcePanel sourceTab={sourceTab} />" in source
    assert "sourceTab: Extract<SourceTab, 'Combined'>" in source
    for needle in [
        "canonical_game_id",
        "steam_appid",
        "mapped_steam_game",
        "mapping_status",
        "mapping_method",
        "mapping_confidence",
        "canonicalGame",
        "mappedSteamGame",
        "mappingStatus",
        "mappingMethod",
        "mappingConfidence",
        "category-game-mappings",
    ]:
        assert needle not in source


def test_no_combined_api_or_sql_surface_exists_yet() -> None:
    api_source = _read_tree(API_SRC_PATH, "*.py")
    sql_source = _read_tree(SQL_POSTGRES_PATH, "*.sql")

    for needle in [
        "/combined",
        "combined source",
        "combined_source",
        "CombinedResponse",
        "CombinedOverview",
        "list_combined",
        "combined_router",
    ]:
        assert needle not in api_source

    for needle in [
        "srv_combined",
        "combined_source",
        "combined source",
        "create or replace view combined",
        "create or replace view srv_game_combined",
    ]:
        assert needle not in sql_source.lower()


def test_no_combined_web_data_surface_or_mapping_coverage_panel_exists_yet() -> None:
    app_source = APP_PATH.read_text(encoding="utf-8")
    web_source = _read_tree(WEB_SRC_PATH, "*.tsx") + "\n" + _read_tree(WEB_SRC_PATH, "*.ts")

    assert "<PendingSourcePanel sourceTab={sourceTab} />" in app_source
    assert "CombinedWhySurfacedNow" not in app_source
    assert "useCombined" not in web_source
    assert "combinedApi" not in web_source
    assert "CombinedTable" not in web_source
    assert "CombinedSourceTable" not in web_source
    assert "MappingCoverage" not in web_source
    assert "mapping coverage" not in web_source.lower()
    assert "category-game-mappings" not in web_source


def test_combined_shell_does_not_gain_ranking_kpi_or_score_semantics() -> None:
    source = "\n".join(
        [
            APP_PATH.read_text(encoding="utf-8"),
            PENDING_SOURCE_PANEL_PATH.read_text(encoding="utf-8"),
            SOURCE_TABS_ROW_PATH.read_text(encoding="utf-8"),
        ]
    ).lower()

    for needle in [
        "kpi",
        "score",
        "recommendation",
        "recommended",
        "ranked combined",
        "combined ranking",
        "mapping coverage",
        "candidate mapping",
        "unresolved mapping",
        "rejected mapping",
        "categorytype=game",
        "inferred mapping",
        "guessed mapping",
        "fallback mapping",
    ]:
        assert needle not in source
