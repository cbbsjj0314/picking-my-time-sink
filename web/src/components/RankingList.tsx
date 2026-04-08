import type { ContextGame, RangeOption } from '../types'

interface RankingListProps {
  games: ContextGame[]
  range: RangeOption
  selectedId: string | null
  onRangeChange: (range: RangeOption) => void
  onSelect: (id: string) => void
}

function RankingCard({
  game,
  selected,
  onSelect,
}: {
  key?: string
  game: ContextGame
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
        <span
          className={`inline-flex shrink-0 whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${badgeClassName}`}
        >
          {game.signalBadge}
        </span>
      </div>

      <div className="mt-2.5 min-w-0">
        <h3 className={`type-display text-[1.14rem] font-bold leading-tight ${titleTone}`}>{game.title}</h3>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2.5 text-sm">
        <div>
          <p className={labelTone}>Reviews</p>
          <p className={`metric-text mt-1 font-semibold ${valueTone}`}>{game.reviewsDelta}</p>
        </div>
        <div>
          <p className={labelTone}>Price</p>
          <p className={`metric-text mt-1 font-semibold ${valueTone}`}>{game.price}</p>
        </div>
        <div>
          <p className={labelTone}>CCU</p>
          <p className={`metric-text mt-1 font-semibold ${valueTone}`}>{game.ccuDelta}</p>
        </div>
        <div>
          <p className={labelTone}>Viewer</p>
          <p className={`metric-text mt-1 font-semibold ${valueTone}`}>{game.viewerDelta}</p>
        </div>
      </div>
    </button>
  )
}

export function RankingList({ games, range, selectedId, onRangeChange, onSelect }: RankingListProps) {
  const rangeControlOptions: Array<{ value: RangeOption; label: string }> = [
    { value: '1D', label: 'Last 1 Days' },
    { value: 'Last 7 Days', label: 'Last 7 Days' },
    { value: 'Last 30 Days', label: 'Last 30 Days' },
    { value: 'Last 3 Months', label: 'Last 3 Months' },
  ]

  return (
    <section className="surface-low panel-worn ghost-outline self-start rounded-[24px] px-4 py-3.5 sm:px-5 sm:py-4">
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <h2 className="type-display text-[1.55rem] font-bold text-[var(--text-primary)]">Top Ranked</h2>

        <label className="surface-high panel-worn ghost-outline flex w-full items-center gap-3 rounded-[18px] px-4 py-2.5 text-sm text-[var(--paper-dim)] shadow-[inset_0_1px_0_rgba(255,249,239,0.04),0_12px_24px_rgba(0,0,0,0.16)] sm:w-auto">
          <select
            className="type-display w-full bg-transparent text-[rem] font-semibold tracking-[0.02em] text-[var(--paper)] outline-none sm:w-auto"
            onChange={(event: { target: HTMLSelectElement }) => onRangeChange(event.target.value as RangeOption)}
            value={range}
          >
            {rangeControlOptions.map((option) => (
              <option key={option.value} className="bg-[#1f1915] text-[#f8efe1]" value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 space-y-2.5">
        {games.length > 0 ? (
          games.map((game) => (
            <RankingCard key={game.id} game={game} onSelect={onSelect} selected={game.id === selectedId} />
          ))
        ) : (
          <div className="surface-etched panel-worn rounded-[24px] px-5 py-7 text-sm text-[var(--text-secondary)]">
            No titles match the current search.
          </div>
        )}
      </div>

      <button
        className="mt-3.5 flex items-center gap-2 rounded-full px-1 text-sm font-medium text-[var(--wine)] transition hover:text-[var(--text-primary)]"
        type="button"
      >
        View full ranking <span aria-hidden="true">→</span>
      </button>
    </section>
  )
}
