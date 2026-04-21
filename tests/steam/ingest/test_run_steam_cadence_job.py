from __future__ import annotations

import json
from pathlib import Path

import pytest

from steam.ingest import run_steam_cadence_job


def test_build_parser_accepts_scheduler_job_shape() -> None:
    parser = run_steam_cadence_job.build_parser()
    args = parser.parse_args(
        [
            "ccu-30m",
            "--base-dir",
            "tmp/test-jobs",
            "--run-id",
            "manual-smoke",
            "--lock-wait-sec",
            "1.5",
        ]
    )

    assert args.job == run_steam_cadence_job.JOB_CCU_30M
    assert args.base_dir == Path("tmp/test-jobs")
    assert args.run_id == "manual-smoke"
    assert args.lock_wait_sec == 1.5


def test_price_job_runs_fixed_hourly_boundary_with_scoped_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_fetch(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("fetch_price_1h", dict(kwargs)))
        return [{"stage": "bronze"}]

    def fake_silver(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("bronze_to_silver_price", dict(kwargs)))
        return [{"stage": "silver"}]

    def fake_gold(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("silver_to_gold_price", dict(kwargs)))
        return [{"stage": "gold"}]

    monkeypatch.setattr(run_steam_cadence_job.fetch_price_1h, "run", fake_fetch)
    monkeypatch.setattr(run_steam_cadence_job.bronze_to_silver_price, "run", fake_silver)
    monkeypatch.setattr(run_steam_cadence_job.silver_to_gold_price, "run", fake_gold)

    base_dir = tmp_path / "jobs"
    result = run_steam_cadence_job.run_job_with_evidence(
        run_steam_cadence_job.JOB_PRICE_1H,
        base_dir=base_dir,
        run_id="price-run",
    )

    run_dir = base_dir / "price-1h" / "price-run"
    assert result["status"] == "success"
    assert result["success"] is True
    assert (run_dir / "result.json").exists()
    assert (run_dir / "meta" / "job.meta.json").exists()
    assert (run_dir / "price-1h.log").exists()
    assert calls == [
        (
            "fetch_price_1h",
            {
                "output_path": run_dir / "price.bronze.jsonl",
                "timeout_seconds": 10.0,
                "max_attempts": 4,
                "backoff_base_seconds": 0.5,
                "jitter_max_seconds": 0.3,
                "max_backoff_seconds": 8.0,
                "meta_path": run_dir / "meta" / "steps" / "fetch_price_1h.meta.json",
            },
        ),
        (
            "bronze_to_silver_price",
            {
                "input_path": run_dir / "price.bronze.jsonl",
                "output_path": run_dir / "price.silver.jsonl",
            },
        ),
        (
            "silver_to_gold_price",
            {
                "input_path": run_dir / "price.silver.jsonl",
                "result_path": run_dir / "price.gold-result.jsonl",
                "meta_path": run_dir / "meta" / "steps" / "silver_to_gold_price.meta.json",
            },
        ),
    ]


def test_ccu_job_marks_per_app_missing_evidence_as_partial_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_steam_cadence_job.fetch_ccu_30m,
        "run",
        lambda **kwargs: [
            {"canonical_game_id": 1, "missing_reason": None},
            {"canonical_game_id": 2, "missing_reason": "http_404"},
        ],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.bronze_to_silver_ccu,
        "run",
        lambda **kwargs: [
            {"canonical_game_id": 1, "missing_reason": None},
            {"canonical_game_id": 2, "missing_reason": "http_404"},
        ],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.silver_to_gold_ccu,
        "run",
        lambda **kwargs: [
            {"canonical_game_id": 1, "skipped": False},
            {"canonical_game_id": 2, "skipped": True},
        ],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.gold_to_agg_ccu_daily,
        "run",
        lambda **kwargs: [{"canonical_game_id": 1}],
    )

    base_dir = tmp_path / "jobs"
    result = run_steam_cadence_job.run_job_with_evidence(
        run_steam_cadence_job.JOB_CCU_30M,
        base_dir=base_dir,
        run_id="ccu-run",
    )

    run_dir = base_dir / "ccu-30m" / "ccu-run"
    meta = json.loads((run_dir / "meta" / "job.meta.json").read_text(encoding="utf-8"))
    assert result["status"] == "partial_success"
    assert result["success"] is True
    assert result["partial_success"] is True
    assert result["triage"]["missing_evidence_records"] == 1
    assert result["triage"]["gold_loaded_records"] == 1
    assert result["triage"]["gold_skipped_records"] == 1
    assert meta["success"] is True
    assert meta["partial_success"] is True
    assert run_steam_cadence_job.exit_code_for_status(str(result["status"])) == 0


