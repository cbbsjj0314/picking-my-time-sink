from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "view_path",
    [
        Path("sql/postgres/020_srv_game_latest_ccu.sql"),
        Path("sql/postgres/021_srv_game_latest_reviews.sql"),
        Path("sql/postgres/022_srv_game_latest_price.sql"),
    ],
)
def test_latest_game_serving_views_pin_active_tracked_universe(view_path: Path) -> None:
    sql = view_path.read_text(encoding="utf-8").lower()

    assert "with active_games as" in sql
    assert "from tracked_game as tg" in sql
    assert "where tg.is_active = true" in sql
