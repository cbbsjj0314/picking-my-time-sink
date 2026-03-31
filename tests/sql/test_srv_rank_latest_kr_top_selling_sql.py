from __future__ import annotations

from pathlib import Path

VIEW_PATH = Path("sql/postgres/023_srv_rank_latest_kr_top_selling.sql")


def test_latest_rank_view_pins_fixed_kr_top_selling_slice() -> None:
    sql = VIEW_PATH.read_text(encoding="utf-8").lower()

    assert "create or replace view srv_rank_latest_kr_top_selling" in sql
    assert "max(snapshot_date)" in sql
    assert "where market = 'kr'" in sql
    assert "and rank_type = 'top_selling'" in sql
