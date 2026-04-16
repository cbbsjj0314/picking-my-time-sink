import type { GameExploreOverview } from '../api/games'
import { formatWon } from './format'

export interface SteamExploreTableRow {
  id: string
  canonicalGameId: number
  steamAppId: number | null
  gameTitle: string
  currentCcuLabel: string
  currentCcuSupportLabel: string | null
  currentCcuTitle: string | null
  avgCcuLabel: string
  avgCcuSupportLabel: string | null
  peakCcuLabel: string
  peakCcuSupportLabel: string | null
  reviewsAddedLabel: string
  reviewsAddedSupportLabel: string | null
  positiveShareLabel: string
  positiveShareSupportLabel: string | null
  priceLabel: string
  priceSupportLabel: string | null
  priceTitle: string | null
  ccuAnchorLabel: string | null
  reviewAnchorLabel: string | null
}

const EMPTY_CELL = '-'

const KST_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: false,
  timeZone: 'Asia/Seoul',
})

const KST_DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'Asia/Seoul',
})

const formatInteger = (value: number) => Math.round(value).toLocaleString('en-US')

const formatOptionalInteger = (value: number | null) => (value === null ? EMPTY_CELL : formatInteger(value))

const formatSignedInteger = (value: number) => {
  if (value > 0) {
    return `+${formatInteger(value)}`
  }

  return formatInteger(value)
}

const formatSignedPercentValue = (value: number) => {
  const formatted = `${Math.abs(value).toFixed(1)}%`

  if (value > 0) {
    return `+${formatted}`
  }

  if (value < 0) {
    return `-${formatted}`
  }

  return formatted
}

const formatDelta = (deltaAbs: number | null, deltaPct: number | null) => {
  if (deltaAbs === null && deltaPct === null) {
    return null
  }

  if (deltaAbs !== null && deltaPct !== null) {
    return `Δ ${formatSignedInteger(deltaAbs)} (${formatSignedPercentValue(deltaPct)})`
  }

  if (deltaAbs !== null) {
    return `Δ ${formatSignedInteger(deltaAbs)}`
  }

  if (deltaPct !== null) {
    return `Δ ${formatSignedPercentValue(deltaPct)}`
  }

  return null
}

const formatRatio = (value: number | null) => {
  if (value === null) {
    return EMPTY_CELL
  }

  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value * 100)}%`
}

const parseDate = (value: string) => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

const formatKstDateTime = (value: string | null) => {
  if (value === null) {
    return null
  }

  const date = parseDate(value)
  return date ? `${KST_DATE_TIME_FORMATTER.format(date)} KST` : value
}

const formatKstDate = (value: string | null) => {
  if (value === null) {
    return null
  }

  const date = parseDate(`${value}T00:00:00+09:00`)
  return date ? `${KST_DATE_FORMATTER.format(date)} KST` : value
}

const formatPrice = (row: GameExploreOverview) => {
  if (row.is_free) {
    return 'Free'
  }

  if (row.final_price_minor === null || row.currency_code === null) {
    return EMPTY_CELL
  }

  if (row.currency_code === 'KRW') {
    return formatWon(Math.round(row.final_price_minor / 100))
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: row.currency_code,
    maximumFractionDigits: 2,
  }).format(row.final_price_minor / 100)
}

const formatDiscountSupport = (row: GameExploreOverview) =>
  !row.is_free && row.discount_percent !== null && row.discount_percent > 0 ? `-${row.discount_percent}%` : null

const formatCurrentCcuSupport = (row: GameExploreOverview) => {
  const deltaLabel = formatDelta(row.current_delta_ccu_abs, row.current_delta_ccu_pct)

  if (deltaLabel !== null) {
    return deltaLabel
  }

  return row.current_ccu !== null && row.current_ccu_missing_flag ? 'No comparison' : null
}

const formatMissingComparisonSupport = (value: number | null) => (value === null ? null : 'No comparison')

const buildSteamExploreTableRow = (row: GameExploreOverview): SteamExploreTableRow => ({
  id: `canonical:${row.canonical_game_id}`,
  canonicalGameId: row.canonical_game_id,
  steamAppId: row.steam_appid,
  gameTitle: row.canonical_name,
  currentCcuLabel: formatOptionalInteger(row.current_ccu),
  currentCcuSupportLabel: formatCurrentCcuSupport(row),
  currentCcuTitle: formatKstDateTime(row.ccu_bucket_time),
  avgCcuLabel: formatOptionalInteger(row.period_avg_ccu_7d),
  avgCcuSupportLabel: formatDelta(row.delta_period_avg_ccu_7d_abs, row.delta_period_avg_ccu_7d_pct),
  peakCcuLabel: formatOptionalInteger(row.period_peak_ccu_7d),
  peakCcuSupportLabel: formatDelta(row.delta_period_peak_ccu_7d_abs, row.delta_period_peak_ccu_7d_pct),
  reviewsAddedLabel: formatOptionalInteger(row.reviews_added_7d),
  reviewsAddedSupportLabel: formatMissingComparisonSupport(row.reviews_added_7d),
  positiveShareLabel: formatRatio(row.period_positive_ratio_7d),
  positiveShareSupportLabel: formatMissingComparisonSupport(row.period_positive_ratio_7d),
  priceLabel: formatPrice(row),
  priceSupportLabel: formatDiscountSupport(row),
  priceTitle: formatKstDateTime(row.price_bucket_time),
  ccuAnchorLabel: formatKstDate(row.ccu_period_anchor_date),
  reviewAnchorLabel: formatKstDate(row.reviews_snapshot_date),
})

export function buildSteamExploreTableRows(rows: GameExploreOverview[], searchQuery: string): SteamExploreTableRow[] {
  const normalizedSearch = searchQuery.trim().toLowerCase()

  return rows
    .map(buildSteamExploreTableRow)
    .filter((row) => {
      if (normalizedSearch.length === 0) {
        return true
      }

      return row.gameTitle.toLowerCase().includes(normalizedSearch)
    })
}
