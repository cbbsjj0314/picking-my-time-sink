import type { GameExploreOverview } from '../api/games'
import { formatWon } from './format'

export const steamExploreSortKeys = [
  'game',
  'currentCcu',
  'estimatedPlayerHours',
  'avgCcu',
  'peakCcu',
  'reviewsAdded',
  'positiveShare',
  'price',
] as const

export type SteamExploreSortKey = (typeof steamExploreSortKeys)[number]
export type SteamExploreSortDirection = 'asc' | 'desc'

export interface SteamExploreSortState {
  key: SteamExploreSortKey
  direction: SteamExploreSortDirection
}

export const DEFAULT_STEAM_EXPLORE_SORT_STATE: SteamExploreSortState = {
  key: 'estimatedPlayerHours',
  direction: 'desc',
}

type SteamExploreSortValue = number | string | null
type SteamExploreSortValueMap = Record<SteamExploreSortKey, SteamExploreSortValue>

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
  estimatedPlayerHoursLabel: string
  estimatedPlayerHoursSupportLabel: string | null
  estimatedPlayerHoursCaveatLabel: string | null
  estimatedPlayerHoursCaveatTitle: string | null
  reviewsAddedLabel: string
  reviewsAddedSupportLabel: string | null
  positiveShareLabel: string
  positiveShareSupportLabel: string | null
  periodHistoryCollectingLabel: string | null
  periodMetricsCollecting: boolean
  priceLabel: string
  priceSupportLabel: string | null
  priceTitle: string | null
  ccuAnchorLabel: string | null
  reviewAnchorLabel: string | null
  sortValues: SteamExploreSortValueMap
}

const EMPTY_CELL = '-'
const EXPLORE_PERIOD = {
  periodLabel: '7 days',
  periodDays: 7,
} as const

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

const finiteNumberOrNull = (value: number | null) =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

export const buildPeriodHistoryCollectingLabel = ({
  periodLabel,
  periodDays,
}: {
  periodLabel: string
  periodDays: number
}) => {
  const normalizedLabel = periodLabel.trim()
  const fallbackLabel = `${periodDays} ${periodDays === 1 ? 'day' : 'days'}`

  return `Collecting ${normalizedLabel.length > 0 ? normalizedLabel : fallbackLabel} of history`
}

const PERIOD_HISTORY_COLLECTING_LABEL = buildPeriodHistoryCollectingLabel(EXPLORE_PERIOD)

const formatInteger = (value: number) => Math.round(value).toLocaleString('en-US')

const formatOptionalInteger = (value: number | null) => {
  const finiteValue = finiteNumberOrNull(value)
  return finiteValue === null ? EMPTY_CELL : formatInteger(finiteValue)
}

