from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.games import router as games_router
from api.services import explore_service

KST = ZoneInfo("Asia/Seoul")


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(games_router)
    return TestClient(app)


def sample_response_record(canonical_game_id: int) -> dict[str, object]:
    return {
        "canonical_game_id": canonical_game_id,
        "canonical_name": f"game-{canonical_game_id}",
        "steam_appid": 730,
        "ccu_bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
        "current_ccu": 1200,
        "current_delta_ccu_abs": 200,
        "current_delta_ccu_pct": 20.0,
        "current_ccu_missing_flag": False,
        "ccu_period_anchor_date": dt.date(2026, 3, 29),
        "period_avg_ccu_7d": 1100.5,
        "period_peak_ccu_7d": 1800,
        "delta_period_avg_ccu_7d_abs": 100.5,
        "delta_period_avg_ccu_7d_pct": 10.05,
        "delta_period_peak_ccu_7d_abs": 300,
        "delta_period_peak_ccu_7d_pct": 20.0,
        "estimated_player_hours_7d": 92400.0,
        "delta_estimated_player_hours_7d_abs": 8400.0,
        "delta_estimated_player_hours_7d_pct": 10.0,
        "reviews_snapshot_date": dt.date(2026, 3, 29),
        "total_reviews": 1000,
        "total_positive": 820,
        "total_negative": 180,
        "positive_ratio": 0.82,
        "reviews_added_7d": 70,
        "reviews_added_30d": 250,
        "period_positive_ratio_7d": 0.8,
        "period_positive_ratio_30d": 0.84,
        "delta_reviews_added_7d_abs": 20,
        "delta_reviews_added_7d_pct": 40.0,
        "delta_period_positive_ratio_7d_pp": 5.0,
        "delta_reviews_added_30d_abs": 50,
        "delta_reviews_added_30d_pct": 25.0,
        "delta_period_positive_ratio_30d_pp": -2.0,
        "price_bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
        "region": "KR",
        "currency_code": "KRW",
        "initial_price_minor": 4200000,
        "final_price_minor": 3360000,
        "discount_percent": 20,
        "is_free": None,
    }


