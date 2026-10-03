"""Combined source API routes."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.services import combined_service

router = APIRouter(prefix="/combined", tags=["combined"])

COMBINED_GAME_OVERVIEW_LIMIT_QUERY = Query(default=50, ge=1, le=200)
COMBINED_GAME_ACTIVITY_LIMIT_QUERY = Query(default=50, ge=1, le=200)


class CombinedGameOverviewResponse(BaseModel):
    """Minimal backend-only Combined overview row."""

    canonical_game_id: int
    canonical_name: str
    steam_appid: int | None
    steam_source_available: bool
    chzzk_mapping_available: bool
    chzzk_category_id: str | None
    category_name: str | None
    category_type: str | None
    latest_bucket_time: dt.datetime | None


@router.get("/games/overview", response_model=list[CombinedGameOverviewResponse])
def list_combined_games_overview(
    limit: int = COMBINED_GAME_OVERVIEW_LIMIT_QUERY,
) -> list[CombinedGameOverviewResponse]:
    """Return minimal read-only Combined overview rows."""

    rows = combined_service.list_game_overview(limit=limit)
    return [CombinedGameOverviewResponse.model_validate(row) for row in rows]


class CombinedGameActivityResponse(BaseModel):
    """Separate Steam and bounded-observed Chzzk activity dimensions."""

    canonical_game_id: int
    canonical_name: str
    steam_appid: int | None
    ccu_period_anchor_date: dt.date | None
    period_avg_ccu_7d: float | None
    period_peak_ccu_7d: int | None
    chzzk_mapped_category_count: int
    chzzk_viewer_hours_observed_7d: float | None
    chzzk_peak_viewers_observed_7d: int | None
    chzzk_observed_bucket_count_7d: int | None
    chzzk_collection_bucket_count_7d: int | None
    chzzk_observation_ratio_7d: float | None
    chzzk_latest_observed_bucket_7d: dt.datetime | None
    bounded_sample_caveat: Literal["bounded_sample"]


@router.get("/games/activity", response_model=list[CombinedGameActivityResponse])
def list_combined_games_activity(
    limit: int = COMBINED_GAME_ACTIVITY_LIMIT_QUERY,
) -> list[CombinedGameActivityResponse]:
    """Return activity rows in canonical ID order, with a transport-only limit."""

    rows = combined_service.list_game_activity(limit=limit)
    return [CombinedGameActivityResponse.model_validate(row) for row in rows]