const formatCoveragePercent = (value: number) => {
  const cappedValue = Math.min(1, Math.max(0, value))
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(cappedValue * 100)}%`
}

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
  const finiteDeltaAbs = finiteNumberOrNull(deltaAbs)
  const finiteDeltaPct = finiteNumberOrNull(deltaPct)

  if (finiteDeltaAbs === null && finiteDeltaPct === null) {
    return null
  }

  if (finiteDeltaAbs !== null && finiteDeltaPct !== null) {
    return `Δ ${formatSignedInteger(finiteDeltaAbs)} (${formatSignedPercentValue(finiteDeltaPct)})`
  }

  if (finiteDeltaAbs !== null) {
    return `Δ ${formatSignedInteger(finiteDeltaAbs)}`
  }

  if (finiteDeltaPct !== null) {
    return `Δ ${formatSignedPercentValue(finiteDeltaPct)}`
  }

  return null
}

const formatPointDelta = (deltaPp: number | null) => {
  const finiteDeltaPp = finiteNumberOrNull(deltaPp)

  if (finiteDeltaPp === null) {
    return null
  }

  const formatted = `${Math.abs(finiteDeltaPp).toFixed(1)} pp`

  if (finiteDeltaPp > 0) {
    return `Δ +${formatted}`
  }

  if (finiteDeltaPp < 0) {
    return `Δ -${formatted}`
  }

  return `Δ ${formatted}`
}

const formatRatio = (value: number | null) => {
  const finiteValue = finiteNumberOrNull(value)

  if (finiteValue === null) {
    return EMPTY_CELL
  }

  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(finiteValue * 100)}%`
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
  if (row.is_free === true) {
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
  row.is_free !== true && row.discount_percent !== null && row.discount_percent > 0 ? `-${row.discount_percent}%` : null

const formatCurrentCcuSupport = (row: GameExploreOverview) => {
  return formatDelta(row.current_delta_ccu_abs, row.current_delta_ccu_pct)
}

const formatPeriodMetricSupport = (value: number | null, support: string | null) =>
  finiteNumberOrNull(value) === null ? PERIOD_HISTORY_COLLECTING_LABEL : support

const getEstimatedPlayerHoursCoverageRatio = (row: GameExploreOverview) => {
  const ratio = finiteNumberOrNull(row.estimated_player_hours_7d_coverage_ratio)

  if (ratio !== null) {
    return Math.min(1, Math.max(0, ratio))
  }

  const observedCount = finiteNumberOrNull(row.estimated_player_hours_7d_observed_bucket_count)
  const expectedCount = finiteNumberOrNull(row.estimated_player_hours_7d_expected_bucket_count)

  if (observedCount === null || expectedCount === null || expectedCount <= 0) {
    return null
  }

  return Math.min(1, Math.max(0, observedCount / expectedCount))
}

const getPartialEstimatedPlayerHoursCaveatTitle = (row: GameExploreOverview) => {
  const observedCount = finiteNumberOrNull(row.estimated_player_hours_7d_observed_bucket_count)
  const expectedCount = finiteNumberOrNull(row.estimated_player_hours_7d_expected_bucket_count)
  const coverageRatio = getEstimatedPlayerHoursCoverageRatio(row)

  if (observedCount === null || expectedCount === null || expectedCount <= 0 || coverageRatio === null) {
    return 'Strict 7D estimate pending.'
  }

  const missingCount = Math.max(0, expectedCount - observedCount)
  return `${formatCoveragePercent(coverageRatio)} observed. Missing ${formatInteger(missingCount)} of ${formatInteger(
    expectedCount,
  )} buckets. Strict 7D estimate pending.`
}

const getEstimatedPlayerHoursDisplay = (row: GameExploreOverview) => {
  const strictPlayerHours = finiteNumberOrNull(row.estimated_player_hours_7d)
  const observedPlayerHours = finiteNumberOrNull(row.observed_player_hours_7d)
  const observedCount = finiteNumberOrNull(row.estimated_player_hours_7d_observed_bucket_count)
  const expectedCount = finiteNumberOrNull(row.estimated_player_hours_7d_expected_bucket_count)
  const hasPartialObservedValue =
    strictPlayerHours === null &&
    observedPlayerHours !== null &&
    observedCount !== null &&
    expectedCount !== null &&
    observedCount > 0 &&
    observedCount < expectedCount

  if (strictPlayerHours !== null) {
    return {
      label: formatInteger(strictPlayerHours),
      supportLabel: formatDelta(row.delta_estimated_player_hours_7d_abs, row.delta_estimated_player_hours_7d_pct),
      caveatLabel: null,
      caveatTitle: null,
    }
  }

  if (hasPartialObservedValue) {
    return {
      label: formatInteger(observedPlayerHours),
      supportLabel: 'Strict 7D estimate pending.',
      caveatLabel: 'Observed',
      caveatTitle: getPartialEstimatedPlayerHoursCaveatTitle(row),
    }
  }

  return {
    label: EMPTY_CELL,
    supportLabel: PERIOD_HISTORY_COLLECTING_LABEL,
    caveatLabel: null,
    caveatTitle: null,
  }
}

const DEFAULT_SORT_DIRECTION_BY_KEY: Record<SteamExploreSortKey, SteamExploreSortDirection> = {
  game: 'asc',
  currentCcu: 'desc',
  estimatedPlayerHours: 'desc',
  avgCcu: 'desc',
  peakCcu: 'desc',
  reviewsAdded: 'desc',
  positiveShare: 'desc',
  price: 'desc',
}

const arePeriodMetricsCollecting = (row: GameExploreOverview) =>
  [
    row.period_avg_ccu_7d,
    row.period_peak_ccu_7d,
    row.estimated_player_hours_7d,
    row.observed_player_hours_7d,
    row.reviews_added_7d,
    row.period_positive_ratio_7d,
  ].every((value) => finiteNumberOrNull(value) === null)

const buildSortValues = (row: GameExploreOverview): SteamExploreSortValueMap => {
  // Period-aware columns currently map to the fixed Last 7 Days Explore contract.
  return {
    game: row.canonical_name.toLocaleLowerCase('en-US'),
    currentCcu: finiteNumberOrNull(row.current_ccu),
    estimatedPlayerHours: finiteNumberOrNull(row.estimated_player_hours_7d),
    avgCcu: finiteNumberOrNull(row.period_avg_ccu_7d),
    peakCcu: finiteNumberOrNull(row.period_peak_ccu_7d),
    reviewsAdded: finiteNumberOrNull(row.reviews_added_7d),
    positiveShare: finiteNumberOrNull(row.period_positive_ratio_7d),
    price: finiteNumberOrNull(row.final_price_minor),
  }
}

const buildSteamExploreTableRow = (row: GameExploreOverview): SteamExploreTableRow => {
  const periodMetricsCollecting = arePeriodMetricsCollecting(row)
  const estimatedPlayerHoursDisplay = getEstimatedPlayerHoursDisplay(row)

  return {
    id: `canonical:${row.canonical_game_id}`,
    canonicalGameId: row.canonical_game_id,
    steamAppId: row.steam_appid,
    gameTitle: row.canonical_name,
    currentCcuLabel: formatOptionalInteger(row.current_ccu),
    currentCcuSupportLabel: formatCurrentCcuSupport(row),
    currentCcuTitle: formatKstDateTime(row.ccu_bucket_time),
    avgCcuLabel: formatOptionalInteger(row.period_avg_ccu_7d),
    avgCcuSupportLabel: formatPeriodMetricSupport(
      row.period_avg_ccu_7d,
      formatDelta(row.delta_period_avg_ccu_7d_abs, row.delta_period_avg_ccu_7d_pct),
    ),
    peakCcuLabel: formatOptionalInteger(row.period_peak_ccu_7d),
    peakCcuSupportLabel: formatPeriodMetricSupport(
      row.period_peak_ccu_7d,
      formatDelta(row.delta_period_peak_ccu_7d_abs, row.delta_period_peak_ccu_7d_pct),
    ),
    estimatedPlayerHoursLabel: estimatedPlayerHoursDisplay.label,
    estimatedPlayerHoursSupportLabel: estimatedPlayerHoursDisplay.supportLabel,
    estimatedPlayerHoursCaveatLabel: estimatedPlayerHoursDisplay.caveatLabel,
    estimatedPlayerHoursCaveatTitle: estimatedPlayerHoursDisplay.caveatTitle,
    reviewsAddedLabel: formatOptionalInteger(row.reviews_added_7d),
    reviewsAddedSupportLabel: formatPeriodMetricSupport(
      row.reviews_added_7d,
      formatDelta(row.delta_reviews_added_7d_abs, row.delta_reviews_added_7d_pct),
    ),
    positiveShareLabel: formatRatio(row.period_positive_ratio_7d),
    positiveShareSupportLabel: formatPeriodMetricSupport(
      row.period_positive_ratio_7d,
      formatPointDelta(row.delta_period_positive_ratio_7d_pp),
    ),
    periodHistoryCollectingLabel: periodMetricsCollecting ? PERIOD_HISTORY_COLLECTING_LABEL : null,
    periodMetricsCollecting,
    priceLabel: formatPrice(row),
    priceSupportLabel: formatDiscountSupport(row),
    priceTitle: formatKstDateTime(row.price_bucket_time),
    ccuAnchorLabel: formatKstDate(row.ccu_period_anchor_date),
    reviewAnchorLabel: formatKstDate(row.reviews_snapshot_date),
    sortValues: buildSortValues(row),
  }
}

const compareNullableNumbers = (left: number | null, right: number | null, direction: SteamExploreSortDirection) => {
  if (left === null && right === null) {
    return 0
  }

  if (left === null) {
    return 1
  }

  if (right === null) {
    return -1
  }

  return direction === 'desc' ? right - left : left - right
}

const compareStrings = (left: string, right: string, direction: SteamExploreSortDirection) =>
  direction === 'desc' ? right.localeCompare(left) : left.localeCompare(right)

const compareByCurrentCcuDesc = (left: SteamExploreTableRow, right: SteamExploreTableRow) =>
  compareNullableNumbers(left.sortValues.currentCcu as number | null, right.sortValues.currentCcu as number | null, 'desc')

export function toggleSteamExploreSort(
  currentSort: SteamExploreSortState,
  key: SteamExploreSortKey,
): SteamExploreSortState {
  if (currentSort.key !== key) {
    return {
      key,
      direction: DEFAULT_SORT_DIRECTION_BY_KEY[key],
    }
  }

  return {
    key,
    direction: currentSort.direction === 'desc' ? 'asc' : 'desc',
  }
}

export function sortSteamExploreTableRows(
  rows: SteamExploreTableRow[],
  sortState: SteamExploreSortState,
): SteamExploreTableRow[] {
  return [...rows].sort((left, right) => {
    const primaryComparison =
      sortState.key === 'game'
        ? compareStrings(left.sortValues.game as string, right.sortValues.game as string, sortState.direction)
        : compareNullableNumbers(
            left.sortValues[sortState.key] as number | null,
            right.sortValues[sortState.key] as number | null,
            sortState.direction,
          )

    if (primaryComparison !== 0) {
      return primaryComparison
    }

    if (sortState.key !== 'currentCcu') {
      const currentCcuComparison = compareByCurrentCcuDesc(left, right)

      if (currentCcuComparison !== 0) {
        return currentCcuComparison
      }
    }

    return left.canonicalGameId - right.canonicalGameId
  })
}

export function buildSteamExploreTableRows(
  rows: GameExploreOverview[],
  searchQuery: string,
  sortState: SteamExploreSortState,
): SteamExploreTableRow[] {
  const normalizedSearch = searchQuery.trim().toLowerCase()

  return sortSteamExploreTableRows(
    rows.map(buildSteamExploreTableRow).filter((row) => {
      if (normalizedSearch.length === 0) {
        return true
      }

      return row.gameTitle.toLowerCase().includes(normalizedSearch)
    }),
    sortState,
  )
}
