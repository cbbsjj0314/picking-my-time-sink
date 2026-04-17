from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from steam.normalize import payload_to_gold_rankings
from steam.normalize.payload_to_gold_rankings import (
    RankingPayloadSource,
    process_payload_sources,
)

FIXTURE_DIR = Path("tests/fixtures/steam/rankings")


class FakeFactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str, int], dict[str, Any]] = {}

    def upsert(
        self,
        snapshot_date,
        market: str,
        rank_type: str,
        rank_position: int,
        steam_appid: int,
        canonical_game_id: int | None,
        collected_at,
    ) -> None:
        key = (snapshot_date.isoformat(), market, rank_type, rank_position)
        self.rows[key] = {
            "canonical_game_id": canonical_game_id,
            "collected_at": collected_at.isoformat().replace("+00:00", "Z"),
            "steam_appid": steam_appid,
        }


def copy_fixture_with_mtime(tmp_path: Path, fixture_name: str, *, timestamp: float) -> Path:
    destination = tmp_path / fixture_name
    fixture_text = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    destination.write_text(fixture_text, encoding="utf-8")
    os.utime(destination, (timestamp, timestamp))
    return destination


def test_process_payload_sources_is_idempotent_for_same_input(tmp_path: Path) -> None:
    collected_at = dt.datetime(2026, 3, 9, 18, 42, 39, tzinfo=dt.UTC)
    timestamp = collected_at.timestamp()
    payload_sources = (
        RankingPayloadSource(
            payload_path=copy_fixture_with_mtime(
                tmp_path,
                "topsellers_kr.payload.json",
                timestamp=timestamp,
            ),
            market="kr",
            rank_type="top_selling",
        ),
        RankingPayloadSource(
            payload_path=copy_fixture_with_mtime(
                tmp_path,
                "mostplayed_kr.payload.json",
                timestamp=timestamp,
            ),
            market="kr",
            rank_type="top_played",
        ),
    )
    store = FakeFactStore()
    mapping_by_steam_appid = {
        570: 2,
        730: 1,
        578080: 3,
    }

    first_results = process_payload_sources(
        payload_sources,
        mapping_by_steam_appid=mapping_by_steam_appid,
        upsert_row=store.upsert,
        max_rows=2,
    )
    second_results = process_payload_sources(
        payload_sources,
        mapping_by_steam_appid=mapping_by_steam_appid,
        upsert_row=store.upsert,
        max_rows=2,
    )

    assert len(store.rows) == 4
    assert first_results[0]["snapshot_date"] == "2026-03-10"
    assert first_results[0]["market"] == "kr"
    assert first_results[0]["rank_type"] == "top_selling"
    assert second_results[2]["rank_type"] == "top_played"

    topsellers_key = ("2026-03-10", "kr", "top_selling", 1)
    mostplayed_key = ("2026-03-10", "kr", "top_played", 1)
    assert store.rows[topsellers_key]["steam_appid"] == 578080
    assert store.rows[topsellers_key]["canonical_game_id"] == 3
    assert store.rows[mostplayed_key]["steam_appid"] == 730
    assert store.rows[mostplayed_key]["canonical_game_id"] == 1


def test_process_payload_sources_keeps_null_mapping_for_unresolved_appid(tmp_path: Path) -> None:
    collected_at = dt.datetime(2026, 3, 9, 18, 42, 39, tzinfo=dt.UTC)
    payload_path = copy_fixture_with_mtime(
        tmp_path,
        "topsellers_global.payload.json",
        timestamp=collected_at.timestamp(),
    )
    payload_sources = (
        RankingPayloadSource(
            payload_path=payload_path,
            market="global",
            rank_type="top_selling",
        ),
    )
    store = FakeFactStore()

    results = process_payload_sources(
        payload_sources,
        mapping_by_steam_appid={730: 1},
        upsert_row=store.upsert,
        max_rows=1,
    )

    assert results == [
        {
            "canonical_game_id": None,
            "market": "global",
            "rank_position": 1,
            "rank_type": "top_selling",
            "snapshot_date": "2026-03-10",
            "steam_appid": 3764200,
        }
    ]
    assert store.rows[("2026-03-10", "global", "top_selling", 1)]["canonical_game_id"] is None


def test_run_writes_result_and_meta_paths(tmp_path: Path, monkeypatch) -> None:
    timestamp = dt.datetime(2026, 3, 9, 18, 42, 39, tzinfo=dt.UTC).timestamp()
    topsellers_kr_path = copy_fixture_with_mtime(
        tmp_path,
        "topsellers_kr.payload.json",
        timestamp=timestamp,
    )
    topsellers_global_path = copy_fixture_with_mtime(
        tmp_path,
        "topsellers_global.payload.json",
        timestamp=timestamp,
    )
    mostplayed_kr_path = copy_fixture_with_mtime(
        tmp_path,
        "mostplayed_kr.payload.json",
        timestamp=timestamp,
    )
    mostplayed_global_path = copy_fixture_with_mtime(
        tmp_path,
        "mostplayed_global.payload.json",
        timestamp=timestamp,
    )
    result_path = tmp_path / "rankings-result.jsonl"
    meta_path = tmp_path / "rankings.meta.json"

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            del sql, params

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    class FakePsycopg:
        @staticmethod
        def connect(*, conninfo: str) -> FakeConnection:
            assert conninfo == "fake"
            return FakeConnection()

    monkeypatch.setattr(payload_to_gold_rankings, "require_psycopg", lambda: FakePsycopg)
    monkeypatch.setattr(
        payload_to_gold_rankings,
        "build_pg_conninfo_from_env",
        lambda: "fake",
    )
    monkeypatch.setattr(
        payload_to_gold_rankings,
        "load_canonical_mapping_by_steam_appid",
        lambda conn: {},
    )

    results = payload_to_gold_rankings.run(
        topsellers_kr_path=topsellers_kr_path,
        topsellers_global_path=topsellers_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
        mostplayed_global_path=mostplayed_global_path,
        result_path=result_path,
        meta_path=meta_path,
        max_rows=1,
    )

    assert len(results) == 4
    assert result_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["job_name"] == "payload_to_gold_rankings"
    assert meta["success"] is True
    assert meta["records_out"] == 4
