from __future__ import annotations

from steam.probe.probe_rankings import infer_title_from_chunks, parse_rankings_html


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
