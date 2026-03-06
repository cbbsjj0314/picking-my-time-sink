from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

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


def test_list_games_latest_ccu_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_latest_ccu(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_response_record(1), sample_response_record(2)]

    monkeypatch.setattr(ccu_service, "list_latest_ccu", fake_list_latest_ccu)

    client = build_test_client()
    response = client.get("/games/ccu/latest", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
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
    assert body["delta_ccu_abs"] == 20
    assert body["missing_flag"] is False


def test_service_sql_uses_serving_view_only() -> None:
    single_sql = ccu_service.GET_LATEST_BY_GAME_SQL.lower()
    list_sql = ccu_service.LIST_LATEST_SQL.lower()

    assert "from srv_game_latest_ccu" in single_sql
    assert "from srv_game_latest_ccu" in list_sql
    assert "fact_steam_ccu_30m" not in single_sql
    assert "fact_steam_ccu_30m" not in list_sql


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
