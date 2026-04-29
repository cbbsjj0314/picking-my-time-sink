"""Load Chzzk channel result artifacts into the category-channel fact table."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chzzk.normalize.category_lives import (
    ALLOWED_CATEGORY_TYPES,
    format_kst_iso,
    parse_timestamp,
    to_kst_datetime,
)
from steam.common.execution_meta import (
    build_execution_meta,
    default_meta_path,
    save_execution_meta,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_RESULT_PATH = Path("tmp/chzzk/channel-result-to-gold-summary.json")
DDL_PATH = "sql/postgres/016_fact_chzzk_category_channel_30m.sql"
RELATION_CHECK_SQL = "SELECT to_regclass('fact_chzzk_category_channel_30m')"

REQUIRED_FIELDS = (
    "bucket_time",
    "category_name",
    "category_type",
    "channel_id",
    "chzzk_category_id",
    "collected_at",
    "concurrent_user_count",
)

UPSERT_SQL = """
INSERT INTO fact_chzzk_category_channel_30m (
    chzzk_category_id,
    bucket_time,
    channel_id,
    category_type,
    category_name,
    concurrent_user_count,
    collected_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (chzzk_category_id, bucket_time, channel_id)
DO UPDATE SET
    category_type = EXCLUDED.category_type,
    category_name = EXCLUDED.category_name,
    concurrent_user_count = EXCLUDED.concurrent_user_count,
    collected_at = EXCLUDED.collected_at,
    ingested_at = NOW()
"""


class MissingChzzkCategoryChannelFactRelationError(RuntimeError):
    """Raised when the Chzzk category-channel fact table has not been created."""


@dataclass(frozen=True, slots=True)
class ChzzkCategoryChannelFactRow:
    """Observed Chzzk channel fact row for one category, bucket, and channel."""

    chzzk_category_id: str
    bucket_time: dt.datetime
    channel_id: str
    category_type: str
    category_name: str
    concurrent_user_count: int
    collected_at: dt.datetime


@dataclass(frozen=True, slots=True)
class SkippedRow:
    line_number: int
    reason: str


@dataclass(frozen=True, slots=True)
class ParsedChannelResultRows:
    input_row_count: int
    valid_rows: list[ChzzkCategoryChannelFactRow]
    skipped_rows: list[SkippedRow]


def configure_logging() -> None:
    """Use a compact logger format for normalization scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def require_psycopg() -> Any:
    """Import psycopg and fail fast when dependency is missing."""

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for Chzzk channel gold upsert") from exc
    return psycopg


def get_required_env(name: str) -> str:
    """Read required environment variable or raise clear error."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_pg_conninfo_from_env() -> str:
    """Build Postgres conninfo from environment variables."""

    host = get_required_env("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = get_required_env("POSTGRES_DB")
    user = get_required_env("POSTGRES_USER")
    password = get_required_env("POSTGRES_PASSWORD")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write deterministic JSON output for operator review."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_string(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if value is None:
        raise ValueError("missing_required_field")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("blank_required_field")
    return normalized


def _required_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if isinstance(value, bool):
        raise ValueError("invalid_integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_integer") from exc


def _parse_result_timestamp(row: Mapping[str, Any], field_name: str) -> dt.datetime:
    try:
        return to_kst_datetime(parse_timestamp(_required_string(row, field_name)))
    except ValueError as exc:
        raise ValueError("invalid_timestamp") from exc


def _validate_bucket_boundary(bucket_time: dt.datetime) -> None:
    kst_bucket = to_kst_datetime(bucket_time)
    if (
        kst_bucket.minute not in {0, 30}
        or kst_bucket.second != 0
        or kst_bucket.microsecond != 0
    ):
        raise ValueError("invalid_bucket_boundary")


def channel_result_row_to_fact_row(
    row: Mapping[str, Any],
) -> ChzzkCategoryChannelFactRow:
    """Validate one channel-result row and return a fact row."""

    for field_name in REQUIRED_FIELDS:
        if field_name not in row:
            raise ValueError("missing_required_field")

    bucket_time = _parse_result_timestamp(row, "bucket_time")
    _validate_bucket_boundary(bucket_time)
    collected_at = _parse_result_timestamp(row, "collected_at")

    category_type = _required_string(row, "category_type").upper()
    if category_type not in ALLOWED_CATEGORY_TYPES:
        raise ValueError("invalid_category_type")

    concurrent_user_count = _required_int(row, "concurrent_user_count")
    if concurrent_user_count < 0:
        raise ValueError("negative_concurrent_user_count")

    return ChzzkCategoryChannelFactRow(
        chzzk_category_id=_required_string(row, "chzzk_category_id"),
        bucket_time=bucket_time,
        channel_id=_required_string(row, "channel_id"),
        category_type=category_type,
        category_name=_required_string(row, "category_name"),
        concurrent_user_count=concurrent_user_count,
        collected_at=collected_at,
    )


def load_channel_result_rows(path: Path) -> ParsedChannelResultRows:
    """Read and validate channel-result JSONL rows without silent drops."""

    input_row_count = 0
    valid_rows: list[ChzzkCategoryChannelFactRow] = []
    skipped_rows: list[SkippedRow] = []
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"input_read_failed:{type(exc).__name__}") from exc

    with handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            input_row_count += 1
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                skipped_rows.append(SkippedRow(line_number, "invalid_json"))
                continue
            if not isinstance(parsed, Mapping):
                skipped_rows.append(SkippedRow(line_number, "row_must_be_object"))
                continue
            try:
                valid_rows.append(channel_result_row_to_fact_row(parsed))
            except ValueError as exc:
                reason = str(exc) or "invalid_row"
                skipped_rows.append(SkippedRow(line_number, reason))

    return ParsedChannelResultRows(
        input_row_count=input_row_count,
        valid_rows=valid_rows,
        skipped_rows=skipped_rows,
    )


def ensure_fact_relation_exists(cursor: Any) -> None:
    """Fail clearly when the provider-specific fact table has not been applied."""

    cursor.execute(RELATION_CHECK_SQL)
    relation_row = cursor.fetchone()
    relation = relation_row[0] if relation_row else None
    if relation is None:
        raise MissingChzzkCategoryChannelFactRelationError(
            f"fact_chzzk_category_channel_30m relation is missing; apply {DDL_PATH}"
        )


def upsert_fact_chzzk_category_channel_row(
    cursor: Any,
    *,
    row: ChzzkCategoryChannelFactRow,
) -> None:
    """Upsert one Chzzk category-channel fact row using the observed grain."""

    cursor.execute(
        UPSERT_SQL,
        (
            row.chzzk_category_id,
            row.bucket_time,
            row.channel_id,
            row.category_type,
            row.category_name,
            row.concurrent_user_count,
            row.collected_at,
        ),
    )


def process_channel_result_rows(
    rows: Sequence[ChzzkCategoryChannelFactRow],
    *,
    upsert_row: Callable[[ChzzkCategoryChannelFactRow], None],
) -> int:
    """Upsert already-validated category-channel fact rows through storage."""

    for row in rows:
        upsert_row(row)
    return len(rows)


def _skip_reason_counts(skipped_rows: Sequence[SkippedRow]) -> dict[str, int]:
    return dict(sorted(Counter(row.reason for row in skipped_rows).items()))


def build_summary(
    *,
    input_path: Path,
    parsed_rows: ParsedChannelResultRows,
    status: str,
    upsert_attempt_count: int,
    committed_row_count: int,
    failed_row_count: int,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Build sanitized load summary without row content or UGC-heavy values."""

    bucket_times = sorted(format_kst_iso(row.bucket_time) for row in parsed_rows.valid_rows)
    return {
        "bucket_max": bucket_times[-1] if bucket_times else None,
        "bucket_min": bucket_times[0] if bucket_times else None,
        "committed_row_count": committed_row_count,
        "failed_row_count": failed_row_count,
        "failure_reason": failure_reason,
        "input_basename": input_path.name,
        "input_row_count": parsed_rows.input_row_count,
        "skipped_row_count": len(parsed_rows.skipped_rows),
        "skipped_rows": [
            {"line_number": row.line_number, "reason": row.reason}
            for row in parsed_rows.skipped_rows
        ],
        "skip_reasons": _skip_reason_counts(parsed_rows.skipped_rows),
        "status": status,
        "unique_category_count": len({row.chzzk_category_id for row in parsed_rows.valid_rows}),
        "unique_channel_count": len({row.channel_id for row in parsed_rows.valid_rows}),
        "upsert_attempt_count": upsert_attempt_count,
        "valid_row_count": len(parsed_rows.valid_rows),
    }


def _sanitize_failure_reason(exc: Exception) -> str:
    if isinstance(exc, MissingChzzkCategoryChannelFactRelationError):
        return str(exc)
    if str(exc).startswith("input_read_failed:"):
        return str(exc)
    return f"database_write_failed:{type(exc).__name__}"


def _close_connection(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def upsert_valid_rows_in_transaction(
    rows: Sequence[ChzzkCategoryChannelFactRow],
) -> int:
    """Check the fact relation and upsert all rows in one transaction."""

    psycopg = require_psycopg()
    conninfo = build_pg_conninfo_from_env()
    conn = psycopg.connect(conninfo=conninfo)
    try:
        with conn.cursor() as cursor:
            ensure_fact_relation_exists(cursor)
            committed_candidate_count = process_channel_result_rows(
                rows,
                upsert_row=lambda row: upsert_fact_chzzk_category_channel_row(
                    cursor,
                    row=row,
                ),
            )
        conn.commit()
        return committed_candidate_count
    except Exception:
        conn.rollback()
        raise
    finally:
        _close_connection(conn)


def run(
    *,
    input_path: Path,
    result_path: Path | None = DEFAULT_RESULT_PATH,
    meta_path: Path | None = None,
) -> dict[str, Any]:
    """Load channel-result rows into Postgres and write a sanitized summary."""

    started_at_utc = utc_now_iso()
    resolved_meta_path = meta_path or default_meta_path(
        job_name="chzzk_channel_result_to_gold",
        started_at_utc=started_at_utc,
        base_dir=Path("tmp/chzzk/run-meta"),
    )

    success = False
    records_in = 0
    records_out = 0
    error_type: str | None = None
    error_message: str | None = None
    parsed_rows = ParsedChannelResultRows(
        input_row_count=0,
        valid_rows=[],
        skipped_rows=[],
    )

    try:
        parsed_rows = load_channel_result_rows(input_path)
        records_in = parsed_rows.input_row_count
        valid_row_count = len(parsed_rows.valid_rows)

        if valid_row_count == 0:
            summary = build_summary(
                input_path=input_path,
                parsed_rows=parsed_rows,
                status="success",
                upsert_attempt_count=0,
                committed_row_count=0,
                failed_row_count=0,
            )
            if result_path is not None:
                write_json(result_path, summary)
                LOGGER.info("Wrote Chzzk channel gold summary to %s", result_path)
            success = True
            return summary

        try:
            committed_row_count = upsert_valid_rows_in_transaction(parsed_rows.valid_rows)
        except Exception as exc:
            failure_reason = _sanitize_failure_reason(exc)
            summary = build_summary(
                input_path=input_path,
                parsed_rows=parsed_rows,
                status="failed",
                upsert_attempt_count=valid_row_count,
                committed_row_count=0,
                failed_row_count=valid_row_count,
                failure_reason=failure_reason,
            )
            if result_path is not None:
                write_json(result_path, summary)
                LOGGER.info("Wrote failed Chzzk channel gold summary to %s", result_path)
            raise

        summary = build_summary(
            input_path=input_path,
            parsed_rows=parsed_rows,
            status="success",
            upsert_attempt_count=valid_row_count,
            committed_row_count=committed_row_count,
            failed_row_count=0,
        )
        if result_path is not None:
            write_json(result_path, summary)
            LOGGER.info("Wrote Chzzk channel gold summary to %s", result_path)
        records_out = committed_row_count
        success = True
        return summary
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        error_type = type(exc).__name__
        error_message = _sanitize_failure_reason(exc)
        raise
    finally:
        execution_meta = build_execution_meta(
            job_name="chzzk_channel_result_to_gold",
            started_at_utc=started_at_utc,
            finished_at_utc=utc_now_iso(),
            success=success,
            http_status=None,
            retry_count=0,
            timeout_count=0,
            rate_limit_count=0,
            records_in=records_in,
            records_out=records_out,
            error_type=error_type,
            error_message=error_message,
        )
        save_execution_meta(execution_meta, resolved_meta_path)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for Chzzk channel artifact to gold loading."""

    parser = argparse.ArgumentParser(
        description=(
            "Load Chzzk channel-result JSONL into "
            "fact_chzzk_category_channel_30m"
        )
    )
    parser.add_argument("--input-path", type=Path, required=True)
    parser.add_argument("--result-path", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("--meta-path", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for Chzzk channel artifact to gold loading."""

    configure_logging()
    args = build_parser().parse_args(argv)
    run(
        input_path=args.input_path,
        result_path=args.result_path,
        meta_path=args.meta_path,
    )


if __name__ == "__main__":
    main()
