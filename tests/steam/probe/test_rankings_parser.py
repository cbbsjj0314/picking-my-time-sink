from __future__ import annotations

import json
from pathlib import Path

import pytest

from steam.probe.probe_rankings import (
    infer_title_from_chunks,
    parse_rankings_html,
    parse_rankings_payload,
)

FIXTURE_DIR = Path("tests/fixtures/steam/rankings")
README_PATH = FIXTURE_DIR / "README.md"
LEGACY_EMPTY_CHART_FIXTURE = FIXTURE_DIR / "legacy_empty_chart.html"
PAYLOAD_CASES = (
    ("topsellers_global.payload.json", "topsellers", "global", 3764200, "Resident Evil Requiem"),
    ("topsellers_kr.payload.json", "topsellers", "KR", 578080, "PUBG: BATTLEGROUNDS"),
    ("mostplayed_global.payload.json", "mostplayed", "global", 730, "Counter-Strike 2"),
    ("mostplayed_kr.payload.json", "mostplayed", "KR", 730, "Counter-Strike 2"),
)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_row_contract(rows: list[dict[str, int | str]]) -> None:
    assert rows
    assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))
    assert all(set(row.keys()) == {"rank", "app_id", "title"} for row in rows)
    assert all(isinstance(row["app_id"], int) for row in rows)
    assert all(isinstance(row["title"], str) and row["title"].strip() for row in rows)


def test_parse_rankings_html_extracts_unique_rows() -> None:
    html = """
    <html>
      <body>
        <a href="https://store.steampowered.com/app/730/Counter-Strike_2/">1 Counter-Strike 2</a>
        <a href="/app/570/Dota_2/">#2 Dota 2</a>
        <a href="/app/730/Counter-Strike_2/">duplicate entry</a>
        <a href="/app/10/">3</a>
      </body>
    </html>
    """

    rows = parse_rankings_html(html, max_rows=100)

    assert [row["app_id"] for row in rows] == [730, 570, 10]
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert rows[0]["title"] == "Counter-Strike 2"
    assert rows[1]["title"] == "Dota 2"
    assert rows[2]["title"] == "app_10"


def test_infer_title_uses_slug_when_text_is_only_rank() -> None:
    title = infer_title_from_chunks(chunks=["1"], slug="PUBG_BATTLEGROUNDS", app_id=578080)
    assert title == "PUBG BATTLEGROUNDS"


def test_parse_rankings_html_respects_max_rows() -> None:
    html = """
    <a href="/app/730/Counter-Strike_2/">Counter-Strike 2</a>
    <a href="/app/570/Dota_2/">Dota 2</a>
    <a href="/app/440/Team_Fortress_2/">Team Fortress 2</a>
    """

    rows = parse_rankings_html(html, max_rows=2)

    assert len(rows) == 2
    assert rows[-1]["app_id"] == 570


def test_legacy_empty_chart_fixture_still_parses_to_empty_rows() -> None:
    excerpt = LEGACY_EMPTY_CHART_FIXTURE.read_text(encoding="utf-8")

    rows = parse_rankings_html(excerpt, max_rows=100)

    assert rows == []


@pytest.mark.parametrize(
    ("fixture_name", "target", "region", "expected_app_id", "expected_title"),
    PAYLOAD_CASES,
)
def test_parse_rankings_payload_fixtures_extract_rows(
    fixture_name: str,
    target: str,
    region: str,
    expected_app_id: int,
    expected_title: str,
) -> None:
    payload = _load_json(FIXTURE_DIR / fixture_name)

    rows = parse_rankings_payload(payload, max_rows=10)

    _assert_row_contract(rows)
    assert rows[0]["app_id"] == expected_app_id
    assert rows[0]["title"] == expected_title
    assert target in fixture_name
    assert region.lower() in fixture_name.lower()


@pytest.mark.parametrize("fixture_name", [case[0] for case in PAYLOAD_CASES])
def test_payload_fixtures_keep_title_source_data(fixture_name: str) -> None:
    payload = _load_json(FIXTURE_DIR / fixture_name)
    ranks = payload["response"]["ranks"]

    assert ranks
    assert isinstance(ranks[0]["rank"], int)
    assert isinstance(ranks[0]["appid"], int)
    assert isinstance(ranks[0]["item"]["name"], str)
    assert ranks[0]["item"]["name"].strip()


def test_rankings_fixture_readme_tracks_target_metadata() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    for fixture_name, target, region, _, _ in PAYLOAD_CASES:
        assert fixture_name in readme
        assert f"target={target}" in readme
        assert f"region={region}" in readme
