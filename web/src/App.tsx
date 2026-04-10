import { startTransition, useDeferredValue, useEffect, useState } from 'react'
import { PendingSourcePanel } from './components/PendingSourcePanel'
import { SourceTabsRow } from './components/SourceTabsRow'
import { SteamDiscoverModeRow } from './components/SteamDiscoverModeRow'
import { SteamDetailPanel } from './components/SteamDetailPanel'
import { SteamRankingList } from './components/SteamRankingList'
import { StickyShell } from './components/StickyShell'
import { useSteamOverview } from './hooks/useSteamOverview'
import { rangeOptions } from './types'
import type { RangeOption, SourceTab, SteamChartRange, SteamDiscoverMode } from './types'

const DEFAULT_SOURCE_TAB: SourceTab = 'Steam'
const DEFAULT_STEAM_DISCOVER_MODE: SteamDiscoverMode = 'Top Selling'
const DEFAULT_RANGE: RangeOption = 'Last 7 Days'
const DEFAULT_STEAM_CHART_RANGE: SteamChartRange = '7D'
const SUPPORTED_RANGES_BY_MODE: Record<SteamDiscoverMode, readonly RangeOption[]> = {
  'Top Selling': ['Last 7 Days'],
  'Most Played': ['1D', 'Last 7 Days', 'Last 30 Days', 'Last 3 Months'],
}
const RANGE_STATUS_TEXT_BY_MODE: Record<SteamDiscoverMode, string> = {
  'Top Selling': 'Top Selling은 Steam weekly topsellers source라 Last 7 Days만 지원한다.',
  'Most Played': '1D는 latest live CCU, 7D/30D/3M는 full-window daily CCU rollup 기준으로 리스트를 바꾼다.',
}

const getInitialSourceTab = (): SourceTab => {
  return DEFAULT_SOURCE_TAB
}

function App() {
  const [sourceTab, setSourceTab] = useState<SourceTab>(getInitialSourceTab())
  const [steamDiscoverMode, setSteamDiscoverMode] = useState<SteamDiscoverMode>(DEFAULT_STEAM_DISCOVER_MODE)
  const [steamRankingWindow, setSteamRankingWindow] = useState<RangeOption>(DEFAULT_RANGE)
  const [steamChartRange, setSteamChartRange] = useState<SteamChartRange>(DEFAULT_STEAM_CHART_RANGE)
  const [searchDraft, setSearchDraft] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const deferredSearch = useDeferredValue(searchQuery)
  const supportedSteamRankingRanges = SUPPORTED_RANGES_BY_MODE[steamDiscoverMode]
  const { games: steamGames, selectedGame: selectedSteamGame, loading, error } = useSteamOverview({
    mode: steamDiscoverMode,
    rankingWindow: steamRankingWindow,
    searchQuery: deferredSearch,
    selectedId,
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

  const handleSteamRankingWindowChange = (nextRange: RangeOption) => {
    startTransition(() => {
      setSteamRankingWindow(nextRange)
    })
  }

  const resetToDefaultView = () => {
    startTransition(() => {
      setSourceTab(DEFAULT_SOURCE_TAB)
      setSteamDiscoverMode(DEFAULT_STEAM_DISCOVER_MODE)
      setSteamRankingWindow(DEFAULT_RANGE)
      setSteamChartRange(DEFAULT_STEAM_CHART_RANGE)
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
          })
        }}
        sourceTab={sourceTab}
      />

      {sourceTab === 'Steam' ? (
        <SteamDiscoverModeRow
          mode={steamDiscoverMode}
          onChange={(mode) => {
            const supportedRanges = SUPPORTED_RANGES_BY_MODE[mode]
            const nextRange = supportedRanges.includes(steamRankingWindow) ? steamRankingWindow : supportedRanges[0]

            startTransition(() => {
              setSelectedId(null)
              setSteamDiscoverMode(mode)
              setSteamRankingWindow(nextRange)
            })
          }}
        />
      ) : null}

      <main className="mx-auto mt-4 grid max-w-[1520px] grid-cols-1 gap-5 px-4 sm:mt-5 sm:gap-6 sm:px-6 lg:mt-6 lg:grid-cols-[minmax(320px,380px)_minmax(0,1fr)] lg:px-8 xl:grid-cols-[380px_minmax(0,1fr)]">
        {sourceTab === 'Steam' ? (
          <>
            <SteamRankingList
              error={error}
              games={steamGames}
              loading={loading}
              disabledRanges={rangeOptions.filter((range) => !supportedSteamRankingRanges.includes(range))}
              onRangeChange={handleSteamRankingWindowChange}
              onSelect={setSelectedId}
              range={steamRankingWindow}
              rangeStatusText={RANGE_STATUS_TEXT_BY_MODE[steamDiscoverMode]}
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
        ) : (
          <PendingSourcePanel sourceTab={sourceTab} />
        )}
      </main>
    </div>
  )
}

export default App
