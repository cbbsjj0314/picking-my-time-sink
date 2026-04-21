from __future__ import annotations

import json
from pathlib import Path

from steam.ingest import retained_partial_success_probe


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def test_probe_summarizes_chronic_partial_success_from_retained_artifacts(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"

    write_json(
        jobs_dir / "ccu-30m" / "20260421T010000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T01:00:35Z",
            "status": "partial_success",
            "triage": {
                "partial_reason": "per_app_missing_evidence",
                "missing_evidence_records": 2,
            },
        },
    )
    write_json(
        jobs_dir / "ccu-30m" / "20260421T020000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T02:00:35Z",
            "status": "partial_success",
            "triage": {
                "partial_reason": "per_app_missing_evidence",
                "missing_evidence_records": 2,
            },
        },
    )
    write_json(
        jobs_dir / "ccu-30m" / "20260421T030000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T03:00:35Z",
            "status": "hard_failure",
            "triage": {},
        },
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T010000000000Z" / "ccu.silver.jsonl",
        [
            {
                "canonical_game_id": 13,
                "steam_appid": 2483190,
                "missing_reason": "http_404",
            },
            {
                "canonical_game_id": 72,
                "steam_appid": 1422450,
                "missing_reason": "http_404",
            },
        ],
    )
    write_jsonl(
        jobs_dir / "ccu-30m" / "20260421T020000000000Z" / "ccu.silver.jsonl",
        [
            {
                "canonical_game_id": 13,
                "steam_appid": 2483190,
                "missing_reason": "http_404",
            },
            {
                "canonical_game_id": 72,
                "steam_appid": 1422450,
                "missing_reason": "http_404",
            },
        ],
    )

    write_json(
        jobs_dir / "daily" / "20260420T180000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-20T18:20:35Z",
            "status": "partial_success",
            "triage": {
                "partial_reason": "reviews_skipped_evidence",
                "reviews_skipped_records": 3,
            },
        },
    )
    write_json(
        jobs_dir / "daily" / "20260421T180000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T18:20:35Z",
            "status": "partial_success",
            "triage": {
                "partial_reason": "reviews_skipped_evidence",
                "reviews_skipped_records": 3,
            },
        },
    )
    write_jsonl(
        jobs_dir / "daily" / "20260420T180000000000Z" / "reviews.silver.jsonl",
        [
            {
                "canonical_game_id": 13,
                "steam_appid": 2483190,
                "skipped_reason": "non_positive_total_reviews",
            },
            {
                "canonical_game_id": 72,
                "steam_appid": 1422450,
                "skipped_reason": "non_positive_total_reviews",
            },
            {
                "canonical_game_id": 114,
                "steam_appid": 4356080,
                "skipped_reason": "non_positive_total_reviews",
            },
        ],
    )
    write_jsonl(
        jobs_dir / "daily" / "20260421T180000000000Z" / "reviews.silver.jsonl",
        [
            {
                "canonical_game_id": 13,
                "steam_appid": 2483190,
                "skipped_reason": "non_positive_total_reviews",
            },
            {
                "canonical_game_id": 72,
                "steam_appid": 1422450,
                "skipped_reason": "non_positive_total_reviews",
            },
            {
                "canonical_game_id": 114,
                "steam_appid": 4356080,
                "skipped_reason": "non_positive_total_reviews",
            },
        ],
    )

    output_path = tmp_path / "retained-summary.json"
    summary = retained_partial_success_probe.run(
        jobs_dir=jobs_dir,
        output_path=output_path,
    )

    assert output_path.exists()
    saved_summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_summary["schema_version"] == "1.0"
    assert summary["jobs_dir"] == str(jobs_dir)

    ccu_summary = next(item for item in summary["cadences"] if item["job_name"] == "ccu-30m")
    assert ccu_summary["retained_run_count"] == 3
    assert ccu_summary["partial_success_run_count"] == 2
    assert ccu_summary["status_counts"] == {"hard_failure": 1, "partial_success": 2}
    assert ccu_summary["latest_run"] == {
        "run_id": "20260421T030000000000Z",
        "finished_at_utc": "2026-04-21T03:00:35",
        "status": "hard_failure",
    }
    assert ccu_summary["latest_partial_run"] == {
        "run_id": "20260421T020000000000Z",
        "finished_at_utc": "2026-04-21T02:00:35",
        "partial_reason": "per_app_missing_evidence",
        "triage_record_count": 2,
    }
    assert ccu_summary["issue_rows"] == [
        {
            "affected_partial_runs": 2,
            "canonical_game_id": 72,
            "chronic": True,
            "issue_reason": "http_404",
            "latest_run_id": "20260421T020000000000Z",
            "latest_seen_at_utc": "2026-04-21T02:00:35",
            "partial_success_share": 1.0,
            "steam_appid": 1422450,
        },
        {
            "affected_partial_runs": 2,
            "canonical_game_id": 13,
            "chronic": True,
            "issue_reason": "http_404",
            "latest_run_id": "20260421T020000000000Z",
            "latest_seen_at_utc": "2026-04-21T02:00:35",
            "partial_success_share": 1.0,
            "steam_appid": 2483190,
        },
    ]

    daily_summary = next(item for item in summary["cadences"] if item["job_name"] == "daily")
    assert daily_summary["retained_run_count"] == 2
    assert daily_summary["partial_success_run_count"] == 2
    assert daily_summary["latest_partial_run"] == {
        "run_id": "20260421T180000000000Z",
        "finished_at_utc": "2026-04-21T18:20:35",
        "partial_reason": "reviews_skipped_evidence",
        "triage_record_count": 3,
    }
    assert [row["steam_appid"] for row in daily_summary["issue_rows"]] == [
        1422450,
        2483190,
        4356080,
    ]
    assert all(row["chronic"] is True for row in daily_summary["issue_rows"])


def test_render_summary_reports_short_operator_view(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    write_json(
        jobs_dir / "daily" / "20260421T180000000000Z" / "result.json",
        {
            "finished_at_utc": "2026-04-21T18:20:35Z",
            "status": "partial_success",
            "triage": {
                "partial_reason": "reviews_skipped_evidence",
                "reviews_skipped_records": 1,
            },
        },
    )
    write_jsonl(
        jobs_dir / "daily" / "20260421T180000000000Z" / "reviews.silver.jsonl",
        [
            {
                "canonical_game_id": 114,
                "steam_appid": 4356080,
                "skipped_reason": "non_positive_total_reviews",
            }
        ],
    )

    rendered = retained_partial_success_probe.render_summary(
        retained_partial_success_probe.build_summary(jobs_dir=jobs_dir)
    )

    assert "daily: 1/1 partial_success runs" in rendered
    assert "appid=4356080" in rendered
