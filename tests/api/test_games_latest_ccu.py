from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.games import router as games_router
from api.services import ccu_service

KST = ZoneInfo("Asia/Seoul")


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(games_router)
    return TestClient(app)


def sample_response_record(canonical_game_id: int) -> dict[str, object]:
    return {
        "canonical_game_id": canonical_game_id,
        "canonical_name": f"game-{canonical_game_id}",
        "bucket_time": dt.datetime(2026, 3, 7, 12, 30, tzinfo=KST),
        "ccu": 120,
        "delta_ccu_abs": 20,
        "delta_ccu_pct": 20.0,
        "missing_flag": False,
    }


def sample_daily_90d_response_record(
    canonical_game_id: int,
    bucket_date: dt.date,
) -> dict[str, object]:
    return {
        "canonical_game_id": canonical_game_id,
        "bucket_date": bucket_date,
        "avg_ccu": 120.5,
        "peak_ccu": 180,
    }


def test_list_games_latest_ccu_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_list_latest_ccu(limit: int = 50, window: str = "1d") -> list[dict[str, object]]:
        captured["limit"] = limit
        captured["window"] = window
        return [sample_response_record(1), sample_response_record(2)]

    monkeypatch.setattr(ccu_service, "list_latest_ccu", fake_list_latest_ccu)

    client = build_test_client()
    response = client.get("/games/ccu/latest", params={"limit": 25, "window": "30d"})

    assert response.status_code == 200
    assert captured["limit"] == 25
    assert captured["window"] == "30d"
    body = response.json()
    assert len(body) == 2
    assert body[0]["canonical_game_id"] == 1
    assert body[0]["ccu"] == 120


def test_get_game_latest_ccu_returns_404_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(ccu_service, "get_latest_ccu_by_game", lambda canonical_game_id: None)

    client = build_test_client()
    response = client.get("/games/999/ccu/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "Game latest CCU not found"


def test_get_game_latest_ccu_returns_row(monkeypatch) -> None:
    monkeypatch.setattr(
        ccu_service,
        "get_latest_ccu_by_game",
        lambda canonical_game_id: sample_response_record(canonical_game_id),
    )

    client = build_test_client()
    response = client.get("/games/123/ccu/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_game_id"] == 123
    # Locks current behavior; UTC-only wire format needs deliberate runtime change and test update.
    assert body["bucket_time"] == "2026-03-07T12:30:00+09:00"
    assert body["delta_ccu_abs"] == 20
    assert body["missing_flag"] is False


def test_get_game_daily_90d_ccu_returns_rows_in_ascending_order(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_get_recent_90d_ccu_daily_by_game(canonical_game_id: int) -> list[dict[str, object]]:
        captured["canonical_game_id"] = canonical_game_id
        return [
            sample_daily_90d_response_record(canonical_game_id, dt.date(2026, 3, 7)),
            sample_daily_90d_response_record(canonical_game_id, dt.date(2026, 3, 8)),
        ]

    monkeypatch.setattr(
        ccu_service,
        "get_recent_90d_ccu_daily_by_game",
        fake_get_recent_90d_ccu_daily_by_game,
    )

    client = build_test_client()
    response = client.get("/games/123/ccu/daily-90d")

    assert response.status_code == 200
    assert captured["canonical_game_id"] == 123
    body = response.json()
    assert body == [
        {
            "canonical_game_id": 123,
            "bucket_date": "2026-03-07",
            "avg_ccu": 120.5,
            "peak_ccu": 180,
        },
        {
            "canonical_game_id": 123,
            "bucket_date": "2026-03-08",
            "avg_ccu": 120.5,
            "peak_ccu": 180,
        },
    ]


def test_get_game_daily_90d_ccu_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        ccu_service,
        "get_recent_90d_ccu_daily_by_game",
        lambda canonical_game_id: [],
    )

    client = build_test_client()
    response = client.get("/games/999/ccu/daily-90d")

    assert response.status_code == 200
    assert response.json() == []


def test_service_sql_uses_serving_view_only() -> None:
    single_sql = ccu_service.GET_LATEST_BY_GAME_SQL.lower()
    list_sql = ccu_service.LIST_LATEST_SQL.lower()
    window_sql = ccu_service.LIST_LATEST_WINDOW_SQL.lower()
    history_sql = ccu_service.GET_RECENT_FIXED_DAILY_CCU_HISTORY_BY_GAME_SQL.lower()

    assert "from srv_game_latest_ccu" in single_sql
    assert "from srv_game_latest_ccu" in list_sql
    assert "order by latest_ccu desc" in list_sql
    assert "fact_steam_ccu_30m" not in single_sql
    assert "fact_steam_ccu_30m" not in list_sql
    assert "from agg_steam_ccu_daily" in window_sql
    assert "join srv_game_latest_ccu" in window_sql
    assert "fact_steam_ccu_30m" not in window_sql
    assert "max(bucket_date)" in window_sql
    assert "count(*) = %s" in window_sql
    assert "from agg_steam_ccu_daily" in history_sql
    assert "fact_steam_ccu_30m" not in history_sql


def test_to_response_record_missing_prev_sets_flag_and_pct_none() -> None:
    row = {
        "canonical_game_id": 77,
        "canonical_name": "example",
        "bucket_time": dt.datetime(2026, 3, 7, 12, 0, tzinfo=KST),
        "ccu": 50,
        "delta_ccu_abs": None,
        "prev_day_same_bucket_ccu": None,
    }

    mapped = ccu_service.to_response_record(row)

    assert mapped["missing_flag"] is True
    assert mapped["delta_ccu_pct"] is None


def test_to_response_record_with_prev_computes_pct() -> None:
    row = {
        "canonical_game_id": 77,
        "canonical_name": "example",
        "bucket_time": dt.datetime(2026, 3, 7, 12, 0, tzinfo=KST),
        "ccu": 120,
        "delta_ccu_abs": 20,
        "prev_day_same_bucket_ccu": 100,
    }

    mapped = ccu_service.to_response_record(row)

    assert mapped["missing_flag"] is False
    assert mapped["delta_ccu_abs"] == 20
    assert mapped["delta_ccu_pct"] == 20.0


def test_list_latest_ccu_uses_window_sql_for_30d(monkeypatch) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()
    rows = [
        {
            "canonical_game_id": "77",
            "canonical_name": "example",
            "bucket_time": dt.datetime(2026, 3, 7, 12, 0, tzinfo=KST),
            "ccu": "120",
            "delta_ccu_abs": "20",
            "prev_day_same_bucket_ccu": "100",
        }
    ]

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def execute(self, sql: str, params: tuple[int, ...]) -> None:
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

    result = ccu_service.list_latest_ccu(limit=10, window="30d")

    assert captured["conninfo"] == "fake-conninfo"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["sql"] == ccu_service.LIST_LATEST_WINDOW_SQL
    assert captured["params"] == (30, 30, 10)
    assert result == [
        {
            "canonical_game_id": 77,
            "canonical_name": "example",
            "bucket_time": dt.datetime(2026, 3, 7, 12, 0, tzinfo=KST),
            "ccu": 120,
            "delta_ccu_abs": 20,
            "delta_ccu_pct": 20.0,
            "missing_flag": False,
        }
    ]


def test_list_latest_ccu_rejects_unknown_window() -> None:
    with pytest.raises(ValueError, match="Unsupported most-played window: 365d"):
        ccu_service.list_latest_ccu(window="365d")
