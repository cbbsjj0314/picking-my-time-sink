import type { ContextGame, DiscoverMode, RangeOption, SourceTab, TimelineRange } from '../types'
import { CombinedWhySurfacedNow } from './CombinedWhySurfacedNow'
import { PlayerSentiment } from './PlayerSentiment'
import { SignalCard } from './SignalCard'
import { TimelineChart } from './TimelineChart'

interface DetailPanelProps {
  game: ContextGame | null
  source: SourceTab
  mode: DiscoverMode
  range: RangeOption
  timelineRange: TimelineRange
  onTimelineRangeChange: (range: TimelineRange) => void
}

export function DetailPanel({
  game,
  source,
  mode,
  range,
  timelineRange,
  onTimelineRangeChange,
}: DetailPanelProps) {
  if (!game) {
    return (
      <section className="surface-low panel-worn ghost-outline flex min-h-[360px] items-center justify-center rounded-[28px] p-6 sm:p-8 lg:min-h-[640px]">
        <div className="max-w-md text-center">
          <p className="type-display text-[1.4rem] font-bold text-[var(--text-primary)]">Selected Game Details</p>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            Search narrowed the candidate list to zero results. Clear the query to inspect a selected game again.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="animate-rise space-y-5">
      <div className="surface-low panel-worn ghost-outline rounded-[28px] p-4 sm:p-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            {source} • {mode} • {range}
          </p>
          <h2 className="type-display paper-ink mt-3 text-[2rem] font-bold leading-none sm:text-[2.3rem] xl:text-[2.5rem]">{game.title}</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {game.verdicts.map((verdict) => (
              <span
                key={verdict}
                className="paper-chip type-display rounded-full px-3 py-2 text-[1rem] font-medium tracking-[0.02em] text-[#63B54F]"
              >
                {verdict}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-4">
          {game.signalCards.map((card) => (
            <SignalCard key={card.label} card={card} />
          ))}
        </div>
      </div>

      <TimelineChart
        onRangeChange={onTimelineRangeChange}
        points={game.timeline[timelineRange]}
        selectedRange={timelineRange}
      />

      {source === 'Combined' ? (
        <CombinedWhySurfacedNow panel={game.whySurfacedNow} />
      ) : (
        <PlayerSentiment sentiment={game.sentiment} />
      )}
    </section>
  )
}
