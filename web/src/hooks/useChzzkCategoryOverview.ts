import { useEffect, useState } from 'react'
import { chzzkApi, type ChzzkCategoryOverview } from '../api/chzzk'
import {
  buildChzzkCategoryTableRows,
  DEFAULT_CHZZK_CATEGORY_SORT_STATE,
  getChzzkQueryErrorMessage,
  toggleChzzkCategorySort,
  type ChzzkCategorySortKey,
  type ChzzkCategorySortState,
  type ChzzkCategoryTableRow,
} from '../lib/chzzkCategoryViewModel'

interface UseChzzkCategoryOverviewArgs {
  enabled: boolean
  searchQuery: string
  limit?: number
}

interface UseChzzkCategoryOverviewResult {
  rows: ChzzkCategoryTableRow[]
  totalRowCount: number
  loading: boolean
  error: string | null
  sortState: ChzzkCategorySortState
  requestSort: (key: ChzzkCategorySortKey) => void
}

export function useChzzkCategoryOverview({
  enabled,
  searchQuery,
  limit = 50,
}: UseChzzkCategoryOverviewArgs): UseChzzkCategoryOverviewResult {
  const [apiRows, setApiRows] = useState<ChzzkCategoryOverview[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const [sortState, setSortState] = useState<ChzzkCategorySortState>(DEFAULT_CHZZK_CATEGORY_SORT_STATE)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()

    async function loadChzzkCategoryOverview() {
      setLoading(true)
      setError(null)

      try {
        const rows = await chzzkApi.listCategoryOverview({ limit, signal: controller.signal })

        if (controller.signal.aborted) {
          return
        }

        setApiRows(rows)
      } catch (nextError) {
        if (controller.signal.aborted) {
          return
        }

        setApiRows([])
        setError(getChzzkQueryErrorMessage(nextError))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadChzzkCategoryOverview()

    return () => {
      controller.abort()
    }
  }, [enabled, limit])

  return {
    rows: enabled ? buildChzzkCategoryTableRows(apiRows, searchQuery, sortState) : [],
    totalRowCount: enabled ? apiRows.length : 0,
    loading,
    error,
    sortState,
    requestSort: (key) => {
      setSortState((currentSort) => toggleChzzkCategorySort(currentSort, key))
    },
  }
}
