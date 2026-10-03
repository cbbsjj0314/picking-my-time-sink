import { useState } from 'react'
import { COMBINED_ACTIVITY_LIMIT, type CombinedGameActivity } from '../api/combinedActivity'
import { buildCombinedActivityPoints } from '../lib/combinedGameActivityViewModel'

interface Props {
  rows: CombinedGameActivity[]
  loading: boolean
  error: string | null
  searchQuery: string
}

export function CombinedGameActivityScatter({ rows, loading, error, searchQuery }: Props) {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const points = buildCombinedActivityPoints(rows, searchQuery)
  const selected = points.find((point) => point.id === selectedId)
  const maxX = Math.max(1, ...points.map((point) => point.x))
  const maxY = Math.max(1, ...points.map((point) => point.y))
  const anchor = rows[0]?.ccu_period_anchor_date
  const format = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 2 })

  return (
    <section className="surface-low panel-worn ghost-outline rounded-[24px] px-4 py-4 lg:col-span-2 sm:px-5 sm:py-5" aria-label="Combined 7-day activity">
      <h2 className="type-display text-[1.65rem] font-bold text-[var(--text-primary)]">Steam × Chzzk activity</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
        One point per active Steam game with a trusted Chzzk mapping. Linear axes: Steam average CCU (7d)
        and Chzzk observed viewer-hours (7d).
      </p>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
        Bounded sample (bounded_sample): Chzzk shows persisted observed evidence, not complete Chzzk population activity.
        Missing observations are omitted; actual observed zero can appear at zero.
      </p>
      {error ? <p role="alert" className="mt-4">Combined activity could not be loaded. {error}</p>
        : loading ? <p role="status" className="mt-4">Loading Combined activity.</p>
          : <>
            <p className="mt-2 text-sm text-[var(--text-muted)]">
              {anchor ? `Shared window: 7 KST dates ending ${anchor} (inclusive).` : 'Shared Steam window unavailable.'}
              {' '}{points.length} plotted of {rows.length} loaded games after search and availability filtering.
              {rows.length === COMBINED_ACTIVITY_LIMIT ? ` Showing the first ${COMBINED_ACTIVITY_LIMIT} canonical IDs; more games may exist.` : ''}
            </p>
            {points.length === 0 ? <p role="status" className="mt-4">No plottable activity for the current search and shared window.</p>
              : <>
                <div className="mt-4 overflow-x-auto">
                  <svg viewBox="0 0 800 420" className="w-full min-w-[560px]" role="group" aria-label="Steam average CCU versus Chzzk observed viewer-hours, linear scatter">
                    <path d="M 100 30 V 340 H 760" fill="none" stroke="currentColor" />
                    {[0, 0.5, 1].map((fraction) => <g key={fraction} className="text-xs" fill="currentColor">
                      <text x={100 + fraction * 660} y={363} textAnchor="middle">{format(maxX * fraction)}</text>
                      <text x={90} y={344 - fraction * 310} textAnchor="end">{format(maxY * fraction)}</text>
                    </g>)}
                    <text x="430" y="400" textAnchor="middle" fill="currentColor">Steam average CCU (7d)</text>
                    <text transform="translate(22 190) rotate(-90)" textAnchor="middle" fill="currentColor">Chzzk observed viewer-hours (7d)</text>
                    {points.map((point) => <circle
                      key={point.id}
                      cx={100 + point.x / maxX * 660}
                      cy={340 - point.y / maxY * 310}
                      r={selectedId === point.id ? 7 : 5}
                      fill="var(--amber)"
                      stroke="currentColor"
                      tabIndex={0}
                      role="img"
                      aria-label={point.label}
                      onFocus={() => setSelectedId(point.id)}
                      onMouseEnter={() => setSelectedId(point.id)}
                      onClick={() => setSelectedId(point.id)}
                    ><title>{point.label}</title></circle>)}
                  </svg>
                </div>
                <p aria-live="polite" className="mt-2 text-sm text-[var(--text-secondary)]">
                  {selected?.label ?? 'Focus, hover, or tap a point to identify its game and values.'}
                </p>
              </>}
          </>}
    </section>
  )
}
