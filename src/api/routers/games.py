"""Game-related API routes."""

from __future__ import annotations

import datetime as dt
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services import (
    ccu_service,
    explore_service,
    price_service,
    rankings_service,
    reviews_service,
)

router = APIRouter(prefix="/games", tags=["games"])


class RankingWindow(str, Enum):
    """Explicit ranking window values exposed on public read-only list endpoints."""

    ONE_DAY = "1d"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"


TOP_SELLING_UNSUPPORTED_WINDOW_DETAIL = (
    "Top Selling currently supports only window=7d because the Steam topsellers source is weekly."
)
CCU_LIST_LIMIT_QUERY = Query(default=50, ge=1, le=200)
CCU_LIST_WINDOW_QUERY = Query(default=RankingWindow.ONE_DAY)
RANKINGS_LIST_LIMIT_QUERY = Query(default=50, ge=1, le=200)
RANKINGS_LIST_WINDOW_QUERY = Query(default=RankingWindow.LAST_7_DAYS)
EXPLORE_OVERVIEW_LIMIT_QUERY = Query(default=50, ge=1, le=200)


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
    currency_code: str | None
    initial_price_minor: int | None
    final_price_minor: int | None
    discount_percent: int | None
    is_free: bool | None


class GameLatestRankingResponse(BaseModel):
    """Latest ranking response model for one fixed rankings list row."""

    snapshot_date: dt.date
    rank_position: int
    steam_appid: int
    canonical_game_id: int | None
    canonical_name: str | None


class GameExploreOverviewResponse(BaseModel):
    """Explore overview response model for one active tracked Steam game."""

    canonical_game_id: int
    canonical_name: str
    steam_appid: int | None
    ccu_bucket_time: dt.datetime | None
    current_ccu: int | None
    current_delta_ccu_abs: int | None
    current_delta_ccu_pct: float | None
    current_ccu_missing_flag: bool
    ccu_period_anchor_date: dt.date | None
    period_avg_ccu_7d: float | None
    period_peak_ccu_7d: int | None
    delta_period_avg_ccu_7d_abs: float | None
    delta_period_avg_ccu_7d_pct: float | None
    delta_period_peak_ccu_7d_abs: int | None
    delta_period_peak_ccu_7d_pct: float | None
    observed_player_hours_7d: float | None
    estimated_player_hours_7d_observed_bucket_count: int | None
    estimated_player_hours_7d_expected_bucket_count: int | None
    estimated_player_hours_7d_coverage_ratio: float | None
    estimated_player_hours_7d: float | None
    delta_estimated_player_hours_7d_abs: float | None
    delta_estimated_player_hours_7d_pct: float | None
    reviews_snapshot_date: dt.date | None
    total_reviews: int | None
    total_positive: int | None
    total_negative: int | None
    positive_ratio: float | None
    reviews_added_7d: int | None
    reviews_added_30d: int | None
    period_positive_ratio_7d: float | None
    period_positive_ratio_30d: float | None
    delta_reviews_added_7d_abs: int | None
    delta_reviews_added_7d_pct: float | None
    delta_period_positive_ratio_7d_pp: float | None
    delta_reviews_added_30d_abs: int | None
    delta_reviews_added_30d_pct: float | None
    delta_period_positive_ratio_30d_pp: float | None
    price_bucket_time: dt.datetime | None
    region: str | None
    currency_code: str | None
    initial_price_minor: int | None
    final_price_minor: int | None
    discount_percent: int | None
    is_free: bool | None


@router.get("/explore/overview", response_model=list[GameExploreOverviewResponse])
def list_games_explore_overview(
    limit: int = EXPLORE_OVERVIEW_LIMIT_QUERY,
) -> list[GameExploreOverviewResponse]:
    """Return active tracked Steam games with grounded Explore evidence fields."""

    rows = explore_service.list_explore_overview(limit=limit)
    return [GameExploreOverviewResponse.model_validate(row) for row in rows]


@router.get("/ccu/latest", response_model=list[GameLatestCcuResponse])
def list_games_latest_ccu(
    limit: int = CCU_LIST_LIMIT_QUERY,
    window: RankingWindow = CCU_LIST_WINDOW_QUERY,
) -> list[GameLatestCcuResponse]:
    """Return latest CCU rows ordered by the requested Most Played list context."""

    rows = ccu_service.list_latest_ccu(limit=limit, window=window.value)
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


@router.get("/rankings/latest", response_model=list[GameLatestRankingResponse])
def list_games_latest_rankings(
    limit: int = RANKINGS_LIST_LIMIT_QUERY,
    window: RankingWindow = RANKINGS_LIST_WINDOW_QUERY,
) -> list[GameLatestRankingResponse]:
    """Return latest fixed KR weekly top-selling ranking rows with an optional limit."""

    if window != RankingWindow.LAST_7_DAYS:
        raise HTTPException(status_code=400, detail=TOP_SELLING_UNSUPPORTED_WINDOW_DETAIL)

    rows = rankings_service.list_latest_rankings(limit=limit)
    return [GameLatestRankingResponse.model_validate(row) for row in rows]


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
