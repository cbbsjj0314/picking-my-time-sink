from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.games import router as games_router
from api.services import price_service

KST = ZoneInfo("Asia/Seoul")


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(games_router)
    return TestClient(app)


def sample_response_record(canonical_game_id: int) -> dict[str, object]:
    return {
        "canonical_game_id": canonical_game_id,
        "canonical_name": f"game-{canonical_game_id}",
        "bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
        "region": "KR",
        "currency_code": "KRW",
        "initial_price_minor": 4200000,
        "final_price_minor": 3360000,
        "discount_percent": 20,
        "is_free": None,
    }


def test_list_games_latest_price_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_latest_price(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_response_record(1), sample_response_record(2)]

    monkeypatch.setattr(price_service, "list_latest_price", fake_list_latest_price)

    client = build_test_client()
    response = client.get("/games/price/latest", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
    body = response.json()
    assert len(body) == 2
    assert body[0]["canonical_game_id"] == 1
    assert body[0]["region"] == "KR"
    assert body[0]["currency_code"] == "KRW"


def test_get_game_latest_price_returns_404_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        price_service,
        "get_latest_price_by_game",
        lambda canonical_game_id: None,
    )

    client = build_test_client()
    response = client.get("/games/999/price/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "Game latest price not found"


def test_get_game_latest_price_returns_row(monkeypatch) -> None:
    monkeypatch.setattr(
        price_service,
        "get_latest_price_by_game",
        lambda canonical_game_id: sample_response_record(canonical_game_id),
    )

    client = build_test_client()
    response = client.get("/games/123/price/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_game_id"] == 123
    assert body["bucket_time"] == "2026-03-29T14:00:00+09:00"
    assert body["region"] == "KR"
    assert body["currency_code"] == "KRW"
    assert body["initial_price_minor"] == 4200000
    assert body["final_price_minor"] == 3360000
    assert body["discount_percent"] == 20
    assert body["is_free"] is None


def test_service_sql_uses_price_serving_view_only() -> None:
    single_sql = price_service.GET_LATEST_BY_GAME_SQL.lower()
    list_sql = price_service.LIST_LATEST_SQL.lower()

    assert "from srv_game_latest_price" in single_sql
    assert "from srv_game_latest_price" in list_sql
    assert "fact_steam_price_1h" not in single_sql
    assert "fact_steam_price_1h" not in list_sql


def test_to_response_record_preserves_nullable_is_free() -> None:
    row = {
        "canonical_game_id": 77,
        "canonical_name": "example",
        "bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
        "region": "KR",
        "currency_code": "KRW",
        "initial_price_minor": 4200000,
        "final_price_minor": 4200000,
        "discount_percent": 0,
        "is_free": None,
    }

    mapped = price_service.to_response_record(row)

    assert mapped["is_free"] is None
    assert mapped["discount_percent"] == 0


def test_to_response_record_preserves_boolean_is_free() -> None:
    row = {
        "canonical_game_id": 77,
        "canonical_name": "example",
        "bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
        "region": "KR",
        "currency_code": "KRW",
        "initial_price_minor": 0,
        "final_price_minor": 0,
        "discount_percent": 0,
        "is_free": False,
    }

    mapped = price_service.to_response_record(row)

    assert mapped["is_free"] is False
    assert mapped["final_price_minor"] == 0
