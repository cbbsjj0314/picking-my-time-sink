"""Recompute retained Steam CCU daily rollups from local gold artifacts with DuckDB."""

from __future__ import annotations

import argparse
import glob
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb

from steam.common.execution_meta import utc_now_iso
from steam.ingest.run_steam_cadence_job import DEFAULT_JOBS_BASE_DIR, JOB_CCU_30M

DEFAULT_OUTPUT_DIR = Path("tmp/steam/triage/retained_ccu_rollup")
DEFAULT_SUMMARY_PATH = DEFAULT_OUTPUT_DIR / "summary.json"
DEFAULT_RECOMPUTED_PATH = DEFAULT_OUTPUT_DIR / "recomputed_daily_rollup.jsonl"
DEFAULT_MISMATCH_PATH = DEFAULT_OUTPUT_DIR / "comparison_mismatches.jsonl"
SUMMARY_SCHEMA_VERSION = "1.0"
EXPECTED_BUCKETS_PER_DAY = 48
ROLLUP_FLOAT_TOLERANCE = 1e-9
COMPARISON_STATUS_SQL = f"""
case
    when recomputed_rollup.canonical_game_id is null then 'missing_from_recomputed'
    when latest_rollup_rows.canonical_game_id is null then 'missing_from_latest_rollup'
    when abs(recomputed_rollup.avg_ccu - latest_rollup_rows.avg_ccu) > {ROLLUP_FLOAT_TOLERANCE}
         and recomputed_rollup.peak_ccu <> latest_rollup_rows.peak_ccu then 'avg_and_peak_mismatch'
    when abs(recomputed_rollup.avg_ccu - latest_rollup_rows.avg_ccu) > {ROLLUP_FLOAT_TOLERANCE}
        then 'avg_mismatch'
    when recomputed_rollup.peak_ccu <> latest_rollup_rows.peak_ccu then 'peak_mismatch'
    else 'match'
end
"""


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


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return path


def _create_result_rows_table(
    connection: duckdb.DuckDBPyConnection,
    *,
    jobs_dir: Path,
) -> None:
    result_glob = f"{jobs_dir.as_posix()}/{JOB_CCU_30M}/*/result.json"
    if not _glob_has_matches(result_glob):
        connection.execute(
            """
            create or replace temp table result_rows as
            select
                cast(null as varchar) as run_id,
                cast(null as varchar) as finished_at_utc
            where false
            """
        )
        return

    connection.execute(
        f"""
        create or replace temp table result_rows as
        select
            regexp_extract(filename, '/([^/]+)/result\\.json$', 1) as run_id,
            finished_at_utc
        from read_json(
            {_sql_literal(result_glob)},
            filename=true,
            columns={{'finished_at_utc': 'VARCHAR'}}
        )
        """
    )


def _create_gold_rows_table(
    connection: duckdb.DuckDBPyConnection,
    *,
    jobs_dir: Path,
) -> None:
    gold_glob = f"{jobs_dir.as_posix()}/{JOB_CCU_30M}/*/ccu.gold-result.jsonl"
    if not _glob_has_matches(gold_glob):
        connection.execute(
            """
            create or replace temp table retained_gold_rows as
            select
                cast(null as varchar) as run_id,
                cast(null as bigint) as canonical_game_id,
                cast(null as varchar) as bucket_time,
                cast(null as bigint) as ccu,
                cast(false as boolean) as skipped
            where false
            """
        )
        return

    connection.execute(
        f"""
        create or replace temp table retained_gold_rows as
        select
            regexp_extract(filename, '/([^/]+)/[^/]+$', 1) as run_id,
            canonical_game_id,
            bucket_time,
            ccu,
            coalesce(skipped, false) as skipped
        from read_json(
            {_sql_literal(gold_glob)},
            format='newline_delimited',
            filename=true,
            columns={{
                'canonical_game_id': 'BIGINT',
                'bucket_time': 'VARCHAR',
                'ccu': 'BIGINT',
                'skipped': 'BOOLEAN'
            }}
        )
        """
    )


