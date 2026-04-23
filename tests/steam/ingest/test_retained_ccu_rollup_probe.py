from __future__ import annotations

import json
from pathlib import Path

from steam.ingest import retained_ccu_rollup_probe


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_probe_recomputes_latest_retained_rollup_and_dedupes_bucket_rows(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"

    write_json(
        jobs_dir / "ccu-30m" / "20260421T000000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T00:00:35Z",
            "status": "partial_success",
        },
    )
    write_json(
        jobs_dir / "ccu-30m" / "20260421T000500000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T00:05:35Z",
            "status": "partial_success",
        },
    )
    write_json(
        jobs_dir / "ccu-30m" / "20260421T003000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T00:30:35Z",
            "status": "partial_success",
        },
    )

    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T000000000000Z" / "ccu.gold-result.jsonl",
        [
            {
                "bucket_time": "2026-04-21T00:00:00+09:00",
                "canonical_game_id": 1,
                "ccu": 100,
                "skipped": False,
            }
        ],
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T000500000000Z" / "ccu.gold-result.jsonl",
        [
            {
                "bucket_time": "2026-04-21T00:00:00+09:00",
                "canonical_game_id": 1,
                "ccu": 130,
                "skipped": False,
            }
        ],
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T003000000000Z" / "ccu.gold-result.jsonl",
        [
            {
                "bucket_time": "2026-04-21T00:30:00+09:00",
                "canonical_game_id": 1,
                "ccu": 170,
                "skipped": False,
            }
        ],
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T003000000000Z" / "ccu.daily-rollup-result.jsonl",
        [
            {
                "avg_ccu": 150.0,
                "bucket_date": "2026-04-21",
                "canonical_game_id": 1,
                "peak_ccu": 170,
            }
        ],
    )

    summary_path = tmp_path / "summary.json"
    recomputed_path = tmp_path / "recomputed.jsonl"
    mismatch_path = tmp_path / "mismatches.jsonl"

    summary = retained_ccu_rollup_probe.run(
        jobs_dir=jobs_dir,
        summary_path=summary_path,
        recomputed_path=recomputed_path,
        mismatch_path=mismatch_path,
    )

    assert summary["source"] == {
        "retained_gold_run_count": 3,
        "latest_gold_run_id": "20260421T003000000000Z",
        "raw_bucket_row_count": 3,
        "deduped_bucket_row_count": 2,
        "duplicate_bucket_row_count": 1,
        "bucket_date_start": "2026-04-21",
        "bucket_date_end": "2026-04-21",
    }
    assert summary["recomputed_rollup"] == {
        "row_count": 1,
        "full_bucket_coverage_row_count": 0,
        "partial_bucket_coverage_row_count": 1,
        "output_path": str(recomputed_path),
    }
    assert summary["latest_rollup"] == {
        "run_id": "20260421T003000000000Z",
        "row_count": 1,
        "path": str(
            jobs_dir
            / "ccu-30m"
            / "20260421T003000000000Z"
            / "ccu.daily-rollup-result.jsonl"
        ),
    }
    assert summary["comparison"] == {
        "compared": True,
        "exact_match_row_count": 1,
        "mismatch_row_count": 0,
        "status_counts": {"match": 1},
        "mismatch_output_path": str(mismatch_path),
    }

    saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert saved_summary["schema_version"] == "1.0"
    assert load_jsonl(recomputed_path) == [
        {
            "avg_ccu": 150.0,
            "bucket_count": 2,
            "bucket_date": "2026-04-21",
            "canonical_game_id": 1,
            "full_bucket_coverage": False,
            "peak_ccu": 170,
        }
    ]
    assert load_jsonl(mismatch_path) == []


def test_probe_reports_rollup_mismatches_and_missing_rows(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"

    write_json(
        jobs_dir / "ccu-30m" / "20260421T000000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T00:00:35Z",
            "status": "partial_success",
        },
    )
    write_json(
        jobs_dir / "ccu-30m" / "20260421T003000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T00:30:35Z",
            "status": "partial_success",
        },
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T000000000000Z" / "ccu.gold-result.jsonl",
        [
            {
                "bucket_time": "2026-04-21T00:00:00+09:00",
                "canonical_game_id": 1,
                "ccu": 100,
                "skipped": False,
            }
        ],
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T003000000000Z" / "ccu.gold-result.jsonl",
        [
            {
                "bucket_time": "2026-04-21T00:30:00+09:00",
                "canonical_game_id": 1,
                "ccu": 200,
                "skipped": False,
            }
        ],
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T003000000000Z" / "ccu.daily-rollup-result.jsonl",
        [
            {
                "avg_ccu": 140.0,
                "bucket_date": "2026-04-21",
                "canonical_game_id": 1,
                "peak_ccu": 200,
            },
            {
                "avg_ccu": 50.0,
                "bucket_date": "2026-04-21",
                "canonical_game_id": 2,
                "peak_ccu": 50,
            },
        ],
    )

    summary_path = tmp_path / "summary.json"
    recomputed_path = tmp_path / "recomputed.jsonl"
    mismatch_path = tmp_path / "mismatches.jsonl"

    summary = retained_ccu_rollup_probe.run(
        jobs_dir=jobs_dir,
        summary_path=summary_path,
        recomputed_path=recomputed_path,
        mismatch_path=mismatch_path,
    )

    assert summary["comparison"] == {
        "compared": True,
        "exact_match_row_count": 0,
        "mismatch_row_count": 2,
        "status_counts": {
            "avg_mismatch": 1,
            "missing_from_recomputed": 1,
        },
        "mismatch_output_path": str(mismatch_path),
    }
    assert load_jsonl(mismatch_path) == [
        {
            "bucket_date": "2026-04-21",
            "canonical_game_id": 1,
            "comparison_status": "avg_mismatch",
            "latest_rollup_avg_ccu": 140.0,
            "latest_rollup_peak_ccu": 200,
            "retained_avg_ccu": 150.0,
            "retained_bucket_count": 2,
            "retained_full_bucket_coverage": False,
            "retained_peak_ccu": 200,
        },
        {
            "bucket_date": "2026-04-21",
            "canonical_game_id": 2,
            "comparison_status": "missing_from_recomputed",
            "latest_rollup_avg_ccu": 50.0,
            "latest_rollup_peak_ccu": 50,
            "retained_avg_ccu": None,
            "retained_bucket_count": None,
            "retained_full_bucket_coverage": None,
            "retained_peak_ccu": None,
        },
    ]


def test_probe_handles_empty_retained_artifacts(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    summary = retained_ccu_rollup_probe.run(
        jobs_dir=jobs_dir,
        summary_path=tmp_path / "summary.json",
        recomputed_path=tmp_path / "recomputed.jsonl",
        mismatch_path=tmp_path / "mismatches.jsonl",
    )

    assert summary["source"] == {
        "retained_gold_run_count": 0,
        "latest_gold_run_id": None,
        "raw_bucket_row_count": 0,
        "deduped_bucket_row_count": 0,
        "duplicate_bucket_row_count": 0,
        "bucket_date_start": None,
        "bucket_date_end": None,
    }
    assert summary["latest_rollup"] is None
    assert summary["comparison"]["compared"] is False

    rendered = retained_ccu_rollup_probe.render_summary(summary)
    assert "runs=0" in rendered
    assert "latest retained rollup: missing" in rendered
