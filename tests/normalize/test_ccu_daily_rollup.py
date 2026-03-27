from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from typing import Any

import pytest

from steam.normalize import gold_to_agg_ccu_daily
from steam.normalize.gold_to_agg_ccu_daily import (
    bucket_date_from_bucket_time,
    parse_bucket_time,
    process_fact_rows,
)


class FakeAggStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str], dict[str, Any]] = {}

    def upsert(
        self,
        canonical_game_id: int,
        bucket_date: dt.date,
        avg_ccu: float,
        peak_ccu: int,
    ) -> None:
        key = (canonical_game_id, bucket_date.isoformat())
        self.rows[key] = {
            "avg_ccu": avg_ccu,
            "peak_ccu": peak_ccu,
        }

    def delete_missing_rows(self, current_keys: set[tuple[int, dt.date]]) -> None:
        allowed_keys = {
            (canonical_game_id, bucket_date.isoformat())
            for canonical_game_id, bucket_date in current_keys
        }
        self.rows = {
            key: value
            for key, value in self.rows.items()
            if key in allowed_keys
        }


def test_bucket_date_from_bucket_time_uses_kst_day() -> None:
    bucket_time = parse_bucket_time("2026-03-07T15:30:00+00:00")

    assert bucket_date_from_bucket_time(bucket_time).isoformat() == "2026-03-08"


def test_process_fact_rows_averages_existing_rows_only_without_full_day_assumption() -> None:
    store = FakeAggStore()
    fact_rows: list[Mapping[str, Any]] = [
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-08T00:00:00+09:00",
            "ccu": 120,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-08T00:30:00+09:00",
            "ccu": 180,
        },
    ]

    results = process_fact_rows(fact_rows, upsert_row=store.upsert)

    assert results == [
        {
            "avg_ccu": 150.0,
            "bucket_date": "2026-03-08",
            "canonical_game_id": 1,
            "peak_ccu": 180,
        }
    ]
    assert store.rows[(1, "2026-03-08")]["avg_ccu"] == pytest.approx(150.0)
    assert store.rows[(1, "2026-03-08")]["avg_ccu"] != pytest.approx(6.25)


def test_process_fact_rows_aggregates_by_day_and_sorts_results() -> None:
    store = FakeAggStore()
    fact_rows: list[Mapping[str, Any]] = [
        {
            "canonical_game_id": 2,
            "bucket_time": "2026-03-08T00:30:00+09:00",
            "ccu": 80,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T23:30:00+09:00",
            "ccu": 240,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T00:00:00+09:00",
            "ccu": 120,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T00:30:00+09:00",
            "ccu": 180,
        },
    ]

    results = process_fact_rows(fact_rows, upsert_row=store.upsert)

    assert results == [
        {
            "avg_ccu": 180.0,
            "bucket_date": "2026-03-07",
            "canonical_game_id": 1,
            "peak_ccu": 240,
        },
        {
            "avg_ccu": 80.0,
            "bucket_date": "2026-03-08",
            "canonical_game_id": 2,
            "peak_ccu": 80,
        },
    ]


def test_process_fact_rows_includes_partial_current_day_when_rows_exist() -> None:
    store = FakeAggStore()
    fact_rows: list[Mapping[str, Any]] = [
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-08T00:00:00+09:00",
            "ccu": 90,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-08T00:30:00+09:00",
            "ccu": 150,
        },
    ]

    results = process_fact_rows(fact_rows, upsert_row=store.upsert)

    assert results == [
        {
            "avg_ccu": 120.0,
            "bucket_date": "2026-03-08",
            "canonical_game_id": 1,
            "peak_ccu": 150,
        }
    ]
    assert (1, "2026-03-08") in store.rows


def test_process_fact_rows_is_idempotent_for_same_input() -> None:
    store = FakeAggStore()
    fact_rows: list[Mapping[str, Any]] = [
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T00:00:00+09:00",
            "ccu": 100,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T00:30:00+09:00",
            "ccu": 200,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-08T00:00:00+09:00",
            "ccu": 300,
        },
    ]

    first_results = process_fact_rows(fact_rows, upsert_row=store.upsert)
    second_results = process_fact_rows(fact_rows, upsert_row=store.upsert)

    assert len(store.rows) == 2
    assert first_results == second_results
    assert store.rows[(1, "2026-03-07")]["avg_ccu"] == pytest.approx(150.0)
    assert store.rows[(1, "2026-03-08")]["peak_ccu"] == 300