def _create_recomputed_rollup_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        create or replace temp table deduped_gold_rows as
        select
            canonical_game_id,
            bucket_time,
            ccu,
            run_id,
            finished_at_utc
        from (
            select
                retained_gold_rows.canonical_game_id,
                retained_gold_rows.bucket_time,
                retained_gold_rows.ccu,
                retained_gold_rows.run_id,
                result_rows.finished_at_utc,
                row_number() over (
                    partition by
                        retained_gold_rows.canonical_game_id,
                        retained_gold_rows.bucket_time
                    order by
                        result_rows.finished_at_utc desc nulls last,
                        retained_gold_rows.run_id desc
                ) as row_num
            from retained_gold_rows
            left join result_rows using (run_id)
            where retained_gold_rows.skipped = false
              and retained_gold_rows.ccu is not null
              and retained_gold_rows.bucket_time is not null
        )
        where row_num = 1
        """
    )
    connection.execute(
        f"""
        create or replace temp table recomputed_rollup as
        select
            canonical_game_id,
            cast(
                cast(bucket_time as TIMESTAMPTZ) AT TIME ZONE 'Asia/Seoul' as date
            ) as bucket_date,
            avg(ccu) as avg_ccu,
            max(ccu) as peak_ccu,
            count(*) as bucket_count,
            count(*) = {EXPECTED_BUCKETS_PER_DAY} as full_bucket_coverage
        from deduped_gold_rows
        group by 1, 2
        order by canonical_game_id, bucket_date
        """
    )


def _resolve_latest_rollup_path(
    *,
    jobs_dir: Path,
    compare_run_id: str | None,
) -> tuple[Path | None, str | None]:
    if compare_run_id:
        candidate = jobs_dir / JOB_CCU_30M / compare_run_id / "ccu.daily-rollup-result.jsonl"
        if not candidate.exists():
            raise ValueError(f"Missing retained rollup artifact for run_id={compare_run_id}")
        return candidate, compare_run_id

    rollup_paths = sorted((jobs_dir / JOB_CCU_30M).glob("*/ccu.daily-rollup-result.jsonl"))
    if not rollup_paths:
        return None, None

    latest_path = max(rollup_paths, key=lambda path: path.parent.name)
    return latest_path, latest_path.parent.name


def _create_latest_rollup_table(
    connection: duckdb.DuckDBPyConnection,
    *,
    latest_rollup_path: Path | None,
) -> None:
    if latest_rollup_path is None:
        connection.execute(
            """
            create or replace temp table latest_rollup_rows as
            select
                cast(null as bigint) as canonical_game_id,
                cast(null as date) as bucket_date,
                cast(null as double) as avg_ccu,
                cast(null as bigint) as peak_ccu
            where false
            """
        )
        return

    connection.execute(
        f"""
        create or replace temp table latest_rollup_rows as
        select
            canonical_game_id,
            cast(bucket_date as date) as bucket_date,
            avg_ccu,
            peak_ccu
        from read_json(
            {_sql_literal(latest_rollup_path.as_posix())},
            format='newline_delimited',
            columns={{
                'canonical_game_id': 'BIGINT',
                'bucket_date': 'VARCHAR',
                'avg_ccu': 'DOUBLE',
                'peak_ccu': 'BIGINT'
            }}
        )
        """
    )


def _fetch_recomputed_rows(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    raw_rows = connection.execute(
        """
        select
            canonical_game_id,
            bucket_date,
            avg_ccu,
            peak_ccu,
            bucket_count,
            full_bucket_coverage
        from recomputed_rollup
        order by canonical_game_id, bucket_date
        """
    ).fetchall()
    return [
        {
            "avg_ccu": avg_ccu,
            "bucket_count": bucket_count,
            "bucket_date": bucket_date.isoformat(),
            "canonical_game_id": canonical_game_id,
            "full_bucket_coverage": full_bucket_coverage,
            "peak_ccu": peak_ccu,
        }
        for (
            canonical_game_id,
            bucket_date,
            avg_ccu,
            peak_ccu,
            bucket_count,
            full_bucket_coverage,
        ) in raw_rows
    ]


def _fetch_mismatch_rows(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    raw_rows = connection.execute(
        f"""
        select
            coalesce(
                recomputed_rollup.canonical_game_id,
                latest_rollup_rows.canonical_game_id
            ) as canonical_game_id,
            coalesce(recomputed_rollup.bucket_date, latest_rollup_rows.bucket_date) as bucket_date,
            {COMPARISON_STATUS_SQL} as comparison_status,
            recomputed_rollup.avg_ccu as retained_avg_ccu,
            latest_rollup_rows.avg_ccu as latest_rollup_avg_ccu,
            recomputed_rollup.peak_ccu as retained_peak_ccu,
            latest_rollup_rows.peak_ccu as latest_rollup_peak_ccu,
            recomputed_rollup.bucket_count as retained_bucket_count,
            recomputed_rollup.full_bucket_coverage as retained_full_bucket_coverage
        from recomputed_rollup
        full outer join latest_rollup_rows using (canonical_game_id, bucket_date)
        where {COMPARISON_STATUS_SQL} <> 'match'
        order by canonical_game_id, bucket_date
        """
    ).fetchall()
    return [
        {
            "bucket_date": bucket_date.isoformat(),
            "canonical_game_id": canonical_game_id,
            "comparison_status": comparison_status,
            "latest_rollup_avg_ccu": latest_rollup_avg_ccu,
            "latest_rollup_peak_ccu": latest_rollup_peak_ccu,
            "retained_avg_ccu": retained_avg_ccu,
            "retained_bucket_count": retained_bucket_count,
            "retained_full_bucket_coverage": retained_full_bucket_coverage,
            "retained_peak_ccu": retained_peak_ccu,
        }
        for (
            canonical_game_id,
            bucket_date,
            comparison_status,
            retained_avg_ccu,
            latest_rollup_avg_ccu,
            retained_peak_ccu,
            latest_rollup_peak_ccu,
            retained_bucket_count,
            retained_full_bucket_coverage,
        ) in raw_rows
    ]


def _build_status_counts(rows: list[tuple[str, int]]) -> dict[str, int]:
    return {status: count for status, count in rows}


def build_summary(
    *,
    jobs_dir: Path = DEFAULT_JOBS_BASE_DIR,
    compare_run_id: str | None = None,
    recomputed_path: Path = DEFAULT_RECOMPUTED_PATH,
    mismatch_path: Path = DEFAULT_MISMATCH_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build retained-artifact CCU rollup summary and local comparison outputs."""

    latest_rollup_path, latest_rollup_run_id = _resolve_latest_rollup_path(
        jobs_dir=jobs_dir,
        compare_run_id=compare_run_id,
    )

    connection = duckdb.connect(database=":memory:")
    try:
        _create_result_rows_table(connection, jobs_dir=jobs_dir)
        _create_gold_rows_table(connection, jobs_dir=jobs_dir)
        _create_recomputed_rollup_tables(connection)
        _create_latest_rollup_table(connection, latest_rollup_path=latest_rollup_path)

        retained_gold_run_count, latest_gold_run_id, raw_bucket_row_count = connection.execute(
            """
            select
                count(distinct run_id) as retained_gold_run_count,
                max(run_id) as latest_gold_run_id,
                count(*) as raw_bucket_row_count
            from retained_gold_rows
            where skipped = false and ccu is not null and bucket_time is not null
            """
        ).fetchone()
        deduped_bucket_row_count = connection.execute(
            "select count(*) from deduped_gold_rows"
        ).fetchone()[0]
        (
            recomputed_row_count,
            full_coverage_row_count,
            partial_coverage_row_count,
        ) = connection.execute(
            """
            select
                count(*) as recomputed_row_count,
                count(*) filter (where full_bucket_coverage) as full_coverage_row_count,
                count(*) filter (where not full_bucket_coverage) as partial_coverage_row_count
            from recomputed_rollup
            """
        ).fetchone()
        bucket_date_start, bucket_date_end = connection.execute(
            """
            select
                min(bucket_date) as bucket_date_start,
                max(bucket_date) as bucket_date_end
            from recomputed_rollup
            """
        ).fetchone()

        latest_rollup_row_count = connection.execute(
            "select count(*) from latest_rollup_rows"
        ).fetchone()[0]
        comparison_status_counts = _build_status_counts(
            connection.execute(
                f"""
                select
                    {COMPARISON_STATUS_SQL} as comparison_status,
                    count(*) as row_count
                from recomputed_rollup
                full outer join latest_rollup_rows using (canonical_game_id, bucket_date)
                group by 1
                order by 1
                """
            ).fetchall()
        )

        recomputed_rows = _fetch_recomputed_rows(connection)
        mismatch_rows = _fetch_mismatch_rows(connection)
    finally:
        connection.close()

    exact_match_row_count = comparison_status_counts.get("match", 0)
    mismatch_row_count = sum(
        count for status, count in comparison_status_counts.items() if status != "match"
    )

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "jobs_dir": str(jobs_dir),
        "cadence": JOB_CCU_30M,
        "source": {
            "retained_gold_run_count": retained_gold_run_count,
            "latest_gold_run_id": latest_gold_run_id,
            "raw_bucket_row_count": raw_bucket_row_count,
            "deduped_bucket_row_count": deduped_bucket_row_count,
            "duplicate_bucket_row_count": raw_bucket_row_count - deduped_bucket_row_count,
            "bucket_date_start": bucket_date_start.isoformat() if bucket_date_start else None,
            "bucket_date_end": bucket_date_end.isoformat() if bucket_date_end else None,
        },
        "recomputed_rollup": {
            "row_count": recomputed_row_count,
            "full_bucket_coverage_row_count": full_coverage_row_count,
            "partial_bucket_coverage_row_count": partial_coverage_row_count,
            "output_path": str(recomputed_path),
        },
        "latest_rollup": (
            {
                "run_id": latest_rollup_run_id,
                "row_count": latest_rollup_row_count,
                "path": str(latest_rollup_path),
            }
            if latest_rollup_path is not None
            else None
        ),
        "comparison": {
            "compared": latest_rollup_path is not None,
            "exact_match_row_count": exact_match_row_count,
            "mismatch_row_count": mismatch_row_count,
            "status_counts": comparison_status_counts,
            "mismatch_output_path": str(mismatch_path),
        },
    }
    return summary, recomputed_rows, mismatch_rows


