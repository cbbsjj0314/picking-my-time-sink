import { ApiError, requestJson } from "./client";

type RequestOptions = {
  signal?: AbortSignal;
};

type ListOptions = RequestOptions & {
  limit?: number;
};

export type GameLatestRanking = {
  snapshot_date: string;
  rank_position: number;
  steam_appid: number;
  canonical_game_id: number | null;
  canonical_name: string | null;
};

export type GameLatestCcu = {
  canonical_game_id: number;
  canonical_name: string;
  bucket_time: string;
  ccu: number;
  delta_ccu_abs: number | null;
  delta_ccu_pct: number | null;
  missing_flag: boolean;
};

export type GameDaily90dCcu = {
  canonical_game_id: number;
  bucket_date: string;
  avg_ccu: number;
  peak_ccu: number;
};

export type GameLatestPrice = {
  canonical_game_id: number;
  canonical_name: string;
  bucket_time: string;
  region: string;
  currency_code: string;
  initial_price_minor: number;
  final_price_minor: number;
  discount_percent: number;
  is_free: boolean | null;
};

export type GameLatestReviews = {
  canonical_game_id: number;
  canonical_name: string;
  snapshot_date: string;
  total_reviews: number;
  total_positive: number;
  total_negative: number;
  positive_ratio: number;
  delta_total_reviews: number | null;
  delta_positive_ratio: number | null;
  missing_flag: boolean;
};

export type GameDashboardData = {
  ccu: GameLatestCcu | null;
  ccuHistory: GameDaily90dCcu[];
  price: GameLatestPrice | null;
  reviews: GameLatestReviews | null;
};

function withQuery(
  path: string,
  query: Record<string, string | number | undefined>,
): string {
  const params = new URLSearchParams();

  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  });

  const search = params.toString();
  return search.length > 0 ? `${path}?${search}` : path;
}

async function requestOptional<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  try {
    return await requestJson<T>(path, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}

function listLatestRankings(options: ListOptions = {}): Promise<GameLatestRanking[]> {
  return requestJson<GameLatestRanking[]>(
    withQuery("/games/rankings/latest", { limit: options.limit ?? 12 }),
    { signal: options.signal },
  );
}

function listLatestCcu(options: ListOptions = {}): Promise<GameLatestCcu[]> {
  return requestJson<GameLatestCcu[]>(
    withQuery("/games/ccu/latest", { limit: options.limit ?? 12 }),
    { signal: options.signal },
  );
}

function getGameLatestCcu(
  canonicalGameId: number,
  signal?: AbortSignal,
): Promise<GameLatestCcu | null> {
  return requestOptional<GameLatestCcu>(`/games/${canonicalGameId}/ccu/latest`, signal);
}

function getGameCcuDaily90d(
  canonicalGameId: number,
  signal?: AbortSignal,
): Promise<GameDaily90dCcu[]> {
  return requestJson<GameDaily90dCcu[]>(`/games/${canonicalGameId}/ccu/daily-90d`, {
    signal,
  });
}

function listLatestPrice(options: ListOptions = {}): Promise<GameLatestPrice[]> {
  return requestJson<GameLatestPrice[]>(
    withQuery("/games/price/latest", { limit: options.limit ?? 12 }),
    { signal: options.signal },
  );
}

function getGameLatestPrice(
  canonicalGameId: number,
  signal?: AbortSignal,
): Promise<GameLatestPrice | null> {
  return requestOptional<GameLatestPrice>(`/games/${canonicalGameId}/price/latest`, signal);
}

function listLatestReviews(options: ListOptions = {}): Promise<GameLatestReviews[]> {
  return requestJson<GameLatestReviews[]>(
    withQuery("/games/reviews/latest", { limit: options.limit ?? 12 }),
    { signal: options.signal },
  );
}

function getGameLatestReviews(
  canonicalGameId: number,
  signal?: AbortSignal,
): Promise<GameLatestReviews | null> {
  return requestOptional<GameLatestReviews>(
    `/games/${canonicalGameId}/reviews/latest`,
    signal,
  );
}

async function getGameDashboard(
  canonicalGameId: number,
  signal?: AbortSignal,
): Promise<GameDashboardData> {
  const [ccu, ccuHistory, price, reviews] = await Promise.all([
    getGameLatestCcu(canonicalGameId, signal),
    getGameCcuDaily90d(canonicalGameId, signal),
    getGameLatestPrice(canonicalGameId, signal),
    getGameLatestReviews(canonicalGameId, signal),
  ]);

  return {
    ccu,
    ccuHistory,
    price,
    reviews,
  };
}

export const gamesApi = {
  listLatestRankings,
  listLatestCcu,
  getGameLatestCcu,
  getGameCcuDaily90d,
  listLatestPrice,
  getGameLatestPrice,
  listLatestReviews,
  getGameLatestReviews,
  getGameDashboard,
};
