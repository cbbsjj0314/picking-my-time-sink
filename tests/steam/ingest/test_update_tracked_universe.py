from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import pytest

from steam.ingest.app_catalog_latest_summary import build_latest_summary, write_latest_summary
from steam.ingest.update_tracked_universe import (
    DEFAULT_APP_CATALOG_PATH,
    DEFAULT_RESULT_PATH,
    DEFAULT_SEED_SOURCES,
    CandidateObservation,
    MappingSnapshot,
    MergedCandidate,
    build_parser,
    build_result_row,
    format_utc_iso,
    load_optional_catalog_metadata,
    load_required_rankings_observations,
    merge_candidate_observations,
    process_candidate,
    resolve_seed_sources,
    validate_candidate,
)
from steam.probe.probe_rankings import (
    DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    DEFAULT_MOSTPLAYED_KR_PATH,
    DEFAULT_TOPSELLERS_GLOBAL_PATH,
    DEFAULT_TOPSELLERS_KR_PATH,
)


def make_candidate(
    *,
    steam_appid: int = 730,
    selected_title: str = "Counter-Strike 2",
    selected_source_label: str = "steam_rank_topsellers_kr",
    market: str = "kr",
    rank_type: str = "top_selling",
    priority: int = 1,
    sources: tuple[str, ...] = ("steam_rank_topsellers_kr",),
) -> MergedCandidate:
    return MergedCandidate(
        steam_appid=steam_appid,
        selected_title=selected_title,
        selected_source_label=selected_source_label,
        market=market,
        rank_type=rank_type,
        priority=priority,
        sources=sources,
    )


def test_default_seed_source_table_is_explicit_and_stable() -> None:
    actual = [
        (item.source_label, item.market, item.rank_type, item.default_priority)
        for item in DEFAULT_SEED_SOURCES
    ]
    assert actual == [
        ("steam_rank_topsellers_kr", "kr", "top_selling", 1),
        ("steam_rank_topsellers_global", "global", "top_selling", 2),
        ("steam_rank_mostplayed_kr", "kr", "top_played", 3),
        ("steam_rank_mostplayed_global", "global", "top_played", 4),
    ]


def test_build_parser_uses_runtime_default_paths() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.topsellers_global_path == DEFAULT_TOPSELLERS_GLOBAL_PATH
    assert args.topsellers_kr_path == DEFAULT_TOPSELLERS_KR_PATH
    assert args.mostplayed_global_path == DEFAULT_MOSTPLAYED_GLOBAL_PATH
    assert args.mostplayed_kr_path == DEFAULT_MOSTPLAYED_KR_PATH
    assert args.app_catalog_path == DEFAULT_APP_CATALOG_PATH
    assert args.result_path == DEFAULT_RESULT_PATH


def test_resolve_seed_sources_applies_cli_overrides() -> None:
    sources = resolve_seed_sources(
        topsellers_kr_path=Path("a.json"),
        topsellers_global_path=Path("b.json"),
        mostplayed_kr_path=Path("c.json"),
        mostplayed_global_path=Path("d.json"),
    )

    assert [item.payload_path for item in sources] == [
        Path("a.json"),
        Path("b.json"),
        Path("c.json"),
        Path("d.json"),
    ]


def test_required_payload_zero_candidates_fails_with_source_name(tmp_path: Path) -> None:
    valid_payload = {
        "response": {
            "ranks": [
                {
                    "appid": 730,
                    "rank": 1,
                    "item": {"name": "Counter-Strike 2"},
                }
            ]
        }
    }
    empty_payload = {"response": {"ranks": []}}

    topsellers_kr = tmp_path / "topsellers_kr.json"
    topsellers_global = tmp_path / "topsellers_global.json"
    mostplayed_kr = tmp_path / "mostplayed_kr.json"
    mostplayed_global = tmp_path / "mostplayed_global.json"
    topsellers_kr.write_text(json.dumps(valid_payload), encoding="utf-8")
    topsellers_global.write_text(json.dumps(valid_payload), encoding="utf-8")
    mostplayed_kr.write_text(json.dumps(empty_payload), encoding="utf-8")
    mostplayed_global.write_text(json.dumps(valid_payload), encoding="utf-8")

    sources = resolve_seed_sources(
        topsellers_kr_path=topsellers_kr,
        topsellers_global_path=topsellers_global,
        mostplayed_kr_path=mostplayed_kr,
        mostplayed_global_path=mostplayed_global,
    )

    with pytest.raises(ValueError, match="steam_rank_mostplayed_kr"):
        load_required_rankings_observations(sources)


def test_optional_catalog_metadata_none_is_quiet_and_non_blocking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="steam.ingest.update_tracked_universe"):
        metadata = load_optional_catalog_metadata(None)

    assert metadata == {
        "app_count": None,
        "pagination": {},
        "snapshot_path": None,
        "top_level_keys": [],
    }
    assert not caplog.records


