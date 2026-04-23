import { useEffect, useState } from 'react'
import { gamesApi, type GameExploreOverview } from '../api/games'
import { getSteamQueryErrorMessage } from '../lib/steamViewModel'
import {
  buildSteamExploreTableRows,
  DEFAULT_STEAM_EXPLORE_SORT_STATE,
  toggleSteamExploreSort,
  type SteamExploreSortKey,
  type SteamExploreSortState,
  type SteamExploreTableRow,
} from '../lib/steamExploreViewModel'

interface UseSteamExploreOverviewArgs {
  enabled: boolean
  searchQuery: string
  limit?: number
}

interface UseSteamExploreOverviewResult {
  rows: SteamExploreTableRow[]
  totalRowCount: number
  loading: boolean
  error: string | null
  sortState: SteamExploreSortState
  requestSort: (key: SteamExploreSortKey) => void
}

export function useSteamExploreOverview({
  enabled,
  searchQuery,
  limit = 50,
}: UseSteamExploreOverviewArgs): UseSteamExploreOverviewResult {
  const [apiRows, setApiRows] = useState<GameExploreOverview[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const [sortState, setSortState] = useState<SteamExploreSortState>(DEFAULT_STEAM_EXPLORE_SORT_STATE)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()

    async function loadExploreOverview() {
      setLoading(true)
      setError(null)

      try {
        const rows = await gamesApi.listExploreOverview({ limit, signal: controller.signal })

        if (controller.signal.aborted) {
          return
        }

        setApiRows(rows)
      } catch (nextError) {
        if (controller.signal.aborted) {
          return
        }

        setApiRows([])
        setError(getSteamQueryErrorMessage(nextError))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadExploreOverview()

    return () => {
      controller.abort()
    }
  }, [enabled, limit])

  return {
    rows: enabled ? buildSteamExploreTableRows(apiRows, searchQuery, sortState) : [],
    totalRowCount: enabled ? apiRows.length : 0,
    loading,
    error,
    sortState,
    requestSort: (key) => {
      setSortState((currentSort) => toggleSteamExploreSort(currentSort, key))
    },
  }
}
