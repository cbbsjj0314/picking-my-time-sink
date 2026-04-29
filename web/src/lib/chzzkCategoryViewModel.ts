import type { ChzzkCategoryOverview } from '../api/chzzk'

export const chzzkCategorySortKeys = [
  'category',
  'latestViewers',
  'viewerHours',
  'avgViewers',
  'peakViewers',
  'avgChannels',
  'peakChannels',
  'viewersPerChannel',
] as const

export type ChzzkCategorySortKey = (typeof chzzkCategorySortKeys)[number]
export type ChzzkCategorySortDirection = 'asc' | 'desc'

export interface ChzzkCategorySortState {
  key: ChzzkCategorySortKey
  direction: ChzzkCategorySortDirection
}

type ChzzkCategorySortValue = number | string | null
type ChzzkCategorySortValueMap = Record<ChzzkCategorySortKey, ChzzkCategorySortValue>

export interface ChzzkCategoryTableRow {
  id: string
  categoryId: string
  categoryName: string
  latestViewersLabel: string
  latestViewersTitle: string | null
  viewerHoursLabel: string
  avgViewersLabel: string
  peakViewersLabel: string
  avgChannelsLabel: string
  avgChannelsTitle: string
  peakChannelsLabel: string
  peakChannelsTitle: string
  viewersPerChannelLabel: string
  viewersPerChannelTitle: string
  coverageLabel: string
  boundedSampleLabel: string | null
  boundedSampleTitle: string | null
  observedBucketLabel: string
  observedWindowLabel: string | null
  sortValues: ChzzkCategorySortValueMap
}

export const DEFAULT_CHZZK_CATEGORY_SORT_STATE: ChzzkCategorySortState = {
  key: 'viewerHours',
  direction: 'desc',
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

const finiteNumberOrNull = (value: number | null) =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

const formatInteger = (value: number) => Math.round(value).toLocaleString('en-US')

const formatOptionalInteger = (value: number | null) => {
  const finiteValue = finiteNumberOrNull(value)
  return finiteValue === null ? EMPTY_CELL : formatInteger(finiteValue)
}

const formatDecimal = (value: number | null, maximumFractionDigits = 1) => {
  const finiteValue = finiteNumberOrNull(value)

  if (finiteValue === null) {
    return EMPTY_CELL
  }

  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits,
  }).format(finiteValue)
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

const formatObservedWindow = (row: ChzzkCategoryOverview) => {
  const minBucket = formatKstDateTime(row.bucket_time_min)
  const maxBucket = formatKstDateTime(row.bucket_time_max)

  if (minBucket === null || maxBucket === null) {
    return null
  }

  if (minBucket === maxBucket) {
    return `Observed bucket ${minBucket}`
  }

  return `Observed buckets ${minBucket} - ${maxBucket}`
}

const formatCoverageLabel = (row: ChzzkCategoryOverview) =>
  `${formatInteger(row.observed_bucket_count)} observed ${row.observed_bucket_count === 1 ? 'bucket' : 'buckets'}`

const getBoundedSampleLabel = (row: ChzzkCategoryOverview) =>
  row.bounded_sample_caveat === 'bounded_sample' ? 'Bounded sample' : null

const getBoundedSampleTitle = (row: ChzzkCategoryOverview) =>
  row.bounded_sample_caveat === 'bounded_sample'
    ? 'Bounded pagination/live-list sample; not a full population claim.'
    : null

const buildSortValues = (row: ChzzkCategoryOverview): ChzzkCategorySortValueMap => ({
  category: row.category_name.toLocaleLowerCase('en-US'),
  latestViewers: finiteNumberOrNull(row.latest_viewers_observed),
  viewerHours: finiteNumberOrNull(row.viewer_hours_observed),
  avgViewers: finiteNumberOrNull(row.avg_viewers_observed),
  peakViewers: finiteNumberOrNull(row.peak_viewers_observed),
  avgChannels: finiteNumberOrNull(row.avg_channels_observed),
  peakChannels: finiteNumberOrNull(row.peak_channels_observed),
  viewersPerChannel: finiteNumberOrNull(row.viewer_per_channel_observed),
})

