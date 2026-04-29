"""Chzzk source API routes."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.services import chzzk_service

router = APIRouter(prefix="/chzzk", tags=["chzzk"])

CHZZK_CATEGORY_OVERVIEW_LIMIT_QUERY = Query(default=50, ge=1, le=200)


class ChzzkCategoryOverviewResponse(BaseModel):
    """Observed sample metrics for one Chzzk category evidence row."""

    chzzk_category_id: str
    category_name: str
    category_type: str
    latest_bucket_time: dt.datetime
    latest_viewers_observed: int
    observed_bucket_count: int
    bucket_time_min: dt.datetime
    bucket_time_max: dt.datetime
    viewer_hours_observed: float
    avg_viewers_observed: float
    peak_viewers_observed: int
    live_count_observed_total: int
    avg_channels_observed: float
    peak_channels_observed: int
    viewer_per_channel_observed: float | None
    full_1d_candidate_available: bool
    full_7d_candidate_available: bool
    missing_1d_bucket_count: int
    missing_7d_bucket_count: int
    coverage_status: str
    bounded_sample_caveat: str


@router.get("/categories/overview", response_model=list[ChzzkCategoryOverviewResponse])
def list_chzzk_categories_overview(
    limit: int = CHZZK_CATEGORY_OVERVIEW_LIMIT_QUERY,
) -> list[ChzzkCategoryOverviewResponse]:
    """Return category-only Chzzk observed sample metrics."""

    rows = chzzk_service.list_category_overview(limit=limit)
    return [ChzzkCategoryOverviewResponse.model_validate(row) for row in rows]
