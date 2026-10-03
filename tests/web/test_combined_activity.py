import subprocess
from pathlib import Path


def test_scatter_runtime_null_zero_axes_states_and_accessible_labels():
    result = subprocess.run(
        ["node", "tests/web/combined_activity_runtime.cjs"],
        check=True, capture_output=True, text=True,
    )
    assert "Combined activity runtime assertions passed" in result.stdout


def test_activity_hook_is_separate_and_preserves_overview_wiring():
    hook = Path("web/src/hooks/useCombinedGameActivity.ts").read_text()
    assert "if (!enabled) return" in hook
    assert "listGameActivity(controller.signal)" in hook
    assert "controller.signal.aborted" in hook
    assert "controller.abort()" in hook
    app = Path("web/src/App.tsx").read_text()
    assert "useCombinedGameActivity(sourceTab === 'Combined')" in app
    assert "<CombinedGameActivityScatter" in app
    assert "<CombinedGameOverviewTable" in app
    overview = Path("web/src/hooks/useCombinedGameOverview.ts").read_text()
    assert "combinedApi.listGameOverview" in overview
    assert "listGameActivity" not in overview
