"""Game-related API routes."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services import ccu_service, price_service, reviews_service

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


class GameDaily90dCcuResponse(BaseModel):
    """Fixed recent 90-day daily CCU response model for one canonical game."""

    canonical_game_id: int
    bucket_date: dt.date
    avg_ccu: float
    peak_ccu: int


class GameLatestReviewsResponse(BaseModel):
    """Latest reviews response model for one canonical game."""

    canonical_game_id: int
    canonical_name: str
    snapshot_date: dt.date
    total_reviews: int
    total_positive: int
    total_negative: int
    positive_ratio: float
    delta_total_reviews: int | None
    delta_positive_ratio: float | None
    missing_flag: bool


class GameLatestPriceResponse(BaseModel):
    """Latest price response model for one canonical game."""

    canonical_game_id: int
    canonical_name: str
    bucket_time: dt.datetime
    region: str
    currency_code: str
    initial_price_minor: int
    final_price_minor: int
    discount_percent: int
    is_free: bool | None


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


@router.get(
    "/{canonical_game_id}/ccu/daily-90d",
    response_model=list[GameDaily90dCcuResponse],
)
def get_game_daily_90d_ccu(canonical_game_id: int) -> list[GameDaily90dCcuResponse]:
    """Return fixed recent 90-day daily CCU rows for one game."""

    rows = ccu_service.get_recent_90d_ccu_daily_by_game(canonical_game_id=canonical_game_id)
    return [GameDaily90dCcuResponse.model_validate(row) for row in rows]


@router.get("/price/latest", response_model=list[GameLatestPriceResponse])
def list_games_latest_price(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[GameLatestPriceResponse]:
    """Return latest KR price rows from srv_game_latest_price with an optional limit."""

    rows = price_service.list_latest_price(limit=limit)
    return [GameLatestPriceResponse.model_validate(row) for row in rows]


@router.get(
    "/{canonical_game_id}/price/latest",
    response_model=GameLatestPriceResponse,
)
def get_game_latest_price(canonical_game_id: int) -> GameLatestPriceResponse:
    """Return latest KR price row from srv_game_latest_price for one game."""

    row = price_service.get_latest_price_by_game(canonical_game_id=canonical_game_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Game latest price not found")

    return GameLatestPriceResponse.model_validate(row)


@router.get("/reviews/latest", response_model=list[GameLatestReviewsResponse])
def list_games_latest_reviews(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[GameLatestReviewsResponse]:
    """Return latest reviews rows from srv_game_latest_reviews with an optional limit."""

    rows = reviews_service.list_latest_reviews(limit=limit)
    return [GameLatestReviewsResponse.model_validate(row) for row in rows]


@router.get(
    "/{canonical_game_id}/reviews/latest",
    response_model=GameLatestReviewsResponse,
)
def get_game_latest_reviews(canonical_game_id: int) -> GameLatestReviewsResponse:
    """Return latest reviews row from srv_game_latest_reviews for one game."""

    row = reviews_service.get_latest_reviews_by_game(canonical_game_id=canonical_game_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Game latest reviews not found")

    return GameLatestReviewsResponse.model_validate(row)
