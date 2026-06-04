from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import app as api_app
from api.routers.chzzk import ChzzkCategoryGameMappingResponse
from api.routers.chzzk import router as chzzk_router
from api.routers.combined import CombinedGameOverviewResponse
from api.routers.combined import router as combined_router
from api.routers.games import GameExploreOverviewResponse
from api.routers.games import router as games_router
from api.services import combined_service

KST = ZoneInfo("Asia/Seoul")


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(combined_router)
    return TestClient(app)


def sample_combined_response_record(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "canonical_game_id": 1001,
        "canonical_name": "Synthetic Game Alpha",
        "steam_appid": 730,
        "steam_source_available": True,
        "chzzk_mapping_available": True,
        "chzzk_category_id": "category-alpha",
        "category_name": "Synthetic Category Alpha",
        "category_type": "GAME",
        "latest_bucket_time": dt.datetime(2026, 5, 28, 9, 0, tzinfo=KST),
    }
    row.update(overrides)
    return row


def test_app_includes_combined_game_overview_route() -> None:
    routes = {getattr(route, "path", "") for route in api_app.routes}

    assert "/combined/games/overview" in routes


def test_list_combined_games_overview_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_game_overview(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_combined_response_record()]

    monkeypatch.setattr(combined_service, "list_game_overview", fake_list_game_overview)

    client = build_test_client()
    response = client.get("/combined/games/overview", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
    assert response.json() == [
        {
            "canonical_game_id": 1001,
            "canonical_name": "Synthetic Game Alpha",
            "steam_appid": 730,
            "steam_source_available": True,
            "chzzk_mapping_available": True,
            "chzzk_category_id": "category-alpha",
            "category_name": "Synthetic Category Alpha",
            "category_type": "GAME",
            "latest_bucket_time": "2026-05-28T09:00:00+09:00",
        }
    ]


def test_list_combined_games_overview_rejects_invalid_limit(monkeypatch) -> None:
    called = False

    def fake_list_game_overview(limit: int = 50) -> list[dict[str, object]]:
        del limit
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(combined_service, "list_game_overview", fake_list_game_overview)

    client = build_test_client()
    response = client.get("/combined/games/overview", params={"limit": 0})

    assert response.status_code == 422
    assert called is False


def test_no_trusted_mapping_keeps_steam_row_with_nullable_chzzk_fields(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        combined_service,
        "list_game_overview",
        lambda limit=50: [
            sample_combined_response_record(
                chzzk_mapping_available=False,
                chzzk_category_id=None,
                category_name=None,
                category_type=None,
                latest_bucket_time=None,
            )
        ],
    )

    client = build_test_client()
    response = client.get("/combined/games/overview")

    assert response.status_code == 200
    assert response.json() == [
        {
            "canonical_game_id": 1001,
            "canonical_name": "Synthetic Game Alpha",
            "steam_appid": 730,
            "steam_source_available": True,
            "chzzk_mapping_available": False,
            "chzzk_category_id": None,
            "category_name": None,
            "category_type": None,
            "latest_bucket_time": None,
        }
    ]


def test_one_trusted_mapping_populates_mapping_fields_and_flag() -> None:
    mapped = combined_service.to_response_record(
        {
            "canonical_game_id": "1001",
            "canonical_name": "Synthetic Game Alpha",
            "steam_appid": "730",
            "steam_source_available": True,
            "chzzk_mapping_available": True,
            "chzzk_category_id": "category-alpha",
            "category_name": "Synthetic Category Alpha",
            "category_type": "GAME",
            "latest_bucket_time": dt.datetime(2026, 5, 28, 9, 0, tzinfo=KST),
        }
    )

    assert mapped == sample_combined_response_record()


def test_row_grain_remains_one_row_per_selected_steam_canonical_game_id(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        combined_service,
        "list_game_overview",
        lambda limit=50: [
            sample_combined_response_record(canonical_game_id=1001),
            sample_combined_response_record(
                canonical_game_id=1002,
                canonical_name="Synthetic Game Beta",
                chzzk_category_id=None,
                category_name=None,
                category_type=None,
                latest_bucket_time=None,
                chzzk_mapping_available=False,
            ),
        ],
    )

    client = build_test_client()
    response = client.get("/combined/games/overview")

    assert response.status_code == 200
    ids = [row["canonical_game_id"] for row in response.json()]
    assert ids == [1001, 1002]
    assert len(ids) == len(set(ids))


def test_combined_response_model_exposes_only_approved_fields() -> None:
    fields = set(CombinedGameOverviewResponse.model_fields)

    assert fields == {
        "canonical_game_id",
        "canonical_name",
        "steam_appid",
        "steam_source_available",
        "chzzk_mapping_available",
        "chzzk_category_id",
        "category_name",
        "category_type",
        "latest_bucket_time",
    }


def test_combined_response_omits_private_candidate_viewer_ranking_and_score_fields(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        combined_service,
        "list_game_overview",
        lambda limit=50: [sample_combined_response_record()],
    )

    client = build_test_client()
    response = client.get("/combined/games/overview")

    assert response.status_code == 200
    keys = set(response.json()[0])
    forbidden_keys = {
        "mapping_status",
        "source_kind",
        "reviewed_by",
        "reviewed_at",
        "candidate_id",
        "candidate_status",
        "latest_viewers_observed",
        "viewer_hours_observed",
        "avg_viewers_observed",
        "peak_viewers_observed",
        "viewer_per_channel_observed",
        "unique_channels_observed",
        "rank",
        "ranking",
        "kpi",
        "score",
        "recommendation",
        "mapping_coverage",
        "fallback_mapping",
        "unresolved_mapping",
        "rejected_mapping",
    }
    assert keys.isdisjoint(forbidden_keys)


def test_combined_service_sql_reads_serving_view_only() -> None:
    sql = combined_service.LIST_COMBINED_GAME_OVERVIEW_SQL.lower()

    assert "from srv_combined_game_overview" in sql
    assert "from srv_game_explore_period_metrics" not in sql
    assert "srv_chzzk_category_game_mapping" not in sql
    assert "chzzk_category_game_candidate" not in sql
    assert "fact_chzzk_category_30m" not in sql
    assert "fact_chzzk_category_channel_30m" not in sql
    assert "get /chzzk/category-game-mappings" not in sql
    assert "/chzzk/category-game-mappings" not in sql
    assert "order by canonical_game_id asc" in sql
    assert "limit %s" in sql


def test_combined_service_does_not_call_chzzk_mapping_api_internally() -> None:
    service_source = combined_service.__loader__.get_source(  # type: ignore[union-attr]
        combined_service.__name__
    ).lower()

    assert "category-game-mappings" not in service_source
    assert "list_category_game_mappings" not in service_source
    assert "chzzk_service" not in service_source


def test_combined_service_executes_serving_view_query(monkeypatch) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()
    rows = [sample_combined_response_record(canonical_game_id="1001")]

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def execute(self, sql: str, params: tuple[int]) -> None:
            captured["execute_call"] = (sql, params)

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

    monkeypatch.setattr(
        combined_service,
        "require_psycopg",
        lambda: (FakePsycopg, dict_row_sentinel),
    )
    monkeypatch.setattr(combined_service, "build_pg_conninfo_from_env", lambda: "fake")

    result = combined_service.list_game_overview(limit=10)

    assert captured["conninfo"] == "fake"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["execute_call"] == (
        combined_service.LIST_COMBINED_GAME_OVERVIEW_SQL,
        (10,),
    )
    assert result == [sample_combined_response_record(canonical_game_id=1001)]


def test_existing_source_routes_and_response_models_remain_unaffected() -> None:
    app = FastAPI()
    app.include_router(games_router)
    app.include_router(chzzk_router)
    app.include_router(combined_router)
    routes = {getattr(route, "path", "") for route in app.routes}

    assert "/games/explore/overview" in routes
    assert "/chzzk/categories/overview" in routes
    assert "/chzzk/category-game-mappings" in routes
    assert "/combined/games/overview" in routes
    assert "chzzk_category_id" not in GameExploreOverviewResponse.model_fields
    assert "canonical_game_id" not in ChzzkCategoryGameMappingResponse.model_fields