def test_process_fact_rows_deletes_stale_rows_for_missing_source_day() -> None:
    store = FakeAggStore()
    store.rows = {
        (1, "2026-03-06"): {
            "avg_ccu": 90.0,
            "peak_ccu": 120,
        },
        (1, "2026-03-07"): {
            "avg_ccu": 50.0,
            "peak_ccu": 50,
        },
    }
    fact_rows: list[Mapping[str, Any]] = [
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T00:00:00+09:00",
            "ccu": 100,
        },
        {
            "canonical_game_id": 1,
            "bucket_time": "2026-03-07T00:30:00+09:00",
            "ccu": 200,
        },
    ]

    results = process_fact_rows(
        fact_rows,
        upsert_row=store.upsert,
        delete_missing_rows=store.delete_missing_rows,
    )

    assert results == [
        {
            "avg_ccu": 150.0,
            "bucket_date": "2026-03-07",
            "canonical_game_id": 1,
            "peak_ccu": 200,
        }
    ]
    assert (1, "2026-03-06") not in store.rows
    assert store.rows[(1, "2026-03-07")]["avg_ccu"] == pytest.approx(150.0)


def test_run_writes_result_path_and_meta_path_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    deleted_keys: list[tuple[int, str]] = []
    upserted_rows: list[tuple[int, str, float, int]] = []

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self._cursor = FakeCursor()

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def cursor(self) -> FakeCursor:
            return self._cursor

    class FakePsycopg:
        @staticmethod
        def connect(*, conninfo: str) -> FakeConnection:
            assert conninfo == "fake-conninfo"
            return FakeConnection()

    monkeypatch.setattr(gold_to_agg_ccu_daily, "require_psycopg", lambda: FakePsycopg)
    monkeypatch.setattr(
        gold_to_agg_ccu_daily,
        "build_pg_conninfo_from_env",
        lambda: "fake-conninfo",
    )
    monkeypatch.setattr(
        gold_to_agg_ccu_daily,
        "load_fact_rows",
        lambda cursor: [
            {
                "canonical_game_id": 1,
                "bucket_time": "2026-03-07T00:00:00+09:00",
                "ccu": 100,
            },
            {
                "canonical_game_id": 1,
                "bucket_time": "2026-03-07T00:30:00+09:00",
                "ccu": 200,
            },
        ],
    )
    monkeypatch.setattr(
        gold_to_agg_ccu_daily,
        "load_agg_keys",
        lambda cursor: {
            (1, dt.date(2026, 3, 6)),
            (1, dt.date(2026, 3, 7)),
        },
    )
    monkeypatch.setattr(
        gold_to_agg_ccu_daily,
        "delete_agg_ccu_daily_row",
        lambda cursor, *, canonical_game_id, bucket_date: deleted_keys.append(
            (canonical_game_id, bucket_date.isoformat())
        ),
    )
    monkeypatch.setattr(
        gold_to_agg_ccu_daily,
        "upsert_agg_ccu_daily_row",
        lambda cursor, *, canonical_game_id, bucket_date, avg_ccu, peak_ccu: upserted_rows.append(
            (canonical_game_id, bucket_date.isoformat(), avg_ccu, peak_ccu)
        ),
    )

    result_path = tmp_path / "result.jsonl"
    meta_path = tmp_path / "meta.json"

    results = gold_to_agg_ccu_daily.run(
        result_path=result_path,
        meta_path=meta_path,
    )

    assert results == [
        {
            "avg_ccu": 150.0,
            "bucket_date": "2026-03-07",
            "canonical_game_id": 1,
            "peak_ccu": 200,
        }
    ]
    assert deleted_keys == [(1, "2026-03-06")]
    assert upserted_rows == [(1, "2026-03-07", 150.0, 200)]
    assert json.loads(result_path.read_text(encoding="utf-8").strip()) == results[0]

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["job_name"] == "gold_to_agg_ccu_daily"
    assert meta["records_in"] == 2
    assert meta["records_out"] == 1
    assert meta["success"] is True


def test_build_pg_conninfo_from_env_requires_postgres_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.setenv("POSTGRES_DB", "steam")
    monkeypatch.setenv("POSTGRES_USER", "tester")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")

    with pytest.raises(RuntimeError, match="Missing required environment variable: POSTGRES_HOST"):
        gold_to_agg_ccu_daily.build_pg_conninfo_from_env()
