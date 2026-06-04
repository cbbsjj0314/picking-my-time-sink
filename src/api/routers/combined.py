"""Combined source API routes."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.services import combined_service

router = APIRouter(prefix="/combined", tags=["combined"])

COMBINED_GAME_OVERVIEW_LIMIT_QUERY = Query(default=50, ge=1, le=200)


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
