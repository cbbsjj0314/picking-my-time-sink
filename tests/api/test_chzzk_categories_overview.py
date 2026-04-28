from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import app as api_app
from api.routers.chzzk import router as chzzk_router
from api.services import chzzk_service

KST = ZoneInfo("Asia/Seoul")


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(chzzk_router)
    return TestClient(app)


def sample_response_record(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "chzzk_category_id": "category-alpha",
        "category_name": "Synthetic Category Alpha",
        "category_type": "GAME",
        "observed_bucket_count": 2,
        "bucket_time_min": dt.datetime(2026, 4, 29, 10, 0, tzinfo=KST),
        "bucket_time_max": dt.datetime(2026, 4, 29, 10, 30, tzinfo=KST),
        "viewer_hours_observed": 35.0,
        "avg_viewers_observed": 35.0,
        "peak_viewers_observed": 40,
        "live_count_observed_total": 5,
        "avg_channels_observed": 2.5,
        "peak_channels_observed": 3,
        "full_1d_candidate_available": False,
        "full_7d_candidate_available": False,
        "missing_1d_bucket_count": 46,
        "missing_7d_bucket_count": 334,
        "coverage_status": "partial_window",
        "bounded_sample_caveat": "bounded_sample",
    }
    row.update(overrides)
    return row


def sample_db_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "chzzk_category_id": "category-alpha",
        "category_name": "Synthetic Category Alpha",
        "category_type": "GAME",
        "observed_bucket_count": "2",
        "bucket_time_min": dt.datetime(2026, 4, 29, 10, 0, tzinfo=KST),
        "bucket_time_max": dt.datetime(2026, 4, 29, 10, 30, tzinfo=KST),
        "viewer_hours_observed": "35.0",
        "avg_viewers_observed": "35.0",
        "peak_viewers_observed": "40",
        "live_count_observed_total": "5",
        "avg_channels_observed": "2.5",
        "peak_channels_observed": "3",
    }
    row.update(overrides)
    return row


def test_app_includes_chzzk_categories_overview_route() -> None:
    routes = {getattr(route, "path", "") for route in api_app.routes}

    assert "/chzzk/categories/overview" in routes


def test_list_chzzk_categories_overview_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_category_overview(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_response_record()]

    monkeypatch.setattr(
        chzzk_service,
        "list_category_overview",
        fake_list_category_overview,
    )

    client = build_test_client()
    response = client.get("/chzzk/categories/overview", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
    assert response.json() == [
        {
            "chzzk_category_id": "category-alpha",
            "category_name": "Synthetic Category Alpha",
            "category_type": "GAME",
            "observed_bucket_count": 2,
            "bucket_time_min": "2026-04-29T10:00:00+09:00",
            "bucket_time_max": "2026-04-29T10:30:00+09:00",
            "viewer_hours_observed": 35.0,
            "avg_viewers_observed": 35.0,
            "peak_viewers_observed": 40,
            "live_count_observed_total": 5,
            "avg_channels_observed": 2.5,
            "peak_channels_observed": 3,
            "full_1d_candidate_available": False,
            "full_7d_candidate_available": False,
            "missing_1d_bucket_count": 46,
            "missing_7d_bucket_count": 334,
            "coverage_status": "partial_window",
            "bounded_sample_caveat": "bounded_sample",
        }
    ]


def test_list_chzzk_categories_overview_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(chzzk_service, "list_category_overview", lambda limit=50: [])

    client = build_test_client()
    response = client.get("/chzzk/categories/overview")

    assert response.status_code == 200
    assert response.json() == []


def test_list_chzzk_categories_overview_rejects_invalid_limit(monkeypatch) -> None:
    called = False

    def fake_list_category_overview(limit: int = 50) -> list[dict[str, object]]:
        del limit
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        chzzk_service,
        "list_category_overview",
        fake_list_category_overview,
    )

    client = build_test_client()
    response = client.get("/chzzk/categories/overview", params={"limit": 0})

    assert response.status_code == 422
    assert called is False


def test_to_response_record_computes_observed_coverage_fields() -> None:
    mapped = chzzk_service.to_response_record(sample_db_row(observed_bucket_count="2"))

    assert mapped["observed_bucket_count"] == 2
    assert mapped["full_1d_candidate_available"] is False
    assert mapped["full_7d_candidate_available"] is False
    assert mapped["missing_1d_bucket_count"] == 46
    assert mapped["missing_7d_bucket_count"] == 334
    assert mapped["coverage_status"] == "partial_window"
    assert mapped["bounded_sample_caveat"] == "bounded_sample"


