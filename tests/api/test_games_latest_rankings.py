from __future__ import annotations

import datetime as dt

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.games import router as games_router
from api.services import rankings_service


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(games_router)
    return TestClient(app)


def sample_response_record(rank_position: int) -> dict[str, object]:
    return {
        "snapshot_date": dt.date(2026, 3, 31),
        "rank_position": rank_position,
        "steam_appid": 730 if rank_position == 1 else 570,
        "canonical_game_id": 1 if rank_position == 1 else None,
        "canonical_name": "Counter-Strike 2" if rank_position == 1 else None,
    }


def test_list_games_latest_rankings_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_latest_rankings(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_response_record(1), sample_response_record(2)]

    monkeypatch.setattr(rankings_service, "list_latest_rankings", fake_list_latest_rankings)

    client = build_test_client()
    response = client.get("/games/rankings/latest", params={"limit": 25, "window": "7d"})

    assert response.status_code == 200
    assert captured["limit"] == 25
    assert response.json() == [
        {
            "snapshot_date": "2026-03-31",
            "rank_position": 1,
            "steam_appid": 730,
            "canonical_game_id": 1,
            "canonical_name": "Counter-Strike 2",
        },
        {
            "snapshot_date": "2026-03-31",
            "rank_position": 2,
            "steam_appid": 570,
            "canonical_game_id": None,
            "canonical_name": None,
        },
    ]


def test_service_sql_uses_rankings_serving_view_only() -> None:
    list_sql = rankings_service.LIST_LATEST_SQL.lower()

    assert "from srv_rank_latest_kr_top_selling" in list_sql
    assert "fact_steam_rank_daily" not in list_sql


def test_to_response_record_preserves_nullable_mapping_fields() -> None:
    row = {
        "snapshot_date": dt.date(2026, 3, 31),
        "rank_position": 2,
        "steam_appid": 570,
        "canonical_game_id": None,
        "canonical_name": None,
    }

    mapped = rankings_service.to_response_record(row)

    assert mapped["rank_position"] == 2
    assert mapped["canonical_game_id"] is None
    assert mapped["canonical_name"] is None


def test_list_games_latest_rankings_rejects_unsupported_window(monkeypatch) -> None:
    expected_detail = (
        "Top Selling currently supports only window=7d because the Steam topsellers "
        "source is weekly."
    )
    called = False

    def fake_list_latest_rankings(limit: int = 50) -> list[dict[str, object]]:
        del limit
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(rankings_service, "list_latest_rankings", fake_list_latest_rankings)

    client = build_test_client()
    response = client.get("/games/rankings/latest", params={"window": "30d"})

    assert response.status_code == 400
    assert called is False
    assert response.json()["detail"] == expected_detail
