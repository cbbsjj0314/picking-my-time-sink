import type { RangeOption, SteamReferenceGame } from '../types'

interface SteamRankingListProps {
  games: SteamReferenceGame[]
  range: RangeOption
  selectedId: string | null
  disabledRanges?: RangeOption[]
  isExpanded?: boolean
  canExpand?: boolean
  onRangeChange: (range: RangeOption) => void
  onSelect: (id: string) => void
  onToggleExpanded: () => void
  loading?: boolean
  error?: string | null
  rangeStatusText?: string
}

function SteamRankingCard({
  game,
  selected,
  onSelect,
}: {
  key?: string
  game: SteamReferenceGame
  selected: boolean
  onSelect: (id: string) => void
}) {
  const cardClassName = selected
    ? 'bg-[linear-gradient(180deg,#E8639B_0%,#D34C88_100%)] shadow-[inset_0_0_0_1px_rgba(255,242,248,0.28),inset_0_0_0_5px_rgba(22,12,18,0.7),0_18px_44px_rgba(122,28,71,0.22)]'
    : 'panel-worn hover:bg-[linear-gradient(180deg,rgba(44,36,29,0.98),rgba(30,24,20,0.98))]'

  const headingTone = selected ? 'text-[rgba(73,16,43,0.74)]' : 'text-[rgba(244,232,214,0.54)]'
  const titleTone = selected ? 'text-[#2f081b]' : 'text-[var(--paper)]'
  const labelTone = selected ? 'text-[rgba(73,16,43,0.68)]' : 'text-[rgba(244,232,214,0.5)]'
  const valueTone = selected ? 'text-[#3a0c20]' : 'text-[var(--paper)]'
  const badgeClassName = selected
    ? 'bg-[rgba(255,242,248,0.22)] text-[#3a0c20] shadow-[inset_0_0_0_1px_rgba(255,242,248,0.3)]'
    : 'bg-[rgba(255,244,226,0.06)] text-[rgba(244,232,214,0.68)]'

  return (
    <button
      className={`surface-high group w-full rounded-[20px] px-4 py-3.5 text-left transition duration-200 sm:px-[18px] sm:py-4 ${cardClassName}`}
      onClick={() => onSelect(game.id)}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <p className={`type-display text-sm font-bold tracking-[0.08em] ${headingTone}`}>#{game.rank}</p>
        {game.statusBadge ? (
          <span
            className={`inline-flex shrink-0 whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${badgeClassName}`}
          >
            {game.statusBadge}
          </span>
        ) : null}
      </div>

      <div className="mt-2.5 min-w-0">
        <h3 className={`type-display text-[1.14rem] font-bold leading-tight ${titleTone}`}>{game.title}</h3>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-x-4 gap-y-2.5 text-sm lg:grid-cols-2">
        <div>
          <p className={labelTone}>Live CCU</p>
          <p className={`metric-text mt-1 font-semibold ${valueTone}`}>{game.liveCcu}</p>
        </div>
        <div className="lg:flex lg:justify-end">
          <div className="lg:flex lg:flex-col lg:items-start">
            <p className={labelTone}>Price</p>
            <p className={`metric-text mt-1 font-semibold ${valueTone}`}>{game.priceLine}</p>
          </div>
        </div>
        <div className="lg:col-span-2">
          <p className={labelTone}>Reviews</p>
          <p className={`mt-1 font-semibold ${valueTone}`}>{game.reviewSummary}</p>
        </div>
      </div>
    </button>
  )
}

export function SteamRankingList({
  games,
  range,
  selectedId,
  disabledRanges = [],
  isExpanded = false,
  canExpand = false,
  onRangeChange,
  onSelect,
  onToggleExpanded,
  loading = false,
  error = null,
  rangeStatusText,
}: SteamRankingListProps) {
  const rangeControlOptions: Array<{ value: RangeOption; label: string }> = [
    { value: '1D', label: '1D' },
    { value: 'Last 7 Days', label: 'Last 7 Days' },
    { value: 'Last 30 Days', label: 'Last 30 Days' },
    { value: 'Last 3 Months', label: 'Last 3 Months' },
  ]

  return (
    <section className="surface-low panel-worn ghost-outline self-start rounded-[24px] px-4 py-3.5 sm:px-5 sm:py-4">
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <div>
          <h2 className="type-display text-[1.55rem] font-bold text-[var(--text-primary)]">Top Ranked</h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {rangeStatusText ?? 'Ranking window changes list context only.'}
          </p>
        </div>

        <label className="surface-high panel-worn ghost-outline flex w-full items-center gap-3 rounded-[18px] px-4 py-2.5 text-sm text-[var(--paper-dim)] shadow-[inset_0_1px_0_rgba(255,249,239,0.04),0_12px_24px_rgba(0,0,0,0.16)] sm:w-auto">
          <select
            className="type-display w-full bg-transparent font-semibold tracking-[0.02em] text-[var(--paper)] outline-none sm:w-auto"
            onChange={(event: { target: HTMLSelectElement }) => onRangeChange(event.target.value as RangeOption)}
            value={range}
          >
            {rangeControlOptions.map((option) => (
              <option
                key={option.value}
                className="bg-[#1f1915] text-[#f8efe1]"
                disabled={disabledRanges.includes(option.value)}
                value={option.value}
              >
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 space-y-2.5">
        {error ? (
          <div className="surface-etched panel-worn rounded-[24px] px-5 py-7 text-sm leading-6 text-[var(--text-secondary)]">
            {error}
          </div>
        ) : loading && games.length === 0 ? (
          <div className="surface-etched panel-worn rounded-[24px] px-5 py-7 text-sm text-[var(--text-secondary)]">
            실데이터 Steam 목록을 불러오는 중입니다.
          </div>
        ) : games.length > 0 ? (
          games.map((game) => (
            <SteamRankingCard key={game.id} game={game} onSelect={onSelect} selected={game.id === selectedId} />
          ))
        ) : (
          <div className="surface-etched panel-worn rounded-[24px] px-5 py-7 text-sm text-[var(--text-secondary)]">
            현재 검색 조건과 일치하는 Steam 게임이 없습니다.
          </div>
        )}
      </div>

      <div className="mt-3.5 px-1">
        {canExpand || isExpanded ? (
          <>
            <button
              className="text-sm text-[var(--text-secondary)] transition hover:text-[var(--text-primary)]"
              onClick={onToggleExpanded}
              type="button"
            >
              {isExpanded ? '\u2190 Back to overview list' : '\u2192 View full ranking'}
            </button>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {isExpanded ? '현재 latest ranking rows 전체를 이 화면에서 펼쳐서 보고 있습니다.' : '현재 선택한 Steam lens의 latest ranking rows 전체를 펼쳐 볼 수 있습니다.'}
            </p>
          </>
        ) : null}
      </div>
    </section>
  )
}
