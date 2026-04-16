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
  rankingCardLimit?: number | null
  searchQuery: string
  selectedId: string | null
}

interface UseSteamOverviewResult {
  games: SteamReferenceGame[]
  selectedGame: SteamReferenceGame | null
  totalGameCount: number
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

type LatestRowWithCanonicalGameId = {
  canonical_game_id: number
}

const mergeLatestRows = <Row extends LatestRowWithCanonicalGameId>(
  baseRows: Row[],
  supplementalRowsByCanonicalGameId: Record<number, Row | null>,
): Row[] => {
  const rowsByCanonicalGameId = new Map(baseRows.map((row) => [row.canonical_game_id, row] as const))

  Object.entries(supplementalRowsByCanonicalGameId).forEach(([canonicalGameId, row]) => {
    if (row !== null) {
      rowsByCanonicalGameId.set(Number(canonicalGameId), row)
    }
  })

  return Array.from(rowsByCanonicalGameId.values())
}

export function useSteamOverview({
  mode,
  rankingWindow,
  rankingCardLimit = 4,
  searchQuery,
  selectedId,
}: UseSteamOverviewArgs): UseSteamOverviewResult {
  const [overviewData, setOverviewData] = useState<SteamOverviewApiData | null>(null)
  const [supplementalCcuByCanonicalGameId, setSupplementalCcuByCanonicalGameId] = useState<Record<number, GameLatestCcu | null>>({})
  const [supplementalPriceByCanonicalGameId, setSupplementalPriceByCanonicalGameId] = useState<Record<number, GameLatestPrice | null>>({})
  const [supplementalReviewsByCanonicalGameId, setSupplementalReviewsByCanonicalGameId] = useState<Record<number, GameLatestReviews | null>>({})
  const [supplementalCcuLoadingCanonicalGameIds, setSupplementalCcuLoadingCanonicalGameIds] = useState<Record<number, true>>({})
  const [supplementalPriceLoadingCanonicalGameIds, setSupplementalPriceLoadingCanonicalGameIds] = useState<Record<number, true>>({})
  const [supplementalReviewsLoadingCanonicalGameIds, setSupplementalReviewsLoadingCanonicalGameIds] = useState<Record<number, true>>({})
  const [supplementalCcuErrorCanonicalGameIds, setSupplementalCcuErrorCanonicalGameIds] = useState<Record<number, true>>({})
  const [supplementalPriceErrorCanonicalGameIds, setSupplementalPriceErrorCanonicalGameIds] = useState<Record<number, true>>({})
  const [supplementalReviewsErrorCanonicalGameIds, setSupplementalReviewsErrorCanonicalGameIds] = useState<Record<number, true>>({})
  const [historyByCanonicalGameId, setHistoryByCanonicalGameId] = useState<Record<number, GameDaily90dCcu[]>>({})
  const [historyLoadingCanonicalGameId, setHistoryLoadingCanonicalGameId] = useState<number | null>(null)
  const [historyErrorCanonicalGameIds, setHistoryErrorCanonicalGameIds] = useState<Record<number, true>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadOverview() {
      if (mode === 'Explore') {
        setOverviewData(EMPTY_OVERVIEW_DATA)
        setLoading(false)
        setError(null)
        return
      }

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

  const mergedOverviewData: SteamOverviewApiData = {
    rankings: overviewData?.rankings ?? EMPTY_OVERVIEW_DATA.rankings,
    ccuRows: mergeLatestRows(overviewData?.ccuRows ?? EMPTY_OVERVIEW_DATA.ccuRows, supplementalCcuByCanonicalGameId),
    priceRows: mergeLatestRows(overviewData?.priceRows ?? EMPTY_OVERVIEW_DATA.priceRows, supplementalPriceByCanonicalGameId),
    reviewRows: mergeLatestRows(overviewData?.reviewRows ?? EMPTY_OVERVIEW_DATA.reviewRows, supplementalReviewsByCanonicalGameId),
  }

  const allGames = buildSteamGames({
    mode,
    rankingWindow,
    searchQuery,
    data: mergedOverviewData,
    historyByCanonicalGameId,
    historyLoadingCanonicalGameId,
    historyErrorCanonicalGameIds,
  })
  const games = rankingCardLimit === null ? allGames : allGames.slice(0, rankingCardLimit)

  useEffect(() => {
    const surfacedCanonicalGameIds = games
      .map((game) => game.canonicalGameId)
      .filter((canonicalGameId): canonicalGameId is number => canonicalGameId !== null)

    if (surfacedCanonicalGameIds.length === 0) {
      return
    }

    const currentCcuGameIds = new Set(mergedOverviewData.ccuRows.map((row) => row.canonical_game_id))
    const currentPriceGameIds = new Set(mergedOverviewData.priceRows.map((row) => row.canonical_game_id))
    const currentReviewGameIds = new Set(mergedOverviewData.reviewRows.map((row) => row.canonical_game_id))

    const ccuTargets =
      mode === 'Top Selling'
        ? surfacedCanonicalGameIds.filter(
            (canonicalGameId) =>
              !currentCcuGameIds.has(canonicalGameId) &&
              supplementalCcuByCanonicalGameId[canonicalGameId] === undefined &&
              !supplementalCcuLoadingCanonicalGameIds[canonicalGameId] &&
              !supplementalCcuErrorCanonicalGameIds[canonicalGameId],
          )
        : []

    const priceTargets = surfacedCanonicalGameIds.filter(
      (canonicalGameId) =>
        !currentPriceGameIds.has(canonicalGameId) &&
        supplementalPriceByCanonicalGameId[canonicalGameId] === undefined &&
        !supplementalPriceLoadingCanonicalGameIds[canonicalGameId] &&
        !supplementalPriceErrorCanonicalGameIds[canonicalGameId],
    )

    const reviewTargets = surfacedCanonicalGameIds.filter(
      (canonicalGameId) =>
        !currentReviewGameIds.has(canonicalGameId) &&
        supplementalReviewsByCanonicalGameId[canonicalGameId] === undefined &&
        !supplementalReviewsLoadingCanonicalGameIds[canonicalGameId] &&
        !supplementalReviewsErrorCanonicalGameIds[canonicalGameId],
    )

    if (ccuTargets.length === 0 && priceTargets.length === 0 && reviewTargets.length === 0) {
      return
    }

    const controller = new AbortController()

    if (ccuTargets.length > 0) {
      setSupplementalCcuLoadingCanonicalGameIds((current) => ({
        ...current,
        ...Object.fromEntries(ccuTargets.map((canonicalGameId) => [canonicalGameId, true])),
      }))
    }

    if (priceTargets.length > 0) {
      setSupplementalPriceLoadingCanonicalGameIds((current) => ({
        ...current,
        ...Object.fromEntries(priceTargets.map((canonicalGameId) => [canonicalGameId, true])),
      }))
    }

    if (reviewTargets.length > 0) {
      setSupplementalReviewsLoadingCanonicalGameIds((current) => ({
        ...current,
        ...Object.fromEntries(reviewTargets.map((canonicalGameId) => [canonicalGameId, true])),
      }))
    }

    async function loadSupplementalRows() {
      await Promise.all([
        ...ccuTargets.map(async (canonicalGameId) => {
          try {
            const row = await gamesApi.getGameLatestCcu(canonicalGameId, controller.signal)

            if (controller.signal.aborted) {
              return
            }

            setSupplementalCcuByCanonicalGameId((current) => ({
              ...current,
              [canonicalGameId]: row,
            }))
          } catch {
            if (controller.signal.aborted) {
              return
            }

            setSupplementalCcuErrorCanonicalGameIds((current) => ({
              ...current,
              [canonicalGameId]: true,
            }))
          } finally {
            if (!controller.signal.aborted) {
              setSupplementalCcuLoadingCanonicalGameIds((current) => {
                const next = { ...current }
                delete next[canonicalGameId]
                return next
              })
            }
          }
        }),
        ...priceTargets.map(async (canonicalGameId) => {
          try {
            const row = await gamesApi.getGameLatestPrice(canonicalGameId, controller.signal)

            if (controller.signal.aborted) {
              return
            }

            setSupplementalPriceByCanonicalGameId((current) => ({
              ...current,
              [canonicalGameId]: row,
            }))
          } catch {
            if (controller.signal.aborted) {
              return
            }

            setSupplementalPriceErrorCanonicalGameIds((current) => ({
              ...current,
              [canonicalGameId]: true,
            }))
          } finally {
            if (!controller.signal.aborted) {
              setSupplementalPriceLoadingCanonicalGameIds((current) => {
                const next = { ...current }
                delete next[canonicalGameId]
                return next
              })
            }
          }
        }),
        ...reviewTargets.map(async (canonicalGameId) => {
          try {
            const row = await gamesApi.getGameLatestReviews(canonicalGameId, controller.signal)

            if (controller.signal.aborted) {
              return
            }

            setSupplementalReviewsByCanonicalGameId((current) => ({
              ...current,
              [canonicalGameId]: row,
            }))
          } catch {
            if (controller.signal.aborted) {
              return
            }

            setSupplementalReviewsErrorCanonicalGameIds((current) => ({
              ...current,
              [canonicalGameId]: true,
            }))
          } finally {
            if (!controller.signal.aborted) {
              setSupplementalReviewsLoadingCanonicalGameIds((current) => {
                const next = { ...current }
                delete next[canonicalGameId]
                return next
              })
            }
          }
        }),
      ])
    }

    void loadSupplementalRows()

    return () => {
      controller.abort()
    }
  }, [
    games,
    mergedOverviewData,
    mode,
    supplementalCcuByCanonicalGameId,
    supplementalCcuErrorCanonicalGameIds,
    supplementalCcuLoadingCanonicalGameIds,
    supplementalPriceByCanonicalGameId,
    supplementalPriceErrorCanonicalGameIds,
    supplementalPriceLoadingCanonicalGameIds,
    supplementalReviewsByCanonicalGameId,
    supplementalReviewsErrorCanonicalGameIds,
    supplementalReviewsLoadingCanonicalGameIds,
  ])

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
    totalGameCount: allGames.length,
    loading,
    error,
  }
}
