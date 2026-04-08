import type {
  GameDaily90dCcu,
  GameLatestCcu,
  GameLatestPrice,
  GameLatestRanking,
  GameLatestReviews,
} from '../api/games'
import { formatCompact, formatSignedPercent, formatWon } from './format'
import type {
  SteamCcuPoint,
  SteamChartRange,
  SteamChartState,
  SteamDataState,
  SteamDataStateTarget,
  SteamDetailCard,
  SteamDiscoverMode,
  SteamReferenceGame,
} from '../types'

export interface SteamOverviewApiData {
  rankings: GameLatestRanking[]
  ccuRows: GameLatestCcu[]
  priceRows: GameLatestPrice[]
  reviewRows: GameLatestReviews[]
}

interface BuildSteamGamesArgs {
  mode: SteamDiscoverMode
  searchQuery: string
  data: SteamOverviewApiData
  historyByCanonicalGameId: Record<number, GameDaily90dCcu[]>
  historyLoadingCanonicalGameId: number | null
  historyErrorCanonicalGameIds: Record<number, true>
}

interface SteamBaseRow {
  id: string
  canonicalGameId: number | null
  steamAppId: number | null
  title: string
  rank: number
  ccu: GameLatestCcu | null
  price: GameLatestPrice | null
  reviews: GameLatestReviews | null
}

const PENDING_TOOLTIP = '데이터를 준비 중입니다.'
const PARTIAL_TOOLTIP = '일부 데이터가 아직 반영되지 않았습니다.'
const DELAYED_MESSAGE = '현재 데이터 업데이트가 지연되고 있습니다.'

const KST_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: false,
  timeZone: 'Asia/Seoul',
})

const KST_DAY_FORMATTER = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  timeZone: 'Asia/Seoul',
})

const KST_MONTH_DAY_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'numeric',
  day: 'numeric',
  timeZone: 'Asia/Seoul',
})

const HISTORY_POINT_LIMITS: Record<SteamChartRange, number> = {
  '7D': 7,
  '30D': 30,
  '90D': 90,
}

const formatInteger = (value: number) => value.toLocaleString('en-US')

const formatPercentRatio = (value: number) => `${Math.round(value * 100)}%`

const formatCompactInteger = (value: number) =>
  new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: value >= 1000 ? 1 : 0,
  }).format(value)

const formatMinorPrice = (valueMinor: number, currencyCode: string, isFree: boolean | null) => {
  if (isFree) {
    return 'Free'
  }

  if (currencyCode === 'KRW') {
    return formatWon(Math.round(valueMinor / 100))
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currencyCode,
    maximumFractionDigits: 2,
  }).format(valueMinor / 100)
}

const getReviewSummaryFallback = (positiveRatio: number) => {
  const percent = Math.round(positiveRatio * 100)

  if (percent >= 95) return 'Overwhelmingly Positive'
  if (percent >= 85) return 'Very Positive'
  if (percent >= 70) return 'Mostly Positive'
  if (percent >= 40) return 'Mixed'
  if (percent >= 20) return 'Mostly Negative'
  return 'Very Negative'
}

const addChip = (chips: string[], value: string) => {
  if (!chips.includes(value) && chips.length < 2) {
    chips.push(value)
  }
}

const getVerdictChips = (row: SteamBaseRow) => {
  const chips: string[] = []

  if (row.ccu) {
    addChip(chips, 'Players healthy')
  }

  if (row.reviews && row.reviews.positive_ratio >= 0.7) {
    addChip(chips, 'Reviews positive')
  }

  if (row.price) {
    addChip(chips, 'Price live')
  }

  if (chips.length === 0) {
    chips.push('Deferred')
  }

  return chips
}

const buildCardState = (
  target: SteamDataStateTarget,
  kind: SteamDataState['kind'],
  tooltip: string,
): SteamDataState => ({
  kind,
  target,
  tooltip,
})

const getCardStates = (
  row: SteamBaseRow,
  historyRows: GameDaily90dCcu[] | undefined,
  historyLoadingCanonicalGameId: number | null,
): Partial<Record<SteamDataStateTarget, SteamDataState>> => {
  const states: Partial<Record<SteamDataStateTarget, SteamDataState>> = {}

  if (row.canonicalGameId === null) {
    states.CCU = buildCardState('CCU', 'Pending', PENDING_TOOLTIP)
    states.Reviews = buildCardState('Reviews', 'Pending', PENDING_TOOLTIP)
    states.Price = buildCardState('Price', 'Pending', PENDING_TOOLTIP)
    return states
  }

  if (!row.ccu) {
    states.CCU = buildCardState('CCU', 'Pending', PENDING_TOOLTIP)
  } else if (historyLoadingCanonicalGameId === row.canonicalGameId && historyRows === undefined) {
    states.CCU = buildCardState('CCU', 'Pending', PENDING_TOOLTIP)
  } else if (row.ccu.missing_flag) {
    states.CCU = buildCardState('CCU', 'Partial', PARTIAL_TOOLTIP)
  } else if (!historyRows || historyRows.length === 0) {
    states.CCU = buildCardState('CCU', 'Partial', PARTIAL_TOOLTIP)
  }

  if (!row.reviews) {
    states.Reviews = buildCardState('Reviews', 'Pending', PENDING_TOOLTIP)
  } else if (
    row.reviews.missing_flag ||
    row.reviews.delta_total_reviews === null ||
    row.reviews.delta_positive_ratio === null
  ) {
    states.Reviews = buildCardState('Reviews', 'Partial', PARTIAL_TOOLTIP)
  }

  if (!row.price) {
    states.Price = buildCardState('Price', 'Pending', PENDING_TOOLTIP)
  }

  return states
}

