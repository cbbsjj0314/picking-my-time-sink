"""Summarize retained local Steam job artifacts that repeatedly end in partial success."""

from __future__ import annotations

import argparse
import glob
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from steam.common.execution_meta import utc_now_iso
from steam.ingest.run_steam_cadence_job import DEFAULT_JOBS_BASE_DIR, JOB_CCU_30M, JOB_DAILY

DEFAULT_OUTPUT_PATH = Path("tmp/steam/triage/retained_partial_success_summary.json")
SUMMARY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ProbeCadence:
    """One retained-artifact partial-success contract."""

    job_name: str
    detail_filename: str
    reason_column: str
    triage_count_column: str


PROBE_CADENCES = (
    ProbeCadence(
        job_name=JOB_CCU_30M,
        detail_filename="ccu.silver.jsonl",
        reason_column="missing_reason",
        triage_count_column="missing_evidence_records",
    ),
    ProbeCadence(
        job_name=JOB_DAILY,
        detail_filename="reviews.silver.jsonl",
        reason_column="skipped_reason",
        triage_count_column="reviews_skipped_records",
    ),
)


def _sql_literal(path_or_glob: str) -> str:
    return "'" + path_or_glob.replace("'", "''") + "'"


def _glob_has_matches(path_glob: str) -> bool:
    return bool(glob.glob(path_glob))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _build_status_counts(rows: list[tuple[str, int]]) -> dict[str, int]:
    return {status: count for status, count in rows}


def _result_summary_for_cadence(
    connection: duckdb.DuckDBPyConnection,
    *,
    jobs_dir: Path,
    cadence: ProbeCadence,
) -> dict[str, Any]:
    result_glob = f"{jobs_dir.as_posix()}/{cadence.job_name}/*/result.json"
    if not _glob_has_matches(result_glob):
        return {
            "job_name": cadence.job_name,
            "retained_run_count": 0,
            "partial_success_run_count": 0,
            "status_counts": {},
            "latest_run": None,
            "latest_partial_run": None,
            "issue_rows": [],
        }

    connection.execute(
        f"""
        create or replace temp table result_rows as
        select
            regexp_extract(filename, '/([^/]+)/result\\.json$', 1) as run_id,
            finished_at_utc,
            coalesce(status, 'unknown') as status,
            coalesce(triage.partial_reason, '') as partial_reason,
            coalesce(triage.{cadence.triage_count_column}, 0) as triage_record_count
        from read_json_auto({ _sql_literal(result_glob) }, filename=true)
        """
    )

    retained_run_count, partial_success_run_count = connection.execute(
        """
        select
            count(*) as retained_run_count,
            count(*) filter (where status = 'partial_success') as partial_success_run_count
        from result_rows
        """
    ).fetchone()

    status_counts = _build_status_counts(
        connection.execute(
            "select status, count(*) as run_count from result_rows group by status order by status"
        ).fetchall()
    )

    latest_run_row = connection.execute(
        """
        select run_id, finished_at_utc, status
        from result_rows
        order by finished_at_utc desc, run_id desc
        limit 1
        """
    ).fetchone()
    latest_run = (
        {
            "run_id": latest_run_row[0],
            "finished_at_utc": latest_run_row[1].isoformat(),
            "status": latest_run_row[2],
        }
        if latest_run_row is not None
        else None
    )

    latest_partial_row = connection.execute(
        """
        select run_id, finished_at_utc, partial_reason, triage_record_count
        from result_rows
        where status = 'partial_success'
        order by finished_at_utc desc, run_id desc
        limit 1
        """
    ).fetchone()
    latest_partial_run = (
        {
            "run_id": latest_partial_row[0],
            "finished_at_utc": latest_partial_row[1].isoformat(),
            "partial_reason": latest_partial_row[2] or None,
            "triage_record_count": latest_partial_row[3],
        }
        if latest_partial_row is not None
        else None
    )

    detail_glob = f"{jobs_dir.as_posix()}/{cadence.job_name}/*/{cadence.detail_filename}"
    issue_rows: list[dict[str, Any]] = []
    if _glob_has_matches(detail_glob):
        connection.execute(
            f"""
            create or replace temp table detail_rows as
            select
                regexp_extract(filename, '/([^/]+)/[^/]+$', 1) as run_id,
                canonical_game_id,
                steam_appid,
                {cadence.reason_column} as issue_reason
            from read_json_auto(
                { _sql_literal(detail_glob) },
                format='newline_delimited',
                filename=true
            )
            where {cadence.reason_column} is not null
            """
        )
        raw_issue_rows = connection.execute(
            """
            select
                detail_rows.steam_appid,
                detail_rows.canonical_game_id,
                detail_rows.issue_reason,
                count(distinct detail_rows.run_id) as affected_partial_runs,
                max(result_rows.finished_at_utc) as latest_seen_at_utc,
                max_by(detail_rows.run_id, result_rows.finished_at_utc) as latest_run_id
            from detail_rows
            join result_rows using (run_id)
            where result_rows.status = 'partial_success'
            group by 1, 2, 3
            order by affected_partial_runs desc, steam_appid asc, canonical_game_id asc
            """
        ).fetchall()

        for (
            steam_appid,
            canonical_game_id,
            issue_reason,
            affected_partial_runs,
            latest_seen_at_utc,
            latest_run_id,
        ) in raw_issue_rows:
            share = (
                affected_partial_runs / partial_success_run_count
                if partial_success_run_count
                else 0.0
            )
            issue_rows.append(
                {
                    "steam_appid": steam_appid,
                    "canonical_game_id": canonical_game_id,
                    "issue_reason": issue_reason,
                    "affected_partial_runs": affected_partial_runs,
                    "partial_success_share": round(share, 4),
                    "chronic": partial_success_run_count > 0
                    and affected_partial_runs == partial_success_run_count,
                    "latest_run_id": latest_run_id,
                    "latest_seen_at_utc": latest_seen_at_utc.isoformat(),
                }
            )

    return {
        "job_name": cadence.job_name,
        "retained_run_count": retained_run_count,
        "partial_success_run_count": partial_success_run_count,
        "status_counts": status_counts,
        "latest_run": latest_run,
        "latest_partial_run": latest_partial_run,
        "issue_rows": issue_rows,
    }