def test_bounded_sample_caveat_is_independent_from_bucket_coverage_status() -> None:
    one_bucket = chzzk_service.to_response_record(
        sample_db_row(observed_bucket_count=1)
    )
    full_1d = chzzk_service.to_response_record(sample_db_row(observed_bucket_count=48))
    full_7d = chzzk_service.to_response_record(sample_db_row(observed_bucket_count=336))

    assert one_bucket["coverage_status"] == "observed_bucket_only"
    assert full_1d["coverage_status"] == "full_1d_candidate_available"
    assert full_7d["coverage_status"] == "full_7d_candidate_available"
    assert one_bucket["bounded_sample_caveat"] == "bounded_sample"
    assert full_1d["bounded_sample_caveat"] == "bounded_sample"
    assert full_7d["bounded_sample_caveat"] == "bounded_sample"


def test_response_omits_private_raw_and_mapping_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        chzzk_service,
        "list_category_overview",
        lambda limit=50: [sample_response_record()],
    )

    client = build_test_client()
    response = client.get("/chzzk/categories/overview")

    assert response.status_code == 200
    keys = set(response.json()[0])
    forbidden_keys = {
        "canonical_game_id",
        "steam_appid",
        "unique_channels_observed",
        "top_channel_id",
        "top_channel_name",
        "top_channel_concurrent",
        "channel_name",
        "live_title",
        "thumbnail",
        "raw_provider_payload",
        "credential",
        "local_path",
    }
    assert keys.isdisjoint(forbidden_keys)


def test_service_sql_reads_chzzk_category_fact_only() -> None:
    sql = chzzk_service.LIST_CATEGORY_OVERVIEW_SQL.lower()

    assert "from fact_chzzk_category_30m" in sql
    assert "srv_" not in sql
    assert "fact_steam" not in sql
    assert "game_external_id" not in sql
    assert "canonical_game_id" not in sql
    assert "combined" not in sql
    assert "unique_channels" not in sql
    assert "top_channel" not in sql


def test_service_sql_computes_observed_metrics_and_default_sort() -> None:
    sql = chzzk_service.LIST_CATEGORY_OVERVIEW_SQL.lower()

    assert "sum(concurrent_sum * 0.5) as viewer_hours_observed" in sql
    assert "avg(concurrent_sum::double precision) as avg_viewers_observed" in sql
    assert "max(concurrent_sum) as peak_viewers_observed" in sql
    assert "sum(live_count) as live_count_observed_total" in sql
    assert "avg(live_count::double precision) as avg_channels_observed" in sql
    assert "max(live_count) as peak_channels_observed" in sql
    assert "order by" in sql
    assert "agg.viewer_hours_observed desc" in sql
    assert "agg.peak_viewers_observed desc" in sql
    assert "agg.chzzk_category_id asc" in sql


def test_service_sql_selects_latest_category_metadata_deterministically() -> None:
    sql = chzzk_service.LIST_CATEGORY_OVERVIEW_SQL.lower()

    assert "select distinct on (chzzk_category_id)" in sql
    assert "category_name" in sql
    assert "category_type" in sql
    assert (
        "order by chzzk_category_id, bucket_time desc, collected_at desc, ingested_at desc"
        in sql
    )


def test_latest_metadata_row_is_preserved_in_response_record() -> None:
    mapped = chzzk_service.to_response_record(
        sample_db_row(
            category_name="Synthetic Category Latest",
            category_type="ENTERTAINMENT",
        )
    )

    assert mapped["category_name"] == "Synthetic Category Latest"
    assert mapped["category_type"] == "ENTERTAINMENT"


def test_list_category_overview_executes_read_only_aggregate_query(monkeypatch) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()
    rows = [sample_db_row()]

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

    monkeypatch.setattr(
        chzzk_service,
        "require_psycopg",
        lambda: (FakePsycopg, dict_row_sentinel),
    )
    monkeypatch.setattr(chzzk_service, "build_pg_conninfo_from_env", lambda: "fake")

    result = chzzk_service.list_category_overview(limit=10)

    assert captured["conninfo"] == "fake"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["sql"] == chzzk_service.LIST_CATEGORY_OVERVIEW_SQL
    assert captured["params"] == (10,)
    assert result == [sample_response_record()]
