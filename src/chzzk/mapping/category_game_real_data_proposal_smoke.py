"""Explicit, aggregate-only smoke; real database execution requires Human Gate approval."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import psycopg
from psycopg.conninfo import make_conninfo

from chzzk.mapping.category_game_candidate_generation import (
    SyntheticChzzkCategoryInput,
    SyntheticSteamGameInput,
    build_category_game_candidate_dry_run_proposals,
)

OBSERVED_SQL = """
SELECT DISTINCT ON (chzzk_category_id)
    chzzk_category_id, category_name, category_type, bucket_time AS latest_bucket_time
FROM fact_chzzk_category_30m
ORDER BY chzzk_category_id, bucket_time DESC, collected_at DESC, ingested_at DESC
"""
GAMES_SQL = """
SELECT canonical_game_id, canonical_name FROM dim_game ORDER BY canonical_game_id ASC
"""
TRUSTED_SQL = """
SELECT chzzk_category_id FROM srv_chzzk_category_game_mapping ORDER BY chzzk_category_id ASC
"""
TRANSACTION_SQL = """
SELECT current_setting('transaction_read_only'), current_setting('transaction_isolation')
"""
NO_WRITES = {
    "db_write_performed": False,
    "candidate_insert_performed": False,
    "trusted_mapping_mutation_performed": False,
}


class SmokeFailure(Exception):
    """Carry only public-safe failure categories and counts."""

    def __init__(self, reason: str, invalid_count: int = 0):
        self.reason = reason
        self.invalid_count = invalid_count
        super().__init__(reason)


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _summarize(observed: list, games: list, trusted: list) -> dict[str, object]:
    invalid_count = 0
    category_ids: set[str] = set()
    game_ids: set[int] = set()
    trusted_ids: set[str] = set()
    for row in observed:
        valid = (
            len(row) == 4
            and _nonblank(row[0])
            and _nonblank(row[1])
            and (row[2] is None or isinstance(row[2], str))
            and isinstance(row[3], datetime)
            and row[3].utcoffset() is not None
            and row[0] not in category_ids
        )
        if valid:
            category_ids.add(row[0])
        else:
            invalid_count += 1
    for row in games:
        valid = (
            len(row) == 2
            and isinstance(row[0], int)
            and not isinstance(row[0], bool)
            and row[0] > 0
            and _nonblank(row[1])
            and row[0] not in game_ids
        )
        if valid:
            game_ids.add(row[0])
        else:
            invalid_count += 1
    for row in trusted:
        if len(row) == 1 and _nonblank(row[0]) and row[0] not in trusted_ids:
            trusted_ids.add(row[0])
        else:
            invalid_count += 1
    if invalid_count:
        raise SmokeFailure("invalid_input", invalid_count)

    # Membership uses the persisted identity, before the builder normalizes its inputs.
    untrusted = [row for row in observed if row[0] not in trusted_ids]
    proposals = build_category_game_candidate_dry_run_proposals(
        categories=[SyntheticChzzkCategoryInput(*row[:3]) for row in untrusted],
        games=[SyntheticSteamGameInput(*row) for row in games],
        alias_hints=None,
    )
    candidate = sum(p.status == "candidate" and p.match_count == 1 for p in proposals)
    no_match = sum(p.status == "unresolved" and p.match_count == 0 for p in proposals)
    ambiguous = sum(p.status == "unresolved" and p.match_count >= 2 for p in proposals)
    already_trusted = len(observed) - len(untrusted)
    if (
        len(proposals) != len(untrusted)
        or candidate + no_match + ambiguous != len(untrusted)
        or already_trusted + candidate + no_match + ambiguous != len(observed)
    ):
        raise SmokeFailure("partition_invariant_failed")
    latest = max((row[3] for row in observed), default=None)
    return {
        "result_status": "success",
        "observed_input_category_count": len(observed),
        "canonical_game_input_count": len(games),
        "already_trusted_category_count": already_trusted,
        "not_currently_trusted_category_count": len(untrusted),
        "candidate_count": candidate,
        "unresolved_no_match_count": no_match,
        "unresolved_ambiguous_count": ambiguous,
        "latest_observed_evidence_timestamp": (
            latest.astimezone(UTC).isoformat() if latest is not None else None
        ),
        **NO_WRITES,
    }


def run_smoke(*, environ: Mapping[str, str] | None = None) -> dict[str, object]:
    """Read one snapshot. Call only against a separately Human-authorized environment."""
    source = os.environ if environ is None else environ
    stage = "database_access_failed"
    try:
        required = ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
        if any(not source.get(key) for key in required):
            raise SmokeFailure("database_configuration_unavailable")
        conninfo = make_conninfo(
            host=source["POSTGRES_HOST"],
            port=source.get("POSTGRES_PORT", "5432"),
            dbname=source["POSTGRES_DB"],
            user=source["POSTGRES_USER"],
            password=source["POSTGRES_PASSWORD"],
            connect_timeout=10,
        )
        with psycopg.connect(conninfo=conninfo, autocommit=False) as connection:
            stage = "transaction_condition_failed"
            connection.read_only = True
            connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(TRANSACTION_SQL)
                    if cursor.fetchone() != ("on", "repeatable read"):
                        raise SmokeFailure("transaction_condition_failed")
                    stage = "approved_source_unavailable"
                    cursor.execute(OBSERVED_SQL)
                    observed = cursor.fetchall()
                    cursor.execute(GAMES_SQL)
                    games = cursor.fetchall()
                    cursor.execute(TRUSTED_SQL)
                    trusted = cursor.fetchall()
                    stage = "invalid_input"
                    summary = _summarize(observed, games, trusted)
                stage = "transaction_condition_failed"
        # Never publish success before transaction and connection exit succeed.
        return summary
    except SmokeFailure as exc:
        return {
            "result_status": "failed",
            "failure_reason_category": exc.reason,
            "invalid_input_count": exc.invalid_count,
            **NO_WRITES,
        }
    except Exception:
        # Driver exceptions can contain credentials, host details and raw row values.
        return {"result_status": "failed", "failure_reason_category": stage, **NO_WRITES}


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        result = {
            "result_status": "blocked",
            "failure_reason_category": "unsupported_arguments",
            **NO_WRITES,
        }
    else:
        result = run_smoke()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