def test_optional_catalog_metadata_missing_is_non_blocking(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    missing_path = tmp_path / "missing.json"

    with caplog.at_level(logging.WARNING, logger="steam.ingest.update_tracked_universe"):
        metadata = load_optional_catalog_metadata(missing_path)

    assert metadata == {
        "app_count": None,
        "pagination": {},
        "snapshot_path": None,
        "top_level_keys": [],
    }
    assert f"Optional App Catalog summary missing: {missing_path}" in caplog.text


def test_optional_catalog_metadata_runtime_latest_summary_extracts_summary(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "latest.summary.json"
    write_latest_summary(
        summary_path,
        build_latest_summary(
            job_name="fetch_app_catalog_weekly",
            started_at_utc="2026-03-31T00:00:00Z",
            finished_at_utc="2026-03-31T00:01:00Z",
            snapshot_path=tmp_path / "snapshot.jsonl",
            rows=[
                {"appid": 10, "last_modified": 1, "name": "Ten", "price_change_number": None},
                {
                    "appid": 20,
                    "last_modified": 2,
                    "name": "Twenty",
                    "price_change_number": None,
                },
            ],
        ),
    )

    metadata = load_optional_catalog_metadata(summary_path)
    assert metadata["app_count"] == 2
    assert metadata["pagination"] == {"have_more_results": False}
    assert metadata["snapshot_path"] == str(tmp_path / "snapshot.jsonl")
    assert metadata["top_level_keys"] == ["apps", "have_more_results"]


def test_optional_catalog_metadata_explicit_probe_sample_still_extracts_summary() -> None:
    metadata = load_optional_catalog_metadata(
        Path("docs/probe/steam/getapplist/representative.json")
    )
    assert metadata["app_count"] == 10000
    assert metadata["pagination"] == {"have_more_results": True, "last_appid": 507030}
    assert metadata["snapshot_path"] is None
    assert metadata["top_level_keys"] == ["apps", "have_more_results", "last_appid"]


def test_merge_candidate_observations_normalizes_duplicate_appids() -> None:
    merged = merge_candidate_observations(
        [
            CandidateObservation(
                steam_appid=int("730"),
                title="Counter-Strike 2",
                source_label="steam_rank_topsellers_kr",
                market="kr",
                rank_type="top_selling",
                default_priority=1,
            ),
            CandidateObservation(
                steam_appid=730,
                title="Counter-Strike 2",
                source_label="steam_rank_topsellers_global",
                market="global",
                rank_type="top_selling",
                default_priority=2,
            ),
        ]
    )

    assert merged[0].steam_appid == 730
    assert merged[0].priority == 1
    assert merged[0].sources == (
        "steam_rank_topsellers_global",
        "steam_rank_topsellers_kr",
    )


def test_validate_candidate_requires_title_for_new_dim_game_only() -> None:
    weak_candidate = make_candidate(selected_title="   ")

    assert (
        validate_candidate(weak_candidate, has_resolved_mapping=False)
        == "missing_title_for_new_dim_game"
    )
    assert validate_candidate(weak_candidate, has_resolved_mapping=True) is None


def test_build_result_row_uses_fixed_schema() -> None:
    run_seen_at = format_utc_iso(dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.UTC))
    row = build_result_row(
        candidate=make_candidate(
            sources=("steam_rank_topsellers_global", "steam_rank_topsellers_kr")
        ),
        run_seen_at_iso=run_seen_at,
        tracked_action="skipped",
        skip_reason="missing_title_for_new_dim_game",
        canonical_game_id=None,
        canonical_name=None,
        is_active=None,
        created_dim_game=None,
        attached_mapping=None,
    )

    assert row == {
        "attached_mapping": None,
        "canonical_game_id": None,
        "canonical_name": None,
        "created_dim_game": None,
        "is_active": None,
        "market": "kr",
        "priority": 1,
        "rank_type": "top_selling",
        "run_seen_at": run_seen_at,
        "selected_source_label": "steam_rank_topsellers_kr",
        "skip_reason": "missing_title_for_new_dim_game",
        "sources": ["steam_rank_topsellers_global", "steam_rank_topsellers_kr"],
        "steam_appid": 730,
        "tracked_action": "skipped",
    }


def test_process_candidate_reused_resolved_mapping_updates_mapping_last_seen_and_tracked_game(
) -> None:
    run_seen_at = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.UTC)
    calls: list[tuple[str, object]] = []
    unlocked = MappingSnapshot(730, 1, "Counter-Strike 2", True)
    locked = MappingSnapshot(730, 1, "Counter-Strike 2", True)

    def fetch_mapping(steam_appid: int, *, for_update: bool) -> MappingSnapshot:
        calls.append(("fetch", (steam_appid, for_update)))
        return locked if for_update else unlocked

    result = process_candidate(
        make_candidate(),
        run_seen_at=run_seen_at,
        fetch_mapping=fetch_mapping,
        insert_mapping_placeholder=lambda steam_appid, seen_at: calls.append(
            ("placeholder", steam_appid)
        ),
        update_mapping_last_seen=lambda steam_appid, seen_at: calls.append(
            ("touch_last_seen", (steam_appid, seen_at))
        ),
        insert_dim_game=lambda canonical_name: 999,
        attach_mapping=lambda steam_appid, canonical_game_id, seen_at: calls.append(
            ("attach", canonical_game_id)
        ),
        upsert_tracked_game=lambda canonical_game_id, priority, sources, seen_at: calls.append(
            ("upsert_tracked_game", (canonical_game_id, priority, tuple(sources), seen_at))
        ),
    )

    assert result["tracked_action"] == "updated"
    assert ("touch_last_seen", (730, run_seen_at)) in calls
    assert ("upsert_tracked_game", (1, 1, ("steam_rank_topsellers_kr",), run_seen_at)) in calls
    assert all(call[0] != "placeholder" for call in calls)


