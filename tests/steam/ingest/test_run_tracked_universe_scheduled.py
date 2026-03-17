from __future__ import annotations

from pathlib import Path

import pytest

from steam.ingest import run_tracked_universe_scheduled


def test_build_parser_requires_explicit_ranking_paths(capsys: pytest.CaptureFixture[str]) -> None:
    parser = run_tracked_universe_scheduled.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    err = capsys.readouterr().err
    assert "--topsellers-global-path" in err
    assert "--topsellers-kr-path" in err
    assert "--mostplayed-global-path" in err
    assert "--mostplayed-kr-path" in err


def test_build_parser_keeps_optional_catalog_omitted_and_result_default() -> None:
    parser = run_tracked_universe_scheduled.build_parser()
    args = parser.parse_args(
        [
            "--topsellers-global-path",
            "topsellers-global.json",
            "--topsellers-kr-path",
            "topsellers-kr.json",
            "--mostplayed-global-path",
            "mostplayed-global.json",
            "--mostplayed-kr-path",
            "mostplayed-kr.json",
        ]
    )

    assert args.app_catalog_path is None
    assert (
        args.result_path
        == run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_RESULT_PATH
    )


def test_run_delegates_to_wrapper_side_core_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected_rows = [{"canonical_game_id": 1, "steam_appid": 730}]

    def fake_run(**kwargs: object) -> list[dict[str, object]]:
        captured.update(kwargs)
        return expected_rows

    monkeypatch.setattr(run_tracked_universe_scheduled.tracked_universe_core, "run", fake_run)

    result = run_tracked_universe_scheduled.run(
        topsellers_global_path=Path("topsellers-global.json"),
        topsellers_kr_path=Path("topsellers-kr.json"),
        mostplayed_global_path=Path("mostplayed-global.json"),
        mostplayed_kr_path=Path("mostplayed-kr.json"),
    )

    assert result == expected_rows
    assert captured == {
        "topsellers_global_path": Path("topsellers-global.json"),
        "topsellers_kr_path": Path("topsellers-kr.json"),
        "mostplayed_global_path": Path("mostplayed-global.json"),
        "mostplayed_kr_path": Path("mostplayed-kr.json"),
        "app_catalog_path": None,
        "result_path": run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_RESULT_PATH,
    }


def test_run_delegates_explicit_override_paths_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    explicit_app_catalog_path = Path("catalog-summary.json")
    explicit_result_path = Path("custom-result.jsonl")

    def fake_run(**kwargs: object) -> list[dict[str, object]]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(run_tracked_universe_scheduled.tracked_universe_core, "run", fake_run)

    result = run_tracked_universe_scheduled.run(
        topsellers_global_path=Path("topsellers-global.json"),
        topsellers_kr_path=Path("topsellers-kr.json"),
        mostplayed_global_path=Path("mostplayed-global.json"),
        mostplayed_kr_path=Path("mostplayed-kr.json"),
        app_catalog_path=explicit_app_catalog_path,
        result_path=explicit_result_path,
    )

    assert result == []
    assert captured["app_catalog_path"] == explicit_app_catalog_path
    assert captured["result_path"] == explicit_result_path
