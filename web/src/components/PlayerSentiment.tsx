import type { SentimentPanel } from '../types'

export function PlayerSentiment({ sentiment }: { sentiment: SentimentPanel }) {
  return (
    <div className="surface-low panel-worn rounded-[28px] p-4 sm:p-5">
      <h3 className="type-display text-[1.25rem] font-bold text-[var(--text-primary)]">Review Synthesis</h3>

      <div className="mt-5">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">Keywords</p>
        <div className="flex flex-wrap gap-2">
          {sentiment.keywords.map((keyword) => (
            <span
              key={keyword}
              className="rounded-full bg-[rgba(96,74,55,0.08)] px-3 py-2 text-sm text-[var(--text-secondary)]"
            >
              {keyword}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-2">
        <div className="surface-etched panel-worn rounded-[22px] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--green)]">Why players like it</p>
          <ul className="mt-3 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">
            {sentiment.likes.map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[var(--green)]" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="surface-etched panel-worn rounded-[22px] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--amber)]">Why players dislike it</p>
          <ul className="mt-3 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">
            {sentiment.dislikes.map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[var(--amber)]" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
