from __future__ import annotations

from pathlib import Path

import pytest

from steam.ingest import run_tracked_universe_scheduled


def test_build_parser_uses_runtime_ranking_defaults() -> None:
    parser = run_tracked_universe_scheduled.build_parser()
    args = parser.parse_args([])

    assert args.app_catalog_path is None
    assert (
        args.topsellers_global_path
        == run_tracked_universe_scheduled.rankings_probe.DEFAULT_TOPSELLERS_GLOBAL_PATH
    )
    assert (
        args.topsellers_kr_path
        == run_tracked_universe_scheduled.rankings_probe.DEFAULT_TOPSELLERS_KR_PATH
    )
    assert (
        args.mostplayed_global_path
        == run_tracked_universe_scheduled.rankings_probe.DEFAULT_MOSTPLAYED_GLOBAL_PATH
    )
    assert (
        args.mostplayed_kr_path
        == run_tracked_universe_scheduled.rankings_probe.DEFAULT_MOSTPLAYED_KR_PATH
    )
    assert (
        args.result_path
        == run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_RESULT_PATH
    )


def test_run_fetches_rankings_then_delegates_to_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    expected_rows = [{"canonical_game_id": 1, "steam_appid": 730}]

    def fake_rankings_run(**kwargs: object) -> list[Path]:
        calls.append(("rankings", dict(kwargs)))
        return []

    def fake_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("core", dict(kwargs)))
        return expected_rows

    monkeypatch.setattr(run_tracked_universe_scheduled.rankings_probe, "run", fake_rankings_run)
    monkeypatch.setattr(run_tracked_universe_scheduled.tracked_universe_core, "run", fake_run)

    result = run_tracked_universe_scheduled.run(
        topsellers_global_path=Path("topsellers-global.json"),
        topsellers_kr_path=Path("topsellers-kr.json"),
        mostplayed_global_path=Path("mostplayed-global.json"),
        mostplayed_kr_path=Path("mostplayed-kr.json"),
    )

    assert result == expected_rows
    assert calls == [
        (
            "rankings",
            {
                "topsellers_global_path": Path("topsellers-global.json"),
                "topsellers_kr_path": Path("topsellers-kr.json"),
                "mostplayed_global_path": Path("mostplayed-global.json"),
                "mostplayed_kr_path": Path("mostplayed-kr.json"),
            },
        ),
        (
            "core",
            {
                "topsellers_global_path": Path("topsellers-global.json"),
                "topsellers_kr_path": Path("topsellers-kr.json"),
                "mostplayed_global_path": Path("mostplayed-global.json"),
                "mostplayed_kr_path": Path("mostplayed-kr.json"),
                "app_catalog_path": None,
                "result_path": (
                    run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_RESULT_PATH
                ),
            },
        ),
    ]


def test_run_delegates_explicit_override_paths_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    explicit_app_catalog_path = Path("catalog-summary.json")
    explicit_result_path = Path("custom-result.jsonl")

    def fake_rankings_run(**kwargs: object) -> list[Path]:
        calls.append(("rankings", dict(kwargs)))
        return []

    def fake_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("core", dict(kwargs)))
        return []

    monkeypatch.setattr(run_tracked_universe_scheduled.rankings_probe, "run", fake_rankings_run)
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
    assert calls == [
        (
            "rankings",
            {
                "topsellers_global_path": Path("topsellers-global.json"),
                "topsellers_kr_path": Path("topsellers-kr.json"),
                "mostplayed_global_path": Path("mostplayed-global.json"),
                "mostplayed_kr_path": Path("mostplayed-kr.json"),
            },
        ),
        (
            "core",
            {
                "topsellers_global_path": Path("topsellers-global.json"),
                "topsellers_kr_path": Path("topsellers-kr.json"),
                "mostplayed_global_path": Path("mostplayed-global.json"),
                "mostplayed_kr_path": Path("mostplayed-kr.json"),
                "app_catalog_path": explicit_app_catalog_path,
                "result_path": explicit_result_path,
            },
        ),
    ]
