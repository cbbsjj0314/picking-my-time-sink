import type { SteamExploreTableRow } from '../lib/steamExploreViewModel'

interface SteamExploreTableProps {
  rows: SteamExploreTableRow[]
  totalRowCount: number
  loading?: boolean
  error?: string | null
  searchQuery?: string
}

interface ExploreCellProps {
  value: string
  support?: string | null
  title?: string | null
}

function ExploreCell({ value, support = null, title = null }: ExploreCellProps) {
  return (
    <td className="px-4 py-3 align-top" title={title ?? undefined}>
      <div className="metric-text whitespace-nowrap text-sm font-semibold text-[var(--text-primary)]">{value}</div>
      {support ? <div className="mt-1 whitespace-nowrap text-xs text-[var(--text-muted)]">{support}</div> : null}
    </td>
  )
}

const tableHeadings = [
  'Game',
  'Current CCU',
  'Avg CCU',
  'Peak CCU',
  'Estimated Player-Hours',
  'Reviews Added',
  'Positive Share',
  'Price',
]

export function SteamExploreTable({
  rows,
  totalRowCount,
  loading = false,
  error = null,
  searchQuery = '',
}: SteamExploreTableProps) {
  const firstCcuAnchor = rows.find((row) => row.ccuAnchorLabel !== null)?.ccuAnchorLabel ?? null
  const firstReviewAnchor = rows.find((row) => row.reviewAnchorLabel !== null)?.reviewAnchorLabel ?? null
  const hasSearch = searchQuery.trim().length > 0

  return (
    <section className="surface-low panel-worn ghost-outline rounded-[24px] px-4 py-4 lg:col-span-2 sm:px-5 sm:py-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Steam source
          </p>
          <h2 className="type-display mt-2 text-[1.65rem] font-bold text-[var(--text-primary)]">Explore</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            Active tracked Steam games, sorted by average CCU for the selected period. Missing evidence stays "-".
          </p>
        </div>

        <div className="surface-high panel-worn ghost-outline flex w-full flex-col gap-1 rounded-[18px] px-4 py-3 text-sm text-[var(--paper-dim)] md:w-auto">
          <span className="type-display font-semibold tracking-[0.02em] text-[var(--paper)]">
            Last 7 Days · KR / KST
          </span>
          <span>Avg, peak, player-hours, reviews, and positive share use this fixed period.</span>
        </div>
      </div>

      {firstCcuAnchor || firstReviewAnchor ? (
        <p className="mt-4 text-xs text-[var(--text-muted)]">
          {firstCcuAnchor ? `CCU anchor ${firstCcuAnchor}` : null}
          {firstCcuAnchor && firstReviewAnchor ? ' · ' : null}
          {firstReviewAnchor ? `Reviews anchor ${firstReviewAnchor}` : null}
        </p>
      ) : null}

      <div className="mt-4 overflow-x-auto rounded-[18px] outline outline-1 outline-[var(--ghost-border)]">
        {error ? (
          <div className="surface-etched px-5 py-8 text-sm leading-6 text-[var(--text-secondary)]">{error}</div>
        ) : loading && rows.length === 0 ? (
          <div className="surface-etched px-5 py-8 text-sm text-[var(--text-secondary)]">
            Loading Steam Explore evidence.
          </div>
        ) : rows.length === 0 ? (
          <div className="surface-etched px-5 py-8 text-sm text-[var(--text-secondary)]">
            {hasSearch && totalRowCount > 0
              ? 'No Steam Explore rows match the current search.'
              : 'No Steam Explore rows are available.'}
          </div>
        ) : (
          <table className="min-w-[1120px] w-full border-collapse bg-[rgba(255,249,239,0.34)] text-left">
            <thead>
              <tr className="border-b border-[var(--ghost-border)] text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">
                {tableHeadings.map((heading) => (
                  <th key={heading} className="px-4 py-3 font-semibold">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--ghost-border)]">
              {rows.map((row) => (
                <tr key={row.id} className="transition hover:bg-[rgba(255,249,239,0.42)]">
                  <td className="min-w-[220px] px-4 py-3 align-top">
                    <div className="font-semibold leading-snug text-[var(--text-primary)]">{row.gameTitle}</div>
                  </td>
                  <ExploreCell
                    support={row.currentCcuSupportLabel}
                    title={row.currentCcuTitle}
                    value={row.currentCcuLabel}
                  />
                  <ExploreCell support={row.avgCcuSupportLabel} value={row.avgCcuLabel} />
                  <ExploreCell support={row.peakCcuSupportLabel} value={row.peakCcuLabel} />
                  <ExploreCell
                    support={row.estimatedPlayerHoursSupportLabel}
                    value={row.estimatedPlayerHoursLabel}
                  />
                  <ExploreCell support={row.reviewsAddedSupportLabel} value={row.reviewsAddedLabel} />
                  <ExploreCell support={row.positiveShareSupportLabel} value={row.positiveShareLabel} />
                  <ExploreCell support={row.priceSupportLabel} title={row.priceTitle} value={row.priceLabel} />
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