const getStatusBadge = (cardStates: Partial<Record<SteamDataStateTarget, SteamDataState>>) => {
  const states = Object.values(cardStates)

  if (states.some((state) => state.kind === 'Pending')) {
    return 'Pending'
  }

  if (states.some((state) => state.kind === 'Partial')) {
    return 'Partial'
  }

  if (states.some((state) => state.kind === 'Stale')) {
    return 'Stale'
  }

  return null
}

const getChartState = (
  row: SteamBaseRow,
  historyRows: GameDaily90dCcu[] | undefined,
  historyLoadingCanonicalGameId: number | null,
  historyErrorCanonicalGameIds: Record<number, true>,
): SteamChartState | undefined => {
  if (row.canonicalGameId === null) {
    return {
      kind: 'empty',
      message: DELAYED_MESSAGE,
    }
  }

  if (historyErrorCanonicalGameIds[row.canonicalGameId]) {
    return {
      kind: 'error',
      message: DELAYED_MESSAGE,
    }
  }

  if (historyLoadingCanonicalGameId === row.canonicalGameId && historyRows === undefined) {
    return {
      kind: 'loading',
      message: '데이터를 불러오는 중입니다.',
    }
  }

  if (historyRows === undefined) {
    return {
      kind: 'loading',
      message: '데이터를 불러오는 중입니다.',
    }
  }

  if (historyRows.length === 0) {
    return {
      kind: 'empty',
      message: DELAYED_MESSAGE,
    }
  }

  return undefined
}

const getSevenDayAverage = (historyRows: GameDaily90dCcu[] | undefined) => {
  if (!historyRows || historyRows.length === 0) {
    return null
  }

  const recentRows = historyRows.slice(-7)
  const avg = recentRows.reduce((sum, row) => sum + row.avg_ccu, 0) / recentRows.length
  return Math.round(avg)
}

const buildTimelinePoints = (historyRows: GameDaily90dCcu[] | undefined, range: SteamChartRange): SteamCcuPoint[] => {
  if (!historyRows || historyRows.length === 0) {
    return []
  }

  return historyRows.slice(-HISTORY_POINT_LIMITS[range]).map((row) => {
    const bucketDate = new Date(`${row.bucket_date}T00:00:00+09:00`)
    const label = range === '7D' ? KST_DAY_FORMATTER.format(bucketDate) : KST_MONTH_DAY_FORMATTER.format(bucketDate)

    return {
      label,
      ccu: Math.round(row.avg_ccu),
    }
  })
}

const buildPriceLine = (price: GameLatestPrice | null) => {
  if (!price) {
    return 'Pending'
  }

  const currentPrice = formatMinorPrice(price.final_price_minor, price.currency_code, price.is_free)

  if (price.is_free) {
    return `${currentPrice} · Free`
  }

  return `${currentPrice} · ${price.discount_percent > 0 ? `-${price.discount_percent}%` : 'No sale'}`
}

const buildReviewSummary = (reviews: GameLatestReviews | null) => {
  if (!reviews) {
    return '리뷰 집계 대기 중'
  }

  return getReviewSummaryFallback(reviews.positive_ratio)
}

const buildDetailCards = (row: SteamBaseRow, historyRows: GameDaily90dCcu[] | undefined): SteamDetailCard[] => {
  const sevenDayAverage = getSevenDayAverage(historyRows)

  return [
    {
      label: 'CCU',
      rows: [
        { label: 'Live CCU', value: row.ccu ? formatCompact(row.ccu.ccu) : 'Pending' },
        {
          label: 'Δ CCU',
          value:
            row.ccu && row.ccu.delta_ccu_pct !== null && !row.ccu.missing_flag
              ? formatSignedPercent(row.ccu.delta_ccu_pct)
              : row.ccu
                ? 'No prior delta'
                : 'Pending',
        },
        { label: '7D avg', value: sevenDayAverage !== null ? formatCompact(sevenDayAverage) : 'Pending' },
      ],
    },
    {
      label: 'Reviews',
      subtitle: row.reviews ? getReviewSummaryFallback(row.reviews.positive_ratio) : undefined,
      rows: [
        {
          label: 'Recent positive',
          value: row.reviews ? formatPercentRatio(row.reviews.positive_ratio) : 'Pending',
        },
        {
          label: 'Recent reviews',
          value:
            row.reviews && row.reviews.delta_total_reviews !== null
              ? formatInteger(row.reviews.delta_total_reviews)
              : row.reviews
                ? 'No prior delta'
                : 'Pending',
        },
        {
          label: 'Lifetime reviews',
          value: row.reviews ? formatCompactInteger(row.reviews.total_reviews) : 'Pending',
        },
      ],
    },
    {
      label: 'Price',
      rows: [
        {
          label: 'Current price',
          value: row.price ? formatMinorPrice(row.price.final_price_minor, row.price.currency_code, row.price.is_free) : 'Pending',
        },
        {
          label: 'Discount',
          value:
            row.price
              ? row.price.is_free
                ? 'Free'
                : row.price.discount_percent > 0
                  ? `-${row.price.discount_percent}%`
                  : 'No sale'
              : 'Pending',
        },
        {
          label: 'Sale ends in',
          value: 'Pending',
        },
      ],
    },
  ]
}