const buildChzzkCategoryTableRow = (row: ChzzkCategoryOverview): ChzzkCategoryTableRow => ({
  id: `chzzk:${row.chzzk_category_id}`,
  categoryId: row.chzzk_category_id,
  categoryName: row.category_name,
  latestViewersLabel: formatOptionalInteger(row.latest_viewers_observed),
  latestViewersTitle: formatKstDateTime(row.latest_bucket_time),
  viewerHoursLabel: formatDecimal(row.viewer_hours_observed),
  avgViewersLabel: formatDecimal(row.avg_viewers_observed),
  peakViewersLabel: formatOptionalInteger(row.peak_viewers_observed),
  avgChannelsLabel: formatDecimal(row.avg_channels_observed),
  avgChannelsTitle: 'Average observed bucket live_count; not unique channels.',
  peakChannelsLabel: formatOptionalInteger(row.peak_channels_observed),
  peakChannelsTitle: 'Maximum observed bucket live_count; not unique channels.',
  viewersPerChannelLabel: formatDecimal(row.viewer_per_channel_observed),
  viewersPerChannelTitle: 'API field viewer_per_channel_observed; observed live_count ratio.',
  coverageLabel: formatCoverageLabel(row),
  boundedSampleLabel: getBoundedSampleLabel(row),
  boundedSampleTitle: getBoundedSampleTitle(row),
  observedBucketLabel: `Coverage state: ${row.coverage_status}`,
  observedWindowLabel: formatObservedWindow(row),
  sortValues: buildSortValues(row),
})

const DEFAULT_SORT_DIRECTION_BY_KEY: Record<ChzzkCategorySortKey, ChzzkCategorySortDirection> = {
  category: 'asc',
  latestViewers: 'desc',
  viewerHours: 'desc',
  avgViewers: 'desc',
  peakViewers: 'desc',
  avgChannels: 'desc',
  peakChannels: 'desc',
  viewersPerChannel: 'desc',
}

const compareNullableNumbers = (left: number | null, right: number | null, direction: ChzzkCategorySortDirection) => {
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

const compareStrings = (left: string, right: string, direction: ChzzkCategorySortDirection) =>
  direction === 'desc' ? right.localeCompare(left) : left.localeCompare(right)

export function toggleChzzkCategorySort(
  currentSort: ChzzkCategorySortState,
  key: ChzzkCategorySortKey,
): ChzzkCategorySortState {
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

export function sortChzzkCategoryTableRows(
  rows: ChzzkCategoryTableRow[],
  sortState: ChzzkCategorySortState,
): ChzzkCategoryTableRow[] {
  return [...rows].sort((left, right) => {
    const primaryComparison =
      sortState.key === 'category'
        ? compareStrings(left.sortValues.category as string, right.sortValues.category as string, sortState.direction)
        : compareNullableNumbers(
            left.sortValues[sortState.key] as number | null,
            right.sortValues[sortState.key] as number | null,
            sortState.direction,
          )

    if (primaryComparison !== 0) {
      return primaryComparison
    }

    return left.categoryId.localeCompare(right.categoryId)
  })
}

export function buildChzzkCategoryTableRows(
  rows: ChzzkCategoryOverview[],
  searchQuery: string,
  sortState: ChzzkCategorySortState,
): ChzzkCategoryTableRow[] {
  const normalizedSearch = searchQuery.trim().toLowerCase()

  return sortChzzkCategoryTableRows(
    rows.map(buildChzzkCategoryTableRow).filter((row) => {
      if (normalizedSearch.length === 0) {
        return true
      }

      return row.categoryName.toLowerCase().includes(normalizedSearch)
    }),
    sortState,
  )
}

export const getChzzkQueryErrorMessage = (error: unknown) => {
  if (error instanceof Error) {
    return error.message
  }

  return '지금은 Chzzk 소스 뷰를 불러올 수 없습니다.'
}
