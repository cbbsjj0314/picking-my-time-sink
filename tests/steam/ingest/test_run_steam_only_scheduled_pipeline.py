from __future__ import annotations

from pathlib import Path

import pytest

from steam.ingest import run_steam_only_scheduled_pipeline


def test_build_parser_accepts_single_command_wrapper_shape() -> None:
    parser = run_steam_only_scheduled_pipeline.build_parser()
    args = parser.parse_args([])

    assert vars(args) == {}


def test_run_executes_manual_runbook_order_with_fixed_handoff_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    expected_results = {
        "tracked_universe": [{"stage": "tracked_universe"}],
        "rankings": [{"stage": "rankings"}],
        "price_bronze": [{"stage": "price_bronze"}],
        "price_silver": [{"stage": "price_silver"}],
        "price_gold": [{"stage": "price_gold"}],
        "reviews_bronze": [{"stage": "reviews_bronze"}],
        "reviews_silver": [{"stage": "reviews_silver"}],
        "reviews_gold": [{"stage": "reviews_gold"}],
        "ccu_bronze": [{"stage": "ccu_bronze"}],
        "ccu_silver": [{"stage": "ccu_silver"}],
        "ccu_gold": [{"stage": "ccu_gold"}],
    }

    def fake_tracked_universe_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("tracked_universe", dict(kwargs)))
        return expected_results["tracked_universe"]

    def fake_rankings_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("rankings", dict(kwargs)))
        return expected_results["rankings"]

    def fake_price_fetch_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("price_bronze", dict(kwargs)))
        return expected_results["price_bronze"]

    def fake_price_silver_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("price_silver", dict(kwargs)))
        return expected_results["price_silver"]

    def fake_price_gold_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("price_gold", dict(kwargs)))
        return expected_results["price_gold"]

    def fake_reviews_fetch_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("reviews_bronze", dict(kwargs)))
        return expected_results["reviews_bronze"]

    def fake_reviews_silver_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("reviews_silver", dict(kwargs)))
        return expected_results["reviews_silver"]

    def fake_reviews_gold_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("reviews_gold", dict(kwargs)))
        return expected_results["reviews_gold"]

    def fake_ccu_fetch_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("ccu_bronze", dict(kwargs)))
        return expected_results["ccu_bronze"]

    def fake_ccu_silver_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("ccu_silver", dict(kwargs)))
        return expected_results["ccu_silver"]

    def fake_ccu_gold_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("ccu_gold", dict(kwargs)))
        return expected_results["ccu_gold"]

    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.run_tracked_universe_scheduled,
        "run",
        fake_tracked_universe_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.payload_to_gold_rankings,
        "run",
        fake_rankings_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.fetch_price_1h,
        "run",
        fake_price_fetch_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.bronze_to_silver_price,
        "run",
        fake_price_silver_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.silver_to_gold_price,
        "run",
        fake_price_gold_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.fetch_reviews_daily,
        "run",
        fake_reviews_fetch_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.bronze_to_silver_reviews,
        "run",
        fake_reviews_silver_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.silver_to_gold_reviews,
        "run",
        fake_reviews_gold_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.fetch_ccu_30m,
        "run",
        fake_ccu_fetch_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.bronze_to_silver_ccu,
        "run",
        fake_ccu_silver_run,
    )
    monkeypatch.setattr(
        run_steam_only_scheduled_pipeline.silver_to_gold_ccu,
        "run",
        fake_ccu_gold_run,
    )

    result = run_steam_only_scheduled_pipeline.run()

    assert result == expected_results
    assert calls == [
        (
            "tracked_universe",
            {
                "result_path": (
                    run_steam_only_scheduled_pipeline.DEFAULT_TRACKED_UNIVERSE_RESULT_PATH
                ),
            },
        ),
        (
            "rankings",
            {
                "result_path": run_steam_only_scheduled_pipeline.DEFAULT_RANKINGS_RESULT_PATH,
            },
        ),
        (
            "price_bronze",
            {
                "output_path": Path("tmp/steam/handoff/price.bronze.jsonl"),
                "timeout_seconds": 10.0,
                "max_attempts": 4,
                "backoff_base_seconds": 0.5,
                "jitter_max_seconds": 0.3,
                "max_backoff_seconds": 8.0,
                "meta_path": None,
            },
        ),
        (
            "price_silver",
            {
                "input_path": Path("tmp/steam/handoff/price.bronze.jsonl"),
                "output_path": Path("tmp/steam/handoff/price.silver.jsonl"),
            },
        ),
        (
            "price_gold",
            {
                "input_path": Path("tmp/steam/handoff/price.silver.jsonl"),
                "result_path": Path("tmp/steam/handoff/price.gold-result.jsonl"),
            },
        ),
        (
            "reviews_bronze",
            {
                "output_path": Path("tmp/steam/handoff/reviews.bronze.jsonl"),
                "timeout_seconds": 10.0,
                "max_attempts": 4,
                "backoff_base_seconds": 0.5,
                "jitter_max_seconds": 0.3,
                "max_backoff_seconds": 8.0,
                "meta_path": None,
            },
        ),
        (
            "reviews_silver",
            {
                "input_path": Path("tmp/steam/handoff/reviews.bronze.jsonl"),
                "output_path": Path("tmp/steam/handoff/reviews.silver.jsonl"),
            },
        ),
        (
            "reviews_gold",
            {
                "input_path": Path("tmp/steam/handoff/reviews.silver.jsonl"),
                "result_path": Path("tmp/steam/handoff/reviews.gold-result.jsonl"),
            },
        ),
        (
            "ccu_bronze",
            {
                "output_path": Path("tmp/steam/handoff/ccu.bronze.jsonl"),
                "timeout_seconds": 10.0,
                "max_attempts": 4,
                "backoff_base_seconds": 0.5,
                "jitter_max_seconds": 0.3,
                "max_backoff_seconds": 8.0,
                "meta_path": None,
            },
        ),
        (
            "ccu_silver",
            {
                "input_path": Path("tmp/steam/handoff/ccu.bronze.jsonl"),
                "output_path": Path("tmp/steam/handoff/ccu.silver.jsonl"),
            },
        ),
        (
            "ccu_gold",
            {
                "input_path": Path("tmp/steam/handoff/ccu.silver.jsonl"),
                "result_path": Path("tmp/steam/handoff/ccu.gold-result.jsonl"),
            },
        ),
    ]
