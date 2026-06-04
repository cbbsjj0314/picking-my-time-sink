import { useEffect, useState } from 'react'
import { combinedApi, type CombinedGameOverview } from '../api/combined'
import {
  buildCombinedGameOverviewTableRows,
  DEFAULT_COMBINED_GAME_OVERVIEW_SORT_STATE,
  getCombinedQueryErrorMessage,
  toggleCombinedGameOverviewSort,
  type CombinedGameOverviewSortKey,
  type CombinedGameOverviewSortState,
  type CombinedGameOverviewTableRow,
} from '../lib/combinedGameOverviewViewModel'

interface UseCombinedGameOverviewArgs {
  enabled: boolean
  searchQuery: string
  limit?: number
}

interface UseCombinedGameOverviewResult {
  rows: CombinedGameOverviewTableRow[]
  totalRowCount: number
  loading: boolean
  error: string | null
  sortState: CombinedGameOverviewSortState
  requestSort: (key: CombinedGameOverviewSortKey) => void
}

export function useCombinedGameOverview({
  enabled,
  searchQuery,
  limit = 50,
}: UseCombinedGameOverviewArgs): UseCombinedGameOverviewResult {
  const [apiRows, setApiRows] = useState<CombinedGameOverview[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const [sortState, setSortState] = useState<CombinedGameOverviewSortState>(
    DEFAULT_COMBINED_GAME_OVERVIEW_SORT_STATE,
  )

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()

    async function loadCombinedGameOverview() {
      setLoading(true)
      setError(null)

      try {
        const rows = await combinedApi.listGameOverview({ limit, signal: controller.signal })

        if (controller.signal.aborted) {
          return
        }

        setApiRows(rows)
      } catch (nextError) {
        if (controller.signal.aborted) {
          return
        }

        setApiRows([])
        setError(getCombinedQueryErrorMessage(nextError))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadCombinedGameOverview()

    return () => {
      controller.abort()
    }
  }, [enabled, limit])

  return {
    rows: enabled ? buildCombinedGameOverviewTableRows(apiRows, searchQuery, sortState) : [],
    totalRowCount: enabled ? apiRows.length : 0,
    loading,
    error,
    sortState,
    requestSort: (key) => {
      setSortState((currentSort) => toggleCombinedGameOverviewSort(currentSort, key))
    },
  }
}
