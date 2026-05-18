from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
PENDING_SOURCE_PANEL_PATH = Path("web/src/components/PendingSourcePanel.tsx")
SOURCE_TABS_ROW_PATH = Path("web/src/components/SourceTabsRow.tsx")


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
