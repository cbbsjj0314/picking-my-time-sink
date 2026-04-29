import { startTransition, useDeferredValue, useEffect, useState } from 'react'
import { ChzzkCategoryTable } from './components/ChzzkCategoryTable'
import { PendingSourcePanel } from './components/PendingSourcePanel'
import { SourceTabsRow } from './components/SourceTabsRow'
import { SteamDiscoverModeRow } from './components/SteamDiscoverModeRow'
import { SteamDetailPanel } from './components/SteamDetailPanel'
import { SteamExploreTable } from './components/SteamExploreTable'
import { SteamRankingList } from './components/SteamRankingList'
import { StickyShell } from './components/StickyShell'
import { useChzzkCategoryOverview } from './hooks/useChzzkCategoryOverview'
import { useSteamExploreOverview } from './hooks/useSteamExploreOverview'
import { useSteamOverview } from './hooks/useSteamOverview'
import type { RangeOption, SourceTab, SteamChartRange, SteamDiscoverMode } from './types'

const DEFAULT_SOURCE_TAB: SourceTab = 'Steam'
const DEFAULT_STEAM_DISCOVER_MODE: SteamDiscoverMode = 'Explore'
const TOP_SELLING_RANGE: RangeOption = 'Last 7 Days'
const DEFAULT_STEAM_CHART_RANGE: SteamChartRange = '7D'
const TOP_SELLING_RANGE_CONTROL_OPTIONS = [{ value: TOP_SELLING_RANGE, label: 'Weekly' }] as const satisfies ReadonlyArray<{
  value: RangeOption
  label: string
}>
const TOP_SELLING_RANGE_STATUS_TEXT =
  'Top Selling은 Steam weekly top sellers snapshot 기준이라 현재 Weekly view로 고정된다.'

const getInitialSourceTab = (): SourceTab => {
  return DEFAULT_SOURCE_TAB
}