def test_list_games_explore_overview_returns_rows_and_passes_limit(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_list_explore_overview(limit: int = 50) -> list[dict[str, object]]:
        captured["limit"] = limit
        return [sample_response_record(1), sample_response_record(2)]

    monkeypatch.setattr(explore_service, "list_explore_overview", fake_list_explore_overview)

    client = build_test_client()
    response = client.get("/games/explore/overview", params={"limit": 25})

    assert response.status_code == 200
    assert captured["limit"] == 25
    body = response.json()
    assert len(body) == 2
    assert body[0]["canonical_game_id"] == 1
    assert body[0]["ccu_bucket_time"] == "2026-03-29T14:00:00+09:00"
    assert body[0]["current_ccu"] == 1200
    assert body[0]["period_avg_ccu_7d"] == 1100.5
    assert body[0]["estimated_player_hours_7d"] == 92400.0
    assert body[0]["reviews_added_7d"] == 70
    assert body[0]["delta_reviews_added_7d_pct"] == 40.0
    assert body[0]["delta_period_positive_ratio_7d_pp"] == 5.0
    assert body[0]["period_positive_ratio_30d"] == 0.84
    assert body[0]["region"] == "KR"


def test_service_sql_reads_explore_serving_view_with_default_sort() -> None:
    sql = explore_service.LIST_EXPLORE_OVERVIEW_SQL.lower()

    assert "from srv_game_explore_period_metrics" in sql
    assert "fact_steam_ccu_30m" not in sql
    assert "fact_steam_reviews_daily" not in sql
    assert "fact_steam_price_1h" not in sql
    assert "estimated_player_hours_7d" in sql
    assert "delta_estimated_player_hours_7d_pct" in sql
    assert "delta_reviews_added_7d_abs" in sql
    assert "delta_period_positive_ratio_30d_pp" in sql
    assert "order by period_avg_ccu_7d desc nulls last, canonical_game_id asc" in sql


def test_to_response_record_preserves_null_evidence_fields() -> None:
    row = {
        "canonical_game_id": "77",
        "canonical_name": "example",
        "steam_appid": None,
        "ccu_bucket_time": None,
        "current_ccu": None,
        "current_delta_ccu_abs": None,
        "current_delta_ccu_pct": None,
        "current_ccu_missing_flag": True,
        "ccu_period_anchor_date": dt.date(2026, 3, 29),
        "period_avg_ccu_7d": None,
        "period_peak_ccu_7d": None,
        "delta_period_avg_ccu_7d_abs": None,
        "delta_period_avg_ccu_7d_pct": None,
        "delta_period_peak_ccu_7d_abs": None,
        "delta_period_peak_ccu_7d_pct": None,
        "estimated_player_hours_7d": None,
        "delta_estimated_player_hours_7d_abs": None,
        "delta_estimated_player_hours_7d_pct": None,
        "reviews_snapshot_date": None,
        "total_reviews": None,
        "total_positive": None,
        "total_negative": None,
        "positive_ratio": None,
        "reviews_added_7d": None,
        "reviews_added_30d": None,
        "period_positive_ratio_7d": None,
        "period_positive_ratio_30d": None,
        "delta_reviews_added_7d_abs": None,
        "delta_reviews_added_7d_pct": None,
        "delta_period_positive_ratio_7d_pp": None,
        "delta_reviews_added_30d_abs": None,
        "delta_reviews_added_30d_pct": None,
        "delta_period_positive_ratio_30d_pp": None,
        "price_bucket_time": None,
        "region": None,
        "currency_code": None,
        "initial_price_minor": None,
        "final_price_minor": None,
        "discount_percent": None,
        "is_free": None,
    }

    mapped = explore_service.to_response_record(row)

    assert mapped["canonical_game_id"] == 77
    assert mapped["steam_appid"] is None
    assert mapped["current_ccu"] is None
    assert mapped["current_ccu_missing_flag"] is True
    assert mapped["period_avg_ccu_7d"] is None
    assert mapped["estimated_player_hours_7d"] is None
    assert mapped["reviews_added_7d"] is None
    assert mapped["period_positive_ratio_7d"] is None
    assert mapped["delta_reviews_added_7d_abs"] is None
    assert mapped["delta_period_positive_ratio_30d_pp"] is None
    assert mapped["final_price_minor"] is None
    assert mapped["is_free"] is None


def test_to_response_record_maps_non_finite_float_evidence_to_null() -> None:
    row = sample_response_record(77)
    row["current_delta_ccu_pct"] = float("nan")
    row["delta_period_avg_ccu_7d_abs"] = "NaN"
    row["delta_period_avg_ccu_7d_pct"] = "Infinity"
    row["estimated_player_hours_7d"] = float("inf")
    row["delta_period_positive_ratio_7d_pp"] = "-Infinity"

    mapped = explore_service.to_response_record(row)

    assert mapped["current_delta_ccu_pct"] is None
    assert mapped["delta_period_avg_ccu_7d_abs"] is None
    assert mapped["delta_period_avg_ccu_7d_pct"] is None
    assert mapped["estimated_player_hours_7d"] is None
    assert mapped["delta_period_positive_ratio_7d_pp"] is None


def test_list_explore_overview_executes_view_query(monkeypatch) -> None:
    captured: dict[str, object] = {}
    dict_row_sentinel = object()
    rows = [
        {
            "canonical_game_id": "77",
            "canonical_name": "game-77",
            "steam_appid": "730",
            "ccu_bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
            "current_ccu": "1200",
            "current_delta_ccu_abs": "200",
            "current_delta_ccu_pct": "20.0",
            "current_ccu_missing_flag": False,
            "ccu_period_anchor_date": dt.date(2026, 3, 29),
            "period_avg_ccu_7d": "1100.5",
            "period_peak_ccu_7d": "1800",
            "delta_period_avg_ccu_7d_abs": "100.5",
            "delta_period_avg_ccu_7d_pct": "10.05",
            "delta_period_peak_ccu_7d_abs": "300",
            "delta_period_peak_ccu_7d_pct": "20.0",
            "estimated_player_hours_7d": "92400.0",
            "delta_estimated_player_hours_7d_abs": "8400.0",
            "delta_estimated_player_hours_7d_pct": "10.0",
            "reviews_snapshot_date": dt.date(2026, 3, 29),
            "total_reviews": "1000",
            "total_positive": "820",
            "total_negative": "180",
            "positive_ratio": "0.82",
            "reviews_added_7d": "70",
            "reviews_added_30d": "250",
            "period_positive_ratio_7d": "0.8",
            "period_positive_ratio_30d": "0.84",
            "delta_reviews_added_7d_abs": "20",
            "delta_reviews_added_7d_pct": "40.0",
            "delta_period_positive_ratio_7d_pp": "5.0",
            "delta_reviews_added_30d_abs": "50",
            "delta_reviews_added_30d_pct": "25.0",
            "delta_period_positive_ratio_30d_pp": "-2.0",
            "price_bucket_time": dt.datetime(2026, 3, 29, 14, 0, tzinfo=KST),
            "region": "KR",
            "currency_code": "KRW",
            "initial_price_minor": "4200000",
            "final_price_minor": "3360000",
            "discount_percent": "20",
            "is_free": None,
        }
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

    monkeypatch.setattr(
        explore_service,
        "require_psycopg",
        lambda: (FakePsycopg, dict_row_sentinel),
    )
    monkeypatch.setattr(explore_service, "build_pg_conninfo_from_env", lambda: "fake")

    result = explore_service.list_explore_overview(limit=10)

    assert captured["conninfo"] == "fake"
    assert captured["row_factory"] is dict_row_sentinel
    assert captured["sql"] == explore_service.LIST_EXPLORE_OVERVIEW_SQL
    assert captured["params"] == (10,)
    assert result == [sample_response_record(77)]
