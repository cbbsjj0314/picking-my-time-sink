import type { CombinedGameOverview } from '../api/combined'

export const combinedGameOverviewSortKeys = [
  'canonicalName',
  'canonicalGameId',
  'steamSourceAvailable',
  'chzzkMappingAvailable',
  'latestBucketTime',
] as const

export type CombinedGameOverviewSortKey = (typeof combinedGameOverviewSortKeys)[number]
export type CombinedGameOverviewSortDirection = 'asc' | 'desc'

export interface CombinedGameOverviewSortState {
  key: CombinedGameOverviewSortKey
  direction: CombinedGameOverviewSortDirection
}

type CombinedGameOverviewSortValue = boolean | number | string | null
type CombinedGameOverviewSortValueMap = Record<CombinedGameOverviewSortKey, CombinedGameOverviewSortValue>

export interface CombinedGameOverviewTableRow {
  id: string
  canonicalGameId: number
  canonicalName: string
  steamAppidLabel: string
  steamStoreUrl: string | null
  steamSourceLabel: string
  steamSourceTitle: string
  chzzkMappingLabel: string
  chzzkMappingTitle: string
  chzzkCategoryIdLabel: string
  categoryNameLabel: string
  categoryTypeLabel: string
  categoryTypeTitle: string
  latestBucketTimeLabel: string
  latestBucketTimeTitle: string
  sortValues: CombinedGameOverviewSortValueMap
}