def build_summary(*, jobs_dir: Path = DEFAULT_JOBS_BASE_DIR) -> dict[str, Any]:
    """Build one retained-artifact triage summary from local jobs evidence."""

    connection = duckdb.connect(database=":memory:")
    try:
        cadence_summaries = [
            _result_summary_for_cadence(connection, jobs_dir=jobs_dir, cadence=cadence)
            for cadence in PROBE_CADENCES
        ]
    finally:
        connection.close()

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "jobs_dir": str(jobs_dir),
        "cadences": cadence_summaries,
    }


def run(
    *,
    jobs_dir: Path = DEFAULT_JOBS_BASE_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Build and persist the retained-artifact partial-success summary."""

    summary = build_summary(jobs_dir=jobs_dir)
    _write_json(output_path, summary)
    return summary


def render_summary(summary: dict[str, Any]) -> str:
    """Render a short operator-readable summary for local terminal use."""

    lines: list[str] = []
    for cadence in summary.get("cadences", []):
        if not isinstance(cadence, dict):
            continue
        latest_run = cadence.get("latest_run") or {}
        latest_partial_run = cadence.get("latest_partial_run") or {}
        lines.append(
            f"{cadence.get('job_name')}: "
            f"{cadence.get('partial_success_run_count', 0)}/"
            f"{cadence.get('retained_run_count', 0)} partial_success runs, "
            f"latest_status={latest_run.get('status', 'missing')}"
        )
        if latest_partial_run:
            lines.append(
                f"  latest_partial={latest_partial_run.get('run_id')} "
                f"reason={latest_partial_run.get('partial_reason')} "
                f"triage_records={latest_partial_run.get('triage_record_count')}"
            )
        for issue_row in cadence.get("issue_rows", []):
            lines.append(
                f"  appid={issue_row['steam_appid']} "
                f"canonical_game_id={issue_row['canonical_game_id']} "
                f"reason={issue_row['issue_reason']} "
                f"runs={issue_row['affected_partial_runs']}/"
                f"{cadence.get('partial_success_run_count', 0)} "
                f"chronic={issue_row['chronic']}"
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for retained-artifact partial-success triage."""

    parser = argparse.ArgumentParser(
        description="Summarize retained local Steam partial-success artifacts with DuckDB"
    )
    parser.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS_BASE_DIR)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = run(
        jobs_dir=args.jobs_dir,
        output_path=args.output_path,
    )
    print(render_summary(summary))


if __name__ == "__main__":
    main()
