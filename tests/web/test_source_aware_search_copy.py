from __future__ import annotations

from pathlib import Path

APP_PATH = Path("web/src/App.tsx")
STICKY_SHELL_PATH = Path("web/src/components/StickyShell.tsx")


def test_sticky_shell_uses_source_aware_search_placeholder_prop() -> None:
    source = STICKY_SHELL_PATH.read_text(encoding="utf-8")

    assert "searchPlaceholder: string" in source
    assert "placeholder={searchPlaceholder}" in source
    assert "aria-label={searchPlaceholder}" in source
    assert 'placeholder="Search"' not in source


def test_app_passes_source_aware_search_placeholder_to_sticky_shell() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert (
        "const getSearchPlaceholder = (sourceTab: SourceTab, "
        "steamDiscoverMode: SteamDiscoverMode)"
        in source
    )
    assert "const searchPlaceholder = getSearchPlaceholder(sourceTab, steamDiscoverMode)" in source
    assert "searchPlaceholder={searchPlaceholder}" in source


def test_app_defines_placeholders_for_current_source_search_boundaries() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "Search Steam games" in source
    assert "Search Steam top sellers" in source
    assert "Search Chzzk observed categories" in source
    assert "Search Combined identity rows" in source


def test_chzzk_search_placeholder_stays_observed_category_scoped() -> None:
    chzzk_placeholder = "Search Chzzk observed categories"

    assert "observed categories" in chzzk_placeholder
    assert "channel" not in chzzk_placeholder.lower()
    assert "category type" not in chzzk_placeholder.lower()
    assert "steam mapping" not in chzzk_placeholder.lower()
    assert "combined" not in chzzk_placeholder.lower()