def run(
    *,
    jobs_dir: Path = DEFAULT_JOBS_BASE_DIR,
    compare_run_id: str | None = None,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    recomputed_path: Path = DEFAULT_RECOMPUTED_PATH,
    mismatch_path: Path = DEFAULT_MISMATCH_PATH,
) -> dict[str, Any]:
    """Recompute retained CCU daily rollups and persist local summary outputs."""

    summary, recomputed_rows, mismatch_rows = build_summary(
        jobs_dir=jobs_dir,
        compare_run_id=compare_run_id,
        recomputed_path=recomputed_path,
        mismatch_path=mismatch_path,
    )
    _write_jsonl(recomputed_path, recomputed_rows)
    _write_jsonl(mismatch_path, mismatch_rows)
    _write_json(summary_path, summary)
    return summary


def render_summary(summary: dict[str, Any]) -> str:
    """Render a short operator-readable retained-rollup summary."""

    source = summary.get("source", {})
    recomputed_rollup = summary.get("recomputed_rollup", {})
    latest_rollup = summary.get("latest_rollup") or {}
    comparison = summary.get("comparison", {})
    date_range = f"{source.get('bucket_date_start')}..{source.get('bucket_date_end')}"

    lines = [
        "ccu-30m retained gold: "
        f"runs={source.get('retained_gold_run_count', 0)} "
        f"latest_run={source.get('latest_gold_run_id') or 'missing'} "
        f"deduped_buckets={source.get('deduped_bucket_row_count', 0)} "
        f"duplicates_removed={source.get('duplicate_bucket_row_count', 0)} "
        f"date_range={date_range}",
        "recomputed daily rollup: "
        f"rows={recomputed_rollup.get('row_count', 0)} "
        f"full_coverage={recomputed_rollup.get('full_bucket_coverage_row_count', 0)} "
        f"partial_coverage={recomputed_rollup.get('partial_bucket_coverage_row_count', 0)}",
    ]
    if comparison.get("compared"):
        lines.append(
            "latest retained rollup: "
            f"run_id={latest_rollup.get('run_id')} rows={latest_rollup.get('row_count', 0)}"
        )
        lines.append(
            "comparison: "
            f"matches={comparison.get('exact_match_row_count', 0)} "
            f"mismatches={comparison.get('mismatch_row_count', 0)}"
        )
        status_counts = comparison.get("status_counts", {})
        mismatch_parts = [
            f"{status}={count}"
            for status, count in sorted(status_counts.items())
            if status != "match"
        ]
        if mismatch_parts:
            lines.append("  mismatch_statuses: " + ", ".join(mismatch_parts))
    else:
        lines.append("latest retained rollup: missing")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for retained-artifact CCU rollup recompute."""

    parser = argparse.ArgumentParser(
        description="Recompute retained Steam CCU daily rollups with DuckDB"
    )
    parser.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS_BASE_DIR)
    parser.add_argument("--compare-run-id", type=str, default=None)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--recomputed-path", type=Path, default=DEFAULT_RECOMPUTED_PATH)
    parser.add_argument("--mismatch-path", type=Path, default=DEFAULT_MISMATCH_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = run(
        jobs_dir=args.jobs_dir,
        compare_run_id=args.compare_run_id,
        summary_path=args.summary_path,
        recomputed_path=args.recomputed_path,
        mismatch_path=args.mismatch_path,
    )
    print(render_summary(summary))


if __name__ == "__main__":
    main()