def test_daily_job_runs_tracked_rankings_and_reviews_with_scoped_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tracked(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("run_tracked_universe_scheduled", dict(kwargs)))
        return [{"stage": "tracked"}]

    def fake_rankings(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("payload_to_gold_rankings", dict(kwargs)))
        return [{"stage": "rankings"}]

    def fake_reviews_fetch(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("fetch_reviews_daily", dict(kwargs)))
        return [{"stage": "reviews_bronze"}]

    def fake_reviews_silver(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("bronze_to_silver_reviews", dict(kwargs)))
        return [{"stage": "reviews_silver"}]

    def fake_reviews_gold(**kwargs: object) -> list[dict[str, object]]:
        calls.append(("silver_to_gold_reviews", dict(kwargs)))
        return [{"stage": "reviews_gold", "skipped": False}]

    monkeypatch.setattr(
        run_steam_cadence_job.run_tracked_universe_scheduled,
        "run",
        fake_tracked,
    )
    monkeypatch.setattr(
        run_steam_cadence_job.payload_to_gold_rankings,
        "run",
        fake_rankings,
    )
    monkeypatch.setattr(
        run_steam_cadence_job.fetch_reviews_daily,
        "run",
        fake_reviews_fetch,
    )
    monkeypatch.setattr(
        run_steam_cadence_job.bronze_to_silver_reviews,
        "run",
        fake_reviews_silver,
    )
    monkeypatch.setattr(
        run_steam_cadence_job.silver_to_gold_reviews,
        "run",
        fake_reviews_gold,
    )

    base_dir = tmp_path / "jobs"
    app_catalog_path = tmp_path / "latest.summary.json"
    result = run_steam_cadence_job.run_job_with_evidence(
        run_steam_cadence_job.JOB_DAILY,
        base_dir=base_dir,
        run_id="daily-run",
        app_catalog_path=app_catalog_path,
    )

    run_dir = base_dir / "daily" / "daily-run"
    rankings_dir = run_dir / "rankings"
    assert result["status"] == "success"
    assert [name for name, _kwargs in calls] == [
        "run_tracked_universe_scheduled",
        "payload_to_gold_rankings",
        "fetch_reviews_daily",
        "bronze_to_silver_reviews",
        "silver_to_gold_reviews",
    ]
    assert calls[0][1] == {
        "topsellers_global_path": rankings_dir / "topsellers_global.payload.json",
        "topsellers_kr_path": rankings_dir / "topsellers_kr.payload.json",
        "mostplayed_global_path": rankings_dir / "mostplayed_global.payload.json",
        "mostplayed_kr_path": rankings_dir / "mostplayed_kr.payload.json",
        "app_catalog_path": app_catalog_path,
        "result_path": run_dir / "tracked_universe.update-result.jsonl",
    }
    assert calls[1][1]["result_path"] == run_dir / "rankings.payload-to-gold-result.jsonl"
    assert calls[1][1]["meta_path"] == (
        run_dir / "meta" / "steps" / "payload_to_gold_rankings.meta.json"
    )
    assert calls[2][1]["output_path"] == run_dir / "reviews.bronze.jsonl"
    assert calls[3][1]["output_path"] == run_dir / "reviews.silver.jsonl"
    assert calls[4][1]["result_path"] == run_dir / "reviews.gold-result.jsonl"