const getSurfaceContext = (row: SteamBaseRow, mode: SteamDiscoverMode) => {
  if (mode === 'Top Selling') {
    return row.canonicalGameId === null
      ? `#${row.rank} in Top Selling · canonical mapping pending`
      : `#${row.rank} in Top Selling`
  }

  return `#${row.rank} in Most Played`
}

const buildTopSellingRows = (data: SteamOverviewApiData): SteamBaseRow[] => {
  const ccuByGameId = new Map(data.ccuRows.map((row) => [row.canonical_game_id, row] as const))
  const priceByGameId = new Map(data.priceRows.map((row) => [row.canonical_game_id, row] as const))
  const reviewsByGameId = new Map(data.reviewRows.map((row) => [row.canonical_game_id, row] as const))

  return data.rankings.map((row) => ({
    id: row.canonical_game_id !== null ? `canonical:${row.canonical_game_id}` : `steam:${row.steam_appid}`,
    canonicalGameId: row.canonical_game_id,
    steamAppId: row.steam_appid,
    title: row.canonical_name ?? `Steam app ${row.steam_appid}`,
    rank: row.rank_position,
    ccu: row.canonical_game_id !== null ? ccuByGameId.get(row.canonical_game_id) ?? null : null,
    price: row.canonical_game_id !== null ? priceByGameId.get(row.canonical_game_id) ?? null : null,
    reviews: row.canonical_game_id !== null ? reviewsByGameId.get(row.canonical_game_id) ?? null : null,
  }))
}

const buildMostPlayedRows = (data: SteamOverviewApiData): SteamBaseRow[] => {
  const priceByGameId = new Map(data.priceRows.map((row) => [row.canonical_game_id, row] as const))
  const reviewsByGameId = new Map(data.reviewRows.map((row) => [row.canonical_game_id, row] as const))

  return data.ccuRows.map((row, index) => ({
    id: `canonical:${row.canonical_game_id}`,
    canonicalGameId: row.canonical_game_id,
    steamAppId: null,
    title: row.canonical_name,
    rank: index + 1,
    ccu: row,
    price: priceByGameId.get(row.canonical_game_id) ?? null,
    reviews: reviewsByGameId.get(row.canonical_game_id) ?? null,
  }))
}

export function buildSteamGames({
  mode,
  searchQuery,
  data,
  historyByCanonicalGameId,
  historyLoadingCanonicalGameId,
  historyErrorCanonicalGameIds,
}: BuildSteamGamesArgs): SteamReferenceGame[] {
  const normalizedSearch = searchQuery.trim().toLowerCase()
  const baseRows = mode === 'Top Selling' ? buildTopSellingRows(data) : buildMostPlayedRows(data)

  return baseRows
    .filter((row) => (normalizedSearch.length > 0 ? row.title.toLowerCase().includes(normalizedSearch) : true))
    .slice(0, 4)
    .map((row) => {
      const historyRows = row.canonicalGameId !== null ? historyByCanonicalGameId[row.canonicalGameId] : undefined
      const cardStates = getCardStates(row, historyRows, historyLoadingCanonicalGameId)

      return {
        id: row.id,
        canonicalGameId: row.canonicalGameId,
        title: row.title,
        rank: row.rank,
        liveCcu: row.ccu ? formatCompact(row.ccu.ccu) : 'Pending',
        priceLine: buildPriceLine(row.price),
        reviewSummary: buildReviewSummary(row.reviews),
        statusBadge: getStatusBadge(cardStates),
        verdictChips: getVerdictChips(row),
        surfaceContext: getSurfaceContext(row, mode),
        detailCards: buildDetailCards(row, historyRows),
        timeline: {
          '7D': buildTimelinePoints(historyRows, '7D'),
          '30D': buildTimelinePoints(historyRows, '30D'),
          '90D': buildTimelinePoints(historyRows, '90D'),
        },
        cardStates,
        chartState: getChartState(row, historyRows, historyLoadingCanonicalGameId, historyErrorCanonicalGameIds),
      }
    })
}

export const getSteamQueryErrorMessage = (error: unknown) => {
  if (error instanceof Error) {
    return error.message
  }

  return '지금은 Steam 소스 뷰를 불러올 수 없습니다.'
}