def test_process_candidate_invalid_unmapped_candidate_skips_without_db_writes() -> None:
    run_seen_at = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.UTC)
    calls: list[str] = []

    result = process_candidate(
        make_candidate(selected_title="   "),
        run_seen_at=run_seen_at,
        fetch_mapping=lambda steam_appid, for_update=False: None,
        insert_mapping_placeholder=lambda steam_appid, seen_at: calls.append("placeholder"),
        update_mapping_last_seen=lambda steam_appid, seen_at: calls.append("touch_last_seen"),
        insert_dim_game=lambda canonical_name: 1,
        attach_mapping=lambda steam_appid, canonical_game_id, seen_at: calls.append("attach"),
        upsert_tracked_game=lambda canonical_game_id, priority, sources, seen_at: calls.append(
            "upsert_tracked_game"
        ),
    )

    assert result["tracked_action"] == "skipped"
    assert result["skip_reason"] == "missing_title_for_new_dim_game"
    assert calls == []


def test_process_candidate_first_seen_attach_path_is_inserted_and_sets_debug_flags() -> None:
    run_seen_at = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.UTC)
    calls: list[tuple[str, object]] = []
    states = iter(
        [
            None,
            MappingSnapshot(730, None, None, False),
            MappingSnapshot(730, 22, "Counter-Strike 2", False),
        ]
    )

    def fetch_mapping(steam_appid: int, *, for_update: bool) -> MappingSnapshot | None:
        calls.append(("fetch", (steam_appid, for_update)))
        return next(states)

    result = process_candidate(
        make_candidate(),
        run_seen_at=run_seen_at,
        fetch_mapping=fetch_mapping,
        insert_mapping_placeholder=lambda steam_appid, seen_at: calls.append(
            ("placeholder", (steam_appid, seen_at))
        ),
        update_mapping_last_seen=lambda steam_appid, seen_at: calls.append(
            ("touch_last_seen", (steam_appid, seen_at))
        ),
        insert_dim_game=lambda canonical_name: calls.append(
            ("insert_dim_game", canonical_name)
        )
        or 22,
        attach_mapping=lambda steam_appid, canonical_game_id, seen_at: calls.append(
            ("attach", (steam_appid, canonical_game_id, seen_at))
        ),
        upsert_tracked_game=lambda canonical_game_id, priority, sources, seen_at: calls.append(
            ("upsert_tracked_game", (canonical_game_id, priority, tuple(sources), seen_at))
        ),
    )

    assert result["tracked_action"] == "inserted"
    assert result["created_dim_game"] is True
    assert result["attached_mapping"] is True
    assert ("insert_dim_game", "Counter-Strike 2") in calls
    assert any(call[0] == "attach" for call in calls)


def test_process_candidate_reuses_mapping_after_attach_conflict() -> None:
    run_seen_at = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.UTC)
    states = iter(
        [
            None,
            MappingSnapshot(730, None, None, False),
            MappingSnapshot(730, 44, "Counter-Strike 2", True),
        ]
    )
    calls: list[str] = []

    def fetch_mapping(steam_appid: int, *, for_update: bool) -> MappingSnapshot | None:
        return next(states)

    def raise_conflict(steam_appid: int, canonical_game_id: int, seen_at: dt.datetime) -> None:
        from steam.ingest.update_tracked_universe import MappingAttachConflict

        raise MappingAttachConflict("conflict")

    result = process_candidate(
        make_candidate(),
        run_seen_at=run_seen_at,
        fetch_mapping=fetch_mapping,
        insert_mapping_placeholder=lambda steam_appid, seen_at: calls.append("placeholder"),
        update_mapping_last_seen=lambda steam_appid, seen_at: calls.append("touch"),
        insert_dim_game=lambda canonical_name: 44,
        attach_mapping=raise_conflict,
        upsert_tracked_game=lambda canonical_game_id, priority, sources, seen_at: calls.append(
            "upsert"
        ),
    )

    assert result["tracked_action"] == "updated"
    assert result["attached_mapping"] is False
    assert calls == ["placeholder", "touch", "upsert"]
