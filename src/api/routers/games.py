"""Game-related API routes."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services import ccu_service

router = APIRouter(prefix="/games", tags=["games"])


class GameLatestCcuResponse(BaseModel):
    """Latest CCU response model for one canonical game."""

    canonical_game_id: int
    canonical_name: str
    bucket_time: dt.datetime
    ccu: int
    delta_ccu_abs: int | None
    delta_ccu_pct: float | None
    missing_flag: bool


@router.get("/ccu/latest", response_model=list[GameLatestCcuResponse])
def list_games_latest_ccu(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[GameLatestCcuResponse]:
    """Return latest CCU rows from srv_game_latest_ccu with an optional limit."""

    rows = ccu_service.list_latest_ccu(limit=limit)
    return [GameLatestCcuResponse.model_validate(row) for row in rows]


@router.get("/{canonical_game_id}/ccu/latest", response_model=GameLatestCcuResponse)
def get_game_latest_ccu(canonical_game_id: int) -> GameLatestCcuResponse:
    """Return latest CCU row from srv_game_latest_ccu for one game."""

    row = ccu_service.get_latest_ccu_by_game(canonical_game_id=canonical_game_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Game latest CCU not found")

    return GameLatestCcuResponse.model_validate(row)
