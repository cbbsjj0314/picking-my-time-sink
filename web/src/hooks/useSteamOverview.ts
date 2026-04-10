import { useEffect, useState } from 'react'
import {
  gamesApi,
  type GameDaily90dCcu,
  type GameLatestCcu,
  type GameLatestPrice,
  type GameLatestRanking,
  type GameLatestReviews,
  type GameRankingWindow,
} from '../api/games'
import { buildSteamGames, getSteamQueryErrorMessage, type SteamOverviewApiData } from '../lib/steamViewModel'
import type { RangeOption, SteamDiscoverMode, SteamReferenceGame } from '../types'

interface UseSteamOverviewArgs {
  mode: SteamDiscoverMode
  rankingWindow: RangeOption
  searchQuery: string
  selectedId: string | null
}

interface UseSteamOverviewResult {
  games: SteamReferenceGame[]
  selectedGame: SteamReferenceGame | null
  loading: boolean
  error: string | null
}

const DEFAULT_LIMIT = 12
const API_WINDOW_BY_RANGE: Record<RangeOption, GameRankingWindow> = {
  '1D': '1d',
  'Last 7 Days': '7d',
  'Last 30 Days': '30d',
  'Last 3 Months': '90d',
}

const EMPTY_OVERVIEW_DATA: SteamOverviewApiData = {
  rankings: [],
  ccuRows: [],
  priceRows: [],
  reviewRows: [],
}

export function useSteamOverview({
  mode,
  rankingWindow,
  searchQuery,
  selectedId,
}: UseSteamOverviewArgs): UseSteamOverviewResult {
  const [overviewData, setOverviewData] = useState<SteamOverviewApiData | null>(null)
  const [historyByCanonicalGameId, setHistoryByCanonicalGameId] = useState<Record<number, GameDaily90dCcu[]>>({})
  const [historyLoadingCanonicalGameId, setHistoryLoadingCanonicalGameId] = useState<number | null>(null)
  const [historyErrorCanonicalGameIds, setHistoryErrorCanonicalGameIds] = useState<Record<number, true>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadOverview() {
      setLoading(true)
      setError(null)

      try {
        let rankings: GameLatestRanking[] = []
        let ccuRows: GameLatestCcu[] = []
        let priceRows: GameLatestPrice[] = []
        let reviewRows: GameLatestReviews[] = []

        if (mode === 'Top Selling') {
          ;[rankings, ccuRows, priceRows, reviewRows] = await Promise.all([
            gamesApi.listLatestRankings({
              limit: DEFAULT_LIMIT,
              signal: controller.signal,
              window: API_WINDOW_BY_RANGE[rankingWindow],
            }),
            gamesApi.listLatestCcu({ limit: DEFAULT_LIMIT, signal: controller.signal }),
            gamesApi.listLatestPrice({ limit: DEFAULT_LIMIT, signal: controller.signal }),
            gamesApi.listLatestReviews({ limit: DEFAULT_LIMIT, signal: controller.signal }),
          ])
        } else {
          ;[ccuRows, priceRows, reviewRows] = await Promise.all([
            gamesApi.listLatestCcu({
              limit: DEFAULT_LIMIT,
              signal: controller.signal,
              window: API_WINDOW_BY_RANGE[rankingWindow],
            }),
            gamesApi.listLatestPrice({ limit: DEFAULT_LIMIT, signal: controller.signal }),
            gamesApi.listLatestReviews({ limit: DEFAULT_LIMIT, signal: controller.signal }),
          ])
        }

        if (controller.signal.aborted) {
          return
        }

        setOverviewData({
          rankings,
          ccuRows,
          priceRows,
          reviewRows,
        })
      } catch (nextError) {
        if (controller.signal.aborted) {
          return
        }

        setOverviewData(null)
        setError(getSteamQueryErrorMessage(nextError))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadOverview()

    return () => {
      controller.abort()
    }
  }, [mode, rankingWindow])

  const games = buildSteamGames({
    mode,
    rankingWindow,
    searchQuery,
    data: overviewData ?? EMPTY_OVERVIEW_DATA,
    historyByCanonicalGameId,
    historyLoadingCanonicalGameId,
    historyErrorCanonicalGameIds,
  })

  const selectedGame = games.find((game) => game.id === selectedId) ?? games[0] ?? null
  const selectedCanonicalGameId = selectedGame?.canonicalGameId ?? null

  useEffect(() => {
    if (selectedCanonicalGameId === null) {
      return
    }

    const canonicalGameId = selectedCanonicalGameId

    if (historyByCanonicalGameId[canonicalGameId] !== undefined || historyErrorCanonicalGameIds[canonicalGameId]) {
      return
    }

    const controller = new AbortController()
    setHistoryLoadingCanonicalGameId(canonicalGameId)

    async function loadHistory() {
      try {
        const rows = await gamesApi.getGameCcuDaily90d(canonicalGameId, controller.signal)

        if (controller.signal.aborted) {
          return
        }

        setHistoryByCanonicalGameId((current) => ({
          ...current,
          [canonicalGameId]: rows,
        }))
      } catch (nextError) {
        if (controller.signal.aborted) {
          return
        }

        setHistoryErrorCanonicalGameIds((current) => ({
          ...current,
          [canonicalGameId]: true,
        }))
        setError(getSteamQueryErrorMessage(nextError))
      } finally {
        if (!controller.signal.aborted) {
          setHistoryLoadingCanonicalGameId((current) => (current === canonicalGameId ? null : current))
        }
      }
    }

    void loadHistory()

    return () => {
      controller.abort()
    }
  }, [historyByCanonicalGameId, historyErrorCanonicalGameIds, selectedCanonicalGameId])

  return {
    games,
    selectedGame,
    loading,
    error,
  }
}
