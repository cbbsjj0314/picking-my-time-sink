from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.routers.combined import CombinedGameActivityResponse
from api.services import combined_service

FIELDS = {
    "canonical_game_id", "canonical_name", "steam_appid", "ccu_period_anchor_date",
    "period_avg_ccu_7d", "period_peak_ccu_7d", "chzzk_mapped_category_count",
    "chzzk_viewer_hours_observed_7d", "chzzk_peak_viewers_observed_7d",
    "chzzk_observed_bucket_count_7d", "chzzk_collection_bucket_count_7d",
    "chzzk_observation_ratio_7d", "chzzk_latest_observed_bucket_7d", "bounded_sample_caveat",
}


def sample_row():
    return {
        "canonical_game_id": 1, "canonical_name": "Synthetic Game", "steam_appid": 100,
        "ccu_period_anchor_date": dt.date(2026, 10, 3),
        "period_avg_ccu_7d": Decimal("100.5"), "period_peak_ccu_7d": 200,
        "chzzk_mapped_category_count": 2,
        "chzzk_viewer_hours_observed_7d": Decimal("17"),
        "chzzk_peak_viewers_observed_7d": 30, "chzzk_observed_bucket_count_7d": 2,
        "chzzk_collection_bucket_count_7d": 3, "chzzk_observation_ratio_7d": 2 / 3,
        "chzzk_latest_observed_bucket_7d": dt.datetime.fromisoformat("2026-10-01T00:30:00+09:00"),
        "bounded_sample_caveat": "bounded_sample",
    }


def test_activity_route_exposes_exact_shape_and_serializes_persisted_values(monkeypatch):
    limits = []

    def fetch(limit):
        limits.append(limit)
        return [{**sample_row(), "reviewed_by": "excluded", "candidate_id": "excluded"}]

    monkeypatch.setattr(combined_service, "list_game_activity", fetch)
    response = TestClient(app).get("/combined/games/activity?limit=25")
    assert response.status_code == 200
    assert limits == [25]
    row = response.json()[0]
    assert set(row) == FIELDS == set(CombinedGameActivityResponse.model_fields)
    assert row["ccu_period_anchor_date"] == "2026-10-03"
    assert row["period_avg_ccu_7d"] == 100.5
    assert row["chzzk_viewer_hours_observed_7d"] == 17
    assert row["chzzk_latest_observed_bucket_7d"] == "2026-10-01T00:30:00+09:00"
    assert row["bounded_sample_caveat"] == "bounded_sample"


@pytest.mark.parametrize("observed,collection,ratio,value", [
    (None, None, None, None), (0, 0, None, None), (0, 3, 0, None), (1, 1, 1, 0),
])
def test_activity_preserves_unknown_missing_and_observed_zero(
    monkeypatch, observed, collection, ratio, value,
):
    row = sample_row()
    row.update({
        "chzzk_observed_bucket_count_7d": observed,
        "chzzk_collection_bucket_count_7d": collection,
        "chzzk_observation_ratio_7d": ratio,
        "chzzk_viewer_hours_observed_7d": value,
        "chzzk_peak_viewers_observed_7d": value,
    })
    if not observed:
        row["chzzk_latest_observed_bucket_7d"] = None
    if observed is None:
        row["ccu_period_anchor_date"] = None
        row["period_avg_ccu_7d"] = None
        row["period_peak_ccu_7d"] = None
    monkeypatch.setattr(combined_service, "list_game_activity", lambda limit: [row])
    response = TestClient(app).get("/combined/games/activity")
    assert response.status_code == 200
    result = response.json()[0]
    for field, expected in row.items():
        if expected is None or isinstance(expected, int):
            assert result[field] == expected
    assert result["chzzk_observation_ratio_7d"] == ratio


@pytest.mark.parametrize("limit", ["0", "201", "-1", "invalid"])
def test_activity_limit_validation_does_not_query_db(monkeypatch, limit):
    def unexpected(**kwargs):
        pytest.fail("Invalid transport limit must not query DB")
    monkeypatch.setattr(combined_service, "list_game_activity", unexpected)
    assert TestClient(app).get(f"/combined/games/activity?limit={limit}").status_code == 422


def test_activity_service_only_queries_activity_view_with_transport_order(monkeypatch):
    captured = {}
    row = sample_row()

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            captured["query"] = (sql, params)

        def fetchall(self):
            return [row]

    class FakeConnection(FakeCursor):
        def cursor(self, row_factory):
            return FakeCursor()

    class FakePsycopg:
        @staticmethod
        def connect(*, conninfo):
            assert conninfo == "synthetic"
            return FakeConnection()

    monkeypatch.setattr(combined_service, "require_psycopg", lambda: (FakePsycopg, object()))
    monkeypatch.setattr(combined_service, "build_pg_conninfo_from_env", lambda: "synthetic")
    assert combined_service.list_game_activity(12) == [row]
    sql = combined_service.LIST_COMBINED_GAME_ACTIVITY_SQL
    assert captured["query"] == (sql, (12,))
    assert set(sql.split("SELECT", 1)[1].split("FROM", 1)[0].replace("\n", "").replace(
        " ", ""
    ).split(",")) == FIELDS
    assert "FROM srv_combined_game_activity_7d\nORDER BY canonical_game_id ASC\nLIMIT %s" in sql
    assert "join" not in sql.lower()
