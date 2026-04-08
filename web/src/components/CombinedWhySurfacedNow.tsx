import type { CombinedWhySurfacedNowPanel } from '../types'

export function CombinedWhySurfacedNow({ panel }: { panel: CombinedWhySurfacedNowPanel }) {
  return (
    <div className="surface-low panel-worn rounded-[28px] p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
        <div>
          <h3 className="type-display text-[1.25rem] font-bold text-[var(--text-primary)]">Combined Why Surfaced Now</h3>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Streaming + Steam currentness</p>
        </div>

        <span className="self-start rounded-full bg-[rgba(96,74,55,0.08)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Combined read
        </span>
      </div>

      <div className="surface-high panel-worn mt-5 rounded-[24px] p-4 sm:p-5 shadow-[inset_0_0_0_1px_rgba(255,248,238,0.03)]">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[rgba(244,232,214,0.62)]">Current read</p>
        <p className="type-display mt-3 max-w-3xl text-[1.1rem] leading-7 text-[var(--paper)] sm:text-[1.25rem]">
          {panel.summary}
        </p>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-2">
        <div className="surface-etched panel-worn rounded-[22px] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--green)]">Streaming now</p>
          <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{panel.streamingNow}</p>
        </div>

        <div className="surface-etched panel-worn rounded-[22px] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--amber)]">Steam now</p>
          <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{panel.steamNow}</p>
        </div>
      </div>
    </div>
  )
}
