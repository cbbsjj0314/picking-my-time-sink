from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import app as api_app
from api.routers.chzzk import ChzzkCategoryGameMappingResponse
from api.routers.chzzk import router as chzzk_router
from api.services import chzzk_service

KST = ZoneInfo("Asia/Seoul")


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(chzzk_router)
    return TestClient(app)


def sample_mapping_response_record(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "chzzk_category_id": "category-alpha",
        "category_name": "Synthetic Category Alpha",
        "category_type": "GAME",
        "latest_bucket_time": dt.datetime(2026, 5, 28, 9, 0, tzinfo=KST),
        "mapped_canonical_game_id": 1001,
        "mapped_canonical_game_name": "Synthetic Game Alpha",
    }
    row.update(overrides)
    return row


def test_app_includes_chzzk_category_game_mappings_route() -> None:
    routes = {getattr(route, "path", "") for route in api_app.routes}

    assert "/chzzk/category-game-mappings" in routes


def test_list_chzzk_category_game_mappings_returns_rows_and_passes_limit(
    monkeypatch,
) -> None:
    captured: dict[str, int] = {}

    def fake_list_category_game_mappings(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_mapping_response_record()]

    monkeypatch.setattr(
        chzzk_service,
        "list_category_game_mappings",
        fake_list_category_game_mappings,
    )

    client = build_test_client()
    response = client.get("/chzzk/category-game-mappings", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
    assert response.json() == [
        {
            "chzzk_category_id": "category-alpha",
            "category_name": "Synthetic Category Alpha",
            "category_type": "GAME",
            "latest_bucket_time": "2026-05-28T09:00:00+09:00",
            "mapped_canonical_game_id": 1001,
            "mapped_canonical_game_name": "Synthetic Game Alpha",
        }
    ]


def test_list_chzzk_category_game_mappings_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(chzzk_service, "list_category_game_mappings", lambda limit=50: [])

    client = build_test_client()
    response = client.get("/chzzk/category-game-mappings")

    assert response.status_code == 200
    assert response.json() == []


def test_list_chzzk_category_game_mappings_rejects_invalid_limit(monkeypatch) -> None:
    called = False

    def fake_list_category_game_mappings(limit: int = 50) -> list[dict[str, object]]:
        del limit
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        chzzk_service,
        "list_category_game_mappings",
        fake_list_category_game_mappings,
    )

    client = build_test_client()
    response = client.get("/chzzk/category-game-mappings", params={"limit": 0})

    assert response.status_code == 422
    assert called is False


def test_mapping_response_serializes_nullable_category_context(monkeypatch) -> None:
    monkeypatch.setattr(
        chzzk_service,
        "list_category_game_mappings",
        lambda limit=50: [
            sample_mapping_response_record(
                category_name=None,
                category_type=None,
                latest_bucket_time=None,
            )
        ],
    )

    client = build_test_client()
    response = client.get("/chzzk/category-game-mappings")

    assert response.status_code == 200
    assert response.json() == [
        {
            "chzzk_category_id": "category-alpha",
            "category_name": None,
            "category_type": None,
            "latest_bucket_time": None,
            "mapped_canonical_game_id": 1001,
            "mapped_canonical_game_name": "Synthetic Game Alpha",
        }
    ]


def test_mapping_response_model_keeps_minimal_public_fields() -> None:
    fields = set(ChzzkCategoryGameMappingResponse.model_fields)

    assert fields == {
        "chzzk_category_id",
        "category_name",
        "category_type",
        "latest_bucket_time",
        "mapped_canonical_game_id",
        "mapped_canonical_game_name",
    }


def test_mapping_response_omits_private_provenance_and_candidate_fields(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        chzzk_service,
        "list_category_game_mappings",
        lambda limit=50: [sample_mapping_response_record()],
    )

    client = build_test_client()
    response = client.get("/chzzk/category-game-mappings")

    assert response.status_code == 200
    keys = set(response.json()[0])
    forbidden_keys = {
        "mapping_status",
        "source_kind",
        "reviewed_by",
        "reviewed_at",
        "candidate_id",
        "candidate_status",
        "category_game_candidate_status",
        "raw_provider_payload",
        "credential",
        "local_path",
        "manual_hint",
    }
    assert keys.isdisjoint(forbidden_keys)


def test_mapping_service_sql_reads_serving_view_only() -> None:
    sql = chzzk_service.LIST_CATEGORY_GAME_MAPPINGS_SQL.lower()

    assert "from srv_chzzk_category_game_mapping" in sql
    assert "from chzzk_category_game_mapping" not in sql
    assert "join chzzk_category_game_mapping" not in sql
    assert "chzzk_category_game_candidate" not in sql
    assert "fact_chzzk_category_30m" not in sql
    assert "dim_game" not in sql
    assert "mapping_status" not in sql
    assert "source_kind" not in sql
    assert "reviewed_by" not in sql
    assert "reviewed_at" not in sql
    assert "order by chzzk_category_id asc" in sql
    assert "limit %s" in sql


def test_mapping_service_record_maps_nullable_context_and_required_mapping() -> None:
    mapped = chzzk_service.to_category_game_mapping_response_record(
        {
            "chzzk_category_id": "category-alpha",
            "category_name": None,
            "category_type": None,
            "latest_bucket_time": None,
            "mapped_canonical_game_id": "1001",
            "mapped_canonical_game_name": "Synthetic Game Alpha",
        }
    )

    assert mapped == {
        "chzzk_category_id": "category-alpha",
        "category_name": None,
        "category_type": None,
        "latest_bucket_time": None,
        "mapped_canonical_game_id": 1001,
        "mapped_canonical_game_name": "Synthetic Game Alpha",
    }


def test_mapping_service_executes_serving_view_query(monkeypatch) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()
    rows = [sample_mapping_response_record(mapped_canonical_game_id="1001")]

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
        chzzk_service,
        "require_psycopg",
        lambda: (FakePsycopg, dict_row_sentinel),
    )
    monkeypatch.setattr(chzzk_service, "build_pg_conninfo_from_env", lambda: "fake")

    result = chzzk_service.list_category_game_mappings(limit=10)

    assert captured["conninfo"] == "fake"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["execute_call"] == (
        chzzk_service.LIST_CATEGORY_GAME_MAPPINGS_SQL,
        (10,),
    )
    assert result == [sample_mapping_response_record(mapped_canonical_game_id=1001)]
