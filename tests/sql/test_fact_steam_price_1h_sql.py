from __future__ import annotations

from pathlib import Path

DDL_PATH = Path("sql/postgres/012_fact_steam_price_1h.sql")


def test_price_fact_allows_grounded_free_rows_without_fake_numeric_fields() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "currency_code text null" in sql
    assert "initial_price_minor integer null" in sql
    assert "final_price_minor integer null" in sql
    assert "discount_percent integer null" in sql
    assert "constraint fact_steam_price_1h_price_evidence_shape" in sql
    assert "is_free is true" in sql
    assert "currency_code is null" in sql
    assert "initial_price_minor is null" in sql
    assert "final_price_minor is null" in sql
    assert "discount_percent is null" in sql


def test_price_fact_blocks_paid_partial_rows() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8").lower()

    assert "is_free is distinct from true" in sql
    assert "currency_code is not null" in sql
    assert "initial_price_minor is not null" in sql
    assert "final_price_minor is not null" in sql
    assert "discount_percent is not null" in sql