function App() {
  const [sourceTab, setSourceTab] = useState<SourceTab>(getInitialSourceTab())
  const [steamDiscoverMode, setSteamDiscoverMode] = useState<SteamDiscoverMode>(DEFAULT_STEAM_DISCOVER_MODE)
  const [steamChartRange, setSteamChartRange] = useState<SteamChartRange>(DEFAULT_STEAM_CHART_RANGE)
  const [showExpandedRanking, setShowExpandedRanking] = useState(false)
  const [searchDraft, setSearchDraft] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const deferredSearch = useDeferredValue(searchQuery)
  const {
    games: steamGames,
    selectedGame: selectedSteamGame,
    totalGameCount: steamTotalGameCount,
    loading,
    error,
  } = useSteamOverview({
    mode: steamDiscoverMode,
    rankingCardLimit: showExpandedRanking ? null : 4,
    searchQuery: deferredSearch,
    selectedId,
  })
  const {
    rows: steamExploreRows,
    totalRowCount: steamExploreTotalRowCount,
    loading: steamExploreLoading,
    error: steamExploreError,
    sortState: steamExploreSortState,
    requestSort: requestSteamExploreSort,
  } = useSteamExploreOverview({
    enabled: steamDiscoverMode === 'Explore' && sourceTab === 'Steam',
    searchQuery: deferredSearch,
  })
  const {
    rows: chzzkCategoryRows,
    totalRowCount: chzzkCategoryTotalRowCount,
    loading: chzzkCategoryLoading,
    error: chzzkCategoryError,
    sortState: chzzkCategorySortState,
    requestSort: requestChzzkCategorySort,
  } = useChzzkCategoryOverview({
    enabled: sourceTab === 'Chzzk',
    searchQuery: deferredSearch,
  })
  const activeGames = steamGames

  useEffect(() => {
    const firstVisibleId = activeGames[0]?.id ?? null

    if (!firstVisibleId) {
      if (selectedId !== null) {
        setSelectedId(null)
      }

      return
    }

    const selectedStillVisible = selectedId !== null && activeGames.some((game) => game.id === selectedId)

    if (!selectedStillVisible && selectedId !== firstVisibleId) {
      setSelectedId(firstVisibleId)
    }
  }, [activeGames, selectedId])

  const resetToDefaultView = () => {
    startTransition(() => {
      setSourceTab(DEFAULT_SOURCE_TAB)
      setSteamDiscoverMode(DEFAULT_STEAM_DISCOVER_MODE)
      setSteamChartRange(DEFAULT_STEAM_CHART_RANGE)
      setShowExpandedRanking(false)
      setSearchDraft('')
      setSearchQuery('')
      setSelectedId(null)
    })
  }

  return (
    <div className="min-h-screen bg-transparent pb-10">
      <StickyShell
        onReset={resetToDefaultView}
        onSearchChange={setSearchDraft}
        onSearchSubmit={() => {
          startTransition(() => {
            setSelectedId(null)
            setSearchQuery(searchDraft)
          })
        }}
        searchApplied={searchQuery.length > 0}
        searchDirty={searchDraft !== searchQuery}
        searchPending={searchQuery !== deferredSearch}
        searchValue={searchDraft}
      />

      <SourceTabsRow
        onChange={(tab) => {
          startTransition(() => {
            setSelectedId(null)
            setSourceTab(tab)
            setShowExpandedRanking(false)
          })
        }}
        sourceTab={sourceTab}
      />

      {sourceTab === 'Steam' ? (
        <SteamDiscoverModeRow
          mode={steamDiscoverMode}
          onChange={(mode) => {
            startTransition(() => {
              setSelectedId(null)
              setSteamDiscoverMode(mode)
              setShowExpandedRanking(false)
            })
          }}
        />
      ) : null}

      <main className="mx-auto mt-4 grid max-w-[1520px] grid-cols-1 gap-5 px-4 sm:mt-5 sm:gap-6 sm:px-6 lg:mt-6 lg:grid-cols-[minmax(320px,380px)_minmax(0,1fr)] lg:px-8 xl:grid-cols-[380px_minmax(0,1fr)]">
        {sourceTab === 'Steam' ? (
          steamDiscoverMode === 'Explore' ? (
            <SteamExploreTable
              error={steamExploreError}
              loading={steamExploreLoading}
              onSortChange={requestSteamExploreSort}
              rows={steamExploreRows}
              searchQuery={deferredSearch}
              sortState={steamExploreSortState}
              totalRowCount={steamExploreTotalRowCount}
            />
          ) : (
            <>
              <SteamRankingList
                error={error}
                games={steamGames}
                loading={loading}
                isExpanded={showExpandedRanking}
                canExpand={steamTotalGameCount > steamGames.length}
                onRangeChange={() => undefined}
                onSelect={setSelectedId}
                onToggleExpanded={() => {
                  startTransition(() => {
                    setShowExpandedRanking((current) => !current)
                  })
                }}
                range={TOP_SELLING_RANGE}
                rangeControlOptions={TOP_SELLING_RANGE_CONTROL_OPTIONS}
                rangeStatusText={TOP_SELLING_RANGE_STATUS_TEXT}
                selectedId={selectedSteamGame?.id ?? null}
              />

              <SteamDetailPanel
                chartRange={steamChartRange}
                error={error}
                game={selectedSteamGame}
                loading={loading}
                mode={steamDiscoverMode}
                onRangeChange={setSteamChartRange}
              />
            </>
          )
        ) : sourceTab === 'Chzzk' ? (
          <ChzzkCategoryTable
            error={chzzkCategoryError}
            loading={chzzkCategoryLoading}
            onSortChange={requestChzzkCategorySort}
            rows={chzzkCategoryRows}
            searchQuery={deferredSearch}
            sortState={chzzkCategorySortState}
            totalRowCount={chzzkCategoryTotalRowCount}
          />
        ) : (
          <PendingSourcePanel sourceTab={sourceTab} />
        )}
      </main>
    </div>
  )
}

export default App
