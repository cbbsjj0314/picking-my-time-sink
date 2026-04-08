import cardCaveatIcon from '../assets/ui/icons/steam-data-caveat-card-icon.svg'
import type { SteamChartRange, SteamDataStateTarget, SteamDetailCard, SteamDiscoverMode, SteamReferenceGame } from '../types'
import { SteamCcuChart } from './SteamCcuChart'

interface SteamDetailPanelProps {
  chartRange: SteamChartRange
  game: SteamReferenceGame | null
  mode: SteamDiscoverMode
  onRangeChange: (range: SteamChartRange) => void
  loading?: boolean
  error?: string | null
}

const chipToneMap: Record<string, string> = {
  'Players healthy': 'text-[#63B54F]',
  'Reviews positive': 'text-[#63B54F]',
  'Price live': 'text-[#63B54F]',
  Deferred: 'text-[var(--paper)]',
}

function SteamSupportingCard({
  card,
  cardStates,
}: {
  key?: string
  card: SteamDetailCard
  cardStates: SteamReferenceGame['cardStates']
}) {
  const cardTarget = card.label as SteamDataStateTarget
  const cardDataState = cardStates?.[cardTarget] ?? null

  return (
    <div className="surface-high panel-worn rounded-[24px] p-4 shadow-[inset_0_0_0_1px_rgba(255,248,238,0.03)]">
      <div className="flex items-center gap-2">
        <h3 className="type-display text-[1rem] font-bold text-[var(--paper)]">{card.label}</h3>
        {cardDataState ? (
          <span
            aria-label={`${cardDataState.kind} data caveat`}
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden"
            title={cardDataState.tooltip}
          >
            <img alt="" className="h-full w-full object-contain opacity-95" src={cardCaveatIcon} />
          </span>
        ) : null}
      </div>

      {card.subtitle ? (
        <p className="mt-0.1 text-sm font-semibold text-[rgba(244,232,214,0.86)]">{card.subtitle}</p>
      ) : null}

      <div className="mt-4 space-y-3">
        {card.rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4">
            <span className="min-w-0 text-sm text-[rgba(244,232,214,0.62)]">{row.label}</span>
            <span className="metric-text shrink-0 text-right text-sm font-semibold text-[var(--paper)]">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SteamDetailPanel({
  chartRange,
  game,
  mode,
  onRangeChange,
  loading = false,
  error = null,
}: SteamDetailPanelProps) {
  if (!game) {
    return (
      <section className="surface-low panel-worn ghost-outline flex min-h-[360px] items-center justify-center rounded-[28px] p-6 sm:p-8 lg:min-h-[640px]">
        <div className="max-w-md text-center">
          <p className="text-sm leading-6 text-[var(--text-secondary)]">
            {error
              ? error
              : loading
                ? '실데이터 Steam 지표를 불러오는 중입니다.'
                : '검색 결과가 없어 선택된 게임을 표시할 수 없습니다. 검색어를 지우고 다시 확인해 주세요.'}
          </p>
        </div>
      </section>
    )
  }
  return (
    <section className="animate-rise space-y-5">
      <div className="surface-low panel-worn ghost-outline rounded-[28px] p-4 sm:p-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">Steam • {mode}</p>
          <h2 className="type-display paper-ink mt-3 text-[2rem] font-bold leading-none sm:text-[2.3rem] xl:text-[2.5rem]">
            {game.title}
          </h2>

          <div className="mt-4 flex flex-wrap gap-2">
            {game.verdictChips.map((chip) => (
              <span
                key={chip}
                className={`paper-chip type-display rounded-full px-3 py-2 text-[1rem] font-medium tracking-[0.02em] ${chipToneMap[chip] ?? 'text-[var(--paper)]'}`}
              >
                {chip}
              </span>
            ))}
          </div>

          <p className="mt-4 text-sm leading-6 text-[var(--text-secondary)]">{game.surfaceContext}</p>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3 xl:max-w-[750px]">
          {game.detailCards.map((card) => (
            <SteamSupportingCard key={card.label} card={card} cardStates={game.cardStates} />
          ))}
        </div>
      </div>

      <SteamCcuChart
        onRangeChange={onRangeChange}
        points={game.timeline[chartRange]}
        selectedRange={chartRange}
        state={game.chartState}
      />
    </section>
  )
}
