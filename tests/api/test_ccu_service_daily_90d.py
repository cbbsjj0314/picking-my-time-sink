from __future__ import annotations

import datetime as dt

from api.services import ccu_service


def test_recent_90d_sql_reads_daily_agg_with_fixed_kst_window_and_ordering() -> None:
    sql = ccu_service.GET_RECENT_90D_CCU_DAILY_BY_GAME_SQL.lower()

    assert "from agg_steam_ccu_daily" in sql
    assert "srv_game_latest_ccu" not in sql
    assert "at time zone 'asia/seoul'" in sql
    assert "::date - 89" in sql
    assert "bucket_date <=" in sql
    assert "order by bucket_date asc" in sql


def test_get_recent_90d_ccu_daily_by_game_returns_raw_rows_in_order(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()
    rows = [
        {
            "canonical_game_id": "77",
            "bucket_date": dt.date(2026, 3, 7),
            "avg_ccu": "120.5",
            "peak_ccu": "180",
        },
        {
            "canonical_game_id": 77,
            "bucket_date": dt.date(2026, 3, 8),
            "avg_ccu": 140,
            "peak_ccu": 210,
        },
    ]

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def execute(self, sql: str, params: tuple[int]) -> None:
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self) -> list[dict[str, object]]:
            return rows

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def cursor(self, row_factory=None) -> FakeCursor:
            captured["row_factory"] = row_factory
            return FakeCursor()

    class FakePsycopg:
        @staticmethod
        def connect(*, conninfo: str) -> FakeConnection:
            captured["conninfo"] = conninfo
            return FakeConnection()

    monkeypatch.setattr(ccu_service, "require_psycopg", lambda: (FakePsycopg, dict_row_sentinel))
    monkeypatch.setattr(ccu_service, "build_pg_conninfo_from_env", lambda: "fake-conninfo")

    result = ccu_service.get_recent_90d_ccu_daily_by_game(canonical_game_id=77)

    assert captured["conninfo"] == "fake-conninfo"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["sql"] == ccu_service.GET_RECENT_90D_CCU_DAILY_BY_GAME_SQL
    assert captured["params"] == (77,)
    assert result == [
        {
            "canonical_game_id": 77,
            "bucket_date": dt.date(2026, 3, 7),
            "avg_ccu": 120.5,
            "peak_ccu": 180,
        },
        {
            "canonical_game_id": 77,
            "bucket_date": dt.date(2026, 3, 8),
            "avg_ccu": 140.0,
            "peak_ccu": 210,
        },
    ]
    assert list(result[0]) == ["canonical_game_id", "bucket_date", "avg_ccu", "peak_ccu"]
    assert [row["bucket_date"] for row in result] == [
        dt.date(2026, 3, 7),
        dt.date(2026, 3, 8),
    ]


def test_get_recent_90d_ccu_daily_by_game_returns_empty_list(monkeypatch) -> None:
    dict_row_sentinel = object()

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def execute(self, sql: str, params: tuple[int]) -> None:
            del sql, params

        def fetchall(self) -> list[dict[str, object]]:
            return []

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def cursor(self, row_factory=None) -> FakeCursor:
            assert row_factory is dict_row_sentinel
            return FakeCursor()

    class FakePsycopg:
        @staticmethod
        def connect(*, conninfo: str) -> FakeConnection:
            assert conninfo == "fake-conninfo"
            return FakeConnection()

    monkeypatch.setattr(ccu_service, "require_psycopg", lambda: (FakePsycopg, dict_row_sentinel))
    monkeypatch.setattr(ccu_service, "build_pg_conninfo_from_env", lambda: "fake-conninfo")

    assert ccu_service.get_recent_90d_ccu_daily_by_game(canonical_game_id=77) == []