def test_daily_job_marks_skipped_review_evidence_as_partial_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_steam_cadence_job.run_tracked_universe_scheduled,
        "run",
        lambda **kwargs: [{"canonical_game_id": 13, "is_active": True}],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.payload_to_gold_rankings,
        "run",
        lambda **kwargs: [{"rank_position": 1}],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.fetch_reviews_daily,
        "run",
        lambda **kwargs: [
            {"canonical_game_id": 13, "steam_appid": 2483190, "http_status": 200},
            {"canonical_game_id": 72, "steam_appid": 1422450, "http_status": 200},
        ],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.bronze_to_silver_reviews,
        "run",
        lambda **kwargs: [
            {"canonical_game_id": 13, "steam_appid": 2483190, "total_reviews": 0},
            {"canonical_game_id": 72, "steam_appid": 1422450, "total_reviews": 0},
        ],
    )
    monkeypatch.setattr(
        run_steam_cadence_job.silver_to_gold_reviews,
        "run",
        lambda **kwargs: [
            {"canonical_game_id": 13, "skipped": True},
            {"canonical_game_id": 72, "skipped": True},
        ],
    )

    base_dir = tmp_path / "jobs"
    result = run_steam_cadence_job.run_job_with_evidence(
        run_steam_cadence_job.JOB_DAILY,
        base_dir=base_dir,
        run_id="daily-partial",
    )

    run_dir = base_dir / "daily" / "daily-partial"
    meta = json.loads((run_dir / "meta" / "job.meta.json").read_text(encoding="utf-8"))
    assert result["status"] == "partial_success"
    assert result["success"] is True
    assert result["partial_success"] is True
    assert result["triage"]["reviews_skipped_records"] == 2
    assert result["triage"]["partial_reason"] == "reviews_skipped_evidence"
    assert meta["success"] is True
    assert meta["partial_success"] is True
    assert run_steam_cadence_job.exit_code_for_status(str(result["status"])) == 0


def test_job_lock_busy_writes_evidence_and_does_not_run_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    base_dir = tmp_path / "jobs"
    held_paths = run_steam_cadence_job.build_job_paths(
        job_name=run_steam_cadence_job.JOB_PRICE_1H,
        base_dir=base_dir,
        run_id="held",
    )
    held_lock = run_steam_cadence_job.NoOverlapLock(held_paths.lock_path)

    def fake_price_job(paths: run_steam_cadence_job.JobPaths) -> tuple[list[dict], dict]:
        calls.append(str(paths.run_dir))
        return [], {}

    monkeypatch.setattr(run_steam_cadence_job, "run_price_job", fake_price_job)

    try:
        assert held_lock.acquire(wait_seconds=0.0) is True
        result = run_steam_cadence_job.run_job_with_evidence(
            run_steam_cadence_job.JOB_PRICE_1H,
            base_dir=base_dir,
            run_id="blocked",
        )
    finally:
        held_lock.release()

    run_dir = base_dir / "price-1h" / "blocked"
    assert calls == []
    assert result["status"] == "lock_busy"
    assert result["lock_busy"] is True
    assert run_steam_cadence_job.exit_code_for_status(str(result["status"])) == (
        run_steam_cadence_job.LOCK_BUSY_EXIT_CODE
    )
    assert (run_dir / "result.json").exists()
    assert (run_dir / "meta" / "job.meta.json").exists()
    assert (run_dir / "price-1h.log").exists()


def test_app_catalog_job_keeps_latest_summary_consumer_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_app_catalog_run(**kwargs: object) -> list[dict[str, object]]:
        calls.append(dict(kwargs))
        return [{"appid": 10}]

    monkeypatch.setattr(
        run_steam_cadence_job.fetch_app_catalog_weekly,
        "run",
        fake_app_catalog_run,
    )

    base_dir = tmp_path / "jobs"
    result = run_steam_cadence_job.run_job_with_evidence(
        run_steam_cadence_job.JOB_APP_CATALOG_WEEKLY,
        base_dir=base_dir,
        run_id="catalog-run",
        app_catalog_max_results=1000,
    )

    run_dir = base_dir / "app-catalog-weekly" / "catalog-run"
    assert result["status"] == "success"
    assert calls == [
        {
            "output_path": run_dir / "app_catalog.snapshot.jsonl",
            "checkpoint_path": run_dir / "app_catalog.checkpoint.json",
            "latest_summary_path": (
                run_steam_cadence_job.fetch_app_catalog_weekly
                .DEFAULT_APP_CATALOG_LATEST_SUMMARY_PATH
            ),
            "timeout_seconds": 10.0,
            "max_attempts": 4,
            "backoff_base_seconds": 0.5,
            "jitter_max_seconds": 0.3,
            "max_backoff_seconds": 8.0,
            "max_results": 1000,
            "meta_path": run_dir / "meta" / "steps" / "fetch_app_catalog_weekly.meta.json",
        }
    ]