export const DEFAULT_COMBINED_GAME_OVERVIEW_SORT_STATE: CombinedGameOverviewSortState = {
  key: 'canonicalName',
  direction: 'asc',
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

const formatOptionalText = (value: string | null, fallback = EMPTY_CELL) => {
  const trimmedValue = value?.trim() ?? ''
  return trimmedValue.length === 0 ? fallback : trimmedValue
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

const formatLatestBucketTimeLabel = (value: string | null) => formatKstDateTime(value) ?? 'No trusted Chzzk context'

const buildSortValues = (row: CombinedGameOverview): CombinedGameOverviewSortValueMap => ({
  canonicalName: row.canonical_name.toLocaleLowerCase('en-US'),
  canonicalGameId: row.canonical_game_id,
  steamSourceAvailable: row.steam_source_available,
  chzzkMappingAvailable: row.chzzk_mapping_available,
  latestBucketTime: row.latest_bucket_time,
})

const buildCombinedGameOverviewTableRow = (row: CombinedGameOverview): CombinedGameOverviewTableRow => ({
  id: `combined:${row.canonical_game_id}`,
  canonicalGameId: row.canonical_game_id,
  canonicalName: row.canonical_name,
  steamAppidLabel: row.steam_appid === null ? EMPTY_CELL : String(row.steam_appid),
  steamStoreUrl: row.steam_appid === null ? null : `https://store.steampowered.com/app/${row.steam_appid}`,
  steamSourceLabel: row.steam_source_available ? 'Steam source available' : 'Steam source unavailable',
  steamSourceTitle: 'Steam source availability from the Combined overview endpoint.',
  chzzkMappingLabel: row.chzzk_mapping_available ? 'Trusted mapping available' : 'No trusted Chzzk mapping',
  chzzkMappingTitle: 'Trusted Chzzk mapping identity availability only.',
  chzzkCategoryIdLabel: formatOptionalText(row.chzzk_category_id),
  categoryNameLabel: formatOptionalText(row.category_name, 'No trusted Chzzk mapping'),
  categoryTypeLabel: formatOptionalText(row.category_type),
  categoryTypeTitle: 'Provider category type from trusted Chzzk mapping context; not canonical identity by itself.',
  latestBucketTimeLabel: formatLatestBucketTimeLabel(row.latest_bucket_time),
  latestBucketTimeTitle: 'Nullable trusted Chzzk mapping/context timestamp from the Combined overview endpoint.',
  sortValues: buildSortValues(row),
})

const DEFAULT_SORT_DIRECTION_BY_KEY: Record<
  CombinedGameOverviewSortKey,
  CombinedGameOverviewSortDirection
> = {
  canonicalName: 'asc',
  canonicalGameId: 'asc',
  steamSourceAvailable: 'desc',
  chzzkMappingAvailable: 'desc',
  latestBucketTime: 'desc',
}

const compareNullableNumbers = (
  left: number | null,
  right: number | null,
  direction: CombinedGameOverviewSortDirection,
) => {
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

const compareStrings = (left: string, right: string, direction: CombinedGameOverviewSortDirection) =>
  direction === 'desc' ? right.localeCompare(left) : left.localeCompare(right)

const compareBooleans = (left: boolean, right: boolean, direction: CombinedGameOverviewSortDirection) => {
  if (left === right) {
    return 0
  }

  const comparison = Number(left) - Number(right)
  return direction === 'desc' ? -comparison : comparison
}

const compareNullableDateStrings = (
  left: string | null,
  right: string | null,
  direction: CombinedGameOverviewSortDirection,
) => {
  const leftTime = left === null ? null : parseDate(left)?.getTime() ?? null
  const rightTime = right === null ? null : parseDate(right)?.getTime() ?? null

  return compareNullableNumbers(leftTime, rightTime, direction)
}

export function toggleCombinedGameOverviewSort(
  currentSort: CombinedGameOverviewSortState,
  key: CombinedGameOverviewSortKey,
): CombinedGameOverviewSortState {
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

export function sortCombinedGameOverviewTableRows(
  rows: CombinedGameOverviewTableRow[],
  sortState: CombinedGameOverviewSortState,
): CombinedGameOverviewTableRow[] {
  return [...rows].sort((left, right) => {
    let primaryComparison = 0

    if (sortState.key === 'canonicalName') {
      primaryComparison = compareStrings(
        left.sortValues.canonicalName as string,
        right.sortValues.canonicalName as string,
        sortState.direction,
      )
    } else if (sortState.key === 'canonicalGameId') {
      primaryComparison = compareNullableNumbers(left.canonicalGameId, right.canonicalGameId, sortState.direction)
    } else if (sortState.key === 'latestBucketTime') {
      primaryComparison = compareNullableDateStrings(
        left.sortValues.latestBucketTime as string | null,
        right.sortValues.latestBucketTime as string | null,
        sortState.direction,
      )
    } else {
      primaryComparison = compareBooleans(
        left.sortValues[sortState.key] as boolean,
        right.sortValues[sortState.key] as boolean,
        sortState.direction,
      )
    }

    if (primaryComparison !== 0) {
      return primaryComparison
    }

    return left.canonicalGameId - right.canonicalGameId
  })
}

export function buildCombinedGameOverviewTableRows(
  rows: CombinedGameOverview[],
  searchQuery: string,
  sortState: CombinedGameOverviewSortState,
): CombinedGameOverviewTableRow[] {
  const normalizedSearch = searchQuery.trim().toLowerCase()

  return sortCombinedGameOverviewTableRows(
    rows.map(buildCombinedGameOverviewTableRow).filter((row) => {
      if (normalizedSearch.length === 0) {
        return true
      }

      return (
        row.canonicalName.toLowerCase().includes(normalizedSearch) ||
        String(row.canonicalGameId).includes(normalizedSearch) ||
        row.steamAppidLabel.includes(normalizedSearch) ||
        row.chzzkCategoryIdLabel.toLowerCase().includes(normalizedSearch) ||
        row.categoryNameLabel.toLowerCase().includes(normalizedSearch)
      )
    }),
    sortState,
  )
}

export const getCombinedQueryErrorMessage = (error: unknown) => {
  if (error instanceof Error) {
    return error.message
  }

  return '지금은 Combined identity/source availability view를 불러올 수 없습니다.'
}
