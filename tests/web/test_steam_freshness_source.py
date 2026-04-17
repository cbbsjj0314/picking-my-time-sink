from __future__ import annotations

from pathlib import Path

STEAM_VIEW_MODEL_PATH = Path("web/src/lib/steamViewModel.ts")
STEAM_EXPLORE_VIEW_MODEL_PATH = Path("web/src/lib/steamExploreViewModel.ts")
STEAM_EXPLORE_TABLE_PATH = Path("web/src/components/SteamExploreTable.tsx")


def test_steam_detail_view_surfaces_latest_evidence_timestamps() -> None:
    source = STEAM_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "rankingSnapshotDate: string | null" in source
    assert "rankingSnapshotDate: row.snapshot_date" in source
    assert "Snapshot ${formatSnapshotDate(row.rankingSnapshotDate)}" in source
    assert "label: 'CCU snapshot'" in source
    assert "formatSnapshotDateTime(row.ccu.bucket_time)" in source
    assert "label: 'Review snapshot'" in source
    assert "formatSnapshotDate(row.reviews.snapshot_date)" in source
    assert "label: 'Price snapshot'" in source
    assert "formatSnapshotDateTime(row.price.bucket_time)" in source


def test_explore_view_model_keeps_nulls_and_timestamp_fields_grounded() -> None:
    source = STEAM_EXPLORE_VIEW_MODEL_PATH.read_text(encoding="utf-8")

    assert "const EMPTY_CELL = '-'" in source
    assert "currentCcuLabel: formatOptionalInteger(row.current_ccu)" in source
    assert "currentCcuTitle: formatKstDateTime(row.ccu_bucket_time)" in source
    assert "ccuAnchorLabel: formatKstDate(row.ccu_period_anchor_date)" in source
    assert "reviewAnchorLabel: formatKstDate(row.reviews_snapshot_date)" in source
    assert "priceTitle: formatKstDateTime(row.price_bucket_time)" in source


def test_explore_table_summarizes_freshness_without_fake_fallback() -> None:
    source = STEAM_EXPLORE_TABLE_PATH.read_text(encoding="utf-8")

    assert "getUniformEvidenceLabel" in source
    assert "return `${label} mixed snapshots`" in source
    assert "Current CCU" in source
    assert "CCU period anchor" in source
    assert "Reviews anchor" in source
    assert "Price snapshot" in source
    assert "freshnessLabels.join(' · ')" in source
