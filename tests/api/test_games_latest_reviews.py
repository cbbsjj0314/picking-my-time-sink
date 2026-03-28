from __future__ import annotations

import datetime as dt

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.games import router as games_router
from api.services import reviews_service


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(games_router)
    return TestClient(app)


def sample_response_record(canonical_game_id: int) -> dict[str, object]:
    return {
        "canonical_game_id": canonical_game_id,
        "canonical_name": f"game-{canonical_game_id}",
        "snapshot_date": dt.date(2026, 3, 29),
        "total_reviews": 1000,
        "total_positive": 820,
        "total_negative": 180,
        "positive_ratio": 0.82,
        "delta_total_reviews": 25,
        "delta_positive_ratio": 0.01,
        "missing_flag": False,
    }


def test_list_games_latest_reviews_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_latest_reviews(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_response_record(1), sample_response_record(2)]

    monkeypatch.setattr(reviews_service, "list_latest_reviews", fake_list_latest_reviews)

    client = build_test_client()
    response = client.get("/games/reviews/latest", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
    body = response.json()
    assert len(body) == 2
    assert body[0]["canonical_game_id"] == 1
    assert body[0]["positive_ratio"] == 0.82


def test_get_game_latest_reviews_returns_404_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        reviews_service,
        "get_latest_reviews_by_game",
        lambda canonical_game_id: None,
    )

    client = build_test_client()
    response = client.get("/games/999/reviews/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "Game latest reviews not found"


def test_get_game_latest_reviews_returns_row(monkeypatch) -> None:
    monkeypatch.setattr(
        reviews_service,
        "get_latest_reviews_by_game",
        lambda canonical_game_id: sample_response_record(canonical_game_id),
    )

    client = build_test_client()
    response = client.get("/games/123/reviews/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_game_id"] == 123
    assert body["snapshot_date"] == "2026-03-29"
    assert body["delta_total_reviews"] == 25
    assert body["delta_positive_ratio"] == 0.01
    assert body["missing_flag"] is False


def test_service_sql_uses_reviews_serving_view_only() -> None:
    single_sql = reviews_service.GET_LATEST_BY_GAME_SQL.lower()
    list_sql = reviews_service.LIST_LATEST_SQL.lower()

    assert "from srv_game_latest_reviews" in single_sql
    assert "from srv_game_latest_reviews" in list_sql
    assert "fact_steam_reviews_daily" not in single_sql
    assert "fact_steam_reviews_daily" not in list_sql


def test_to_response_record_missing_prev_sets_flag() -> None:
    row = {
        "canonical_game_id": 77,
        "canonical_name": "example",
        "snapshot_date": dt.date(2026, 3, 29),
        "total_reviews": 100,
        "total_positive": 80,
        "total_negative": 20,
        "positive_ratio": 0.8,
        "delta_total_reviews": None,
        "delta_positive_ratio": None,
        "prev_day_total_reviews": None,
    }

    mapped = reviews_service.to_response_record(row)

    assert mapped["missing_flag"] is True
    assert mapped["delta_total_reviews"] is None
    assert mapped["delta_positive_ratio"] is None


def test_to_response_record_with_prev_keeps_delta_values() -> None:
    row = {
        "canonical_game_id": 77,
        "canonical_name": "example",
        "snapshot_date": dt.date(2026, 3, 29),
        "total_reviews": 120,
        "total_positive": 100,
        "total_negative": 20,
        "positive_ratio": 0.8333333333,
        "delta_total_reviews": 12,
        "delta_positive_ratio": 0.02,
        "prev_day_total_reviews": 108,
    }

    mapped = reviews_service.to_response_record(row)

    assert mapped["missing_flag"] is False
    assert mapped["delta_total_reviews"] == 12
    assert mapped["delta_positive_ratio"] == 0.02
    assert mapped["positive_ratio"] == 0.8333333333
