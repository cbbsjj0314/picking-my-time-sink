import type { SignalCardData } from '../types'

const accentMap = {
  streaming: 'bg-[rgba(195,245,255,0.12)] text-[var(--paper)]',
  positive: 'bg-[rgba(72,221,188,0.14)] text-[var(--green)]',
  warning: 'bg-[rgba(255,185,80,0.16)] text-[var(--amber)]',
  neutral: 'bg-[rgba(232,220,200,0.11)] text-[var(--paper)]',
} satisfies Record<SignalCardData['accent'], string>

export function SignalCard({ card }: { key?: string; card: SignalCardData }) {
  return (
    <div className="surface-high panel-worn rounded-[24px] p-4 shadow-[inset_0_0_0_1px_rgba(255,248,238,0.03)]">
      <div className="flex items-start justify-between gap-3">
        <h3 className="type-display text-[1rem] font-bold text-[var(--paper)]">{card.label}</h3>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${accentMap[card.accent]}`}>{card.rows[1]?.value}</span>
      </div>

      <div className="mt-4 space-y-3">
        {card.rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4">
            <span className="min-w-0 text-sm text-[rgba(244,232,214,0.62)]">{row.label}</span>
            <span className="metric-text shrink-0 text-sm font-semibold text-[var(--paper)]">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
