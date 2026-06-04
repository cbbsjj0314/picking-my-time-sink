import type {
  CombinedGameOverviewSortKey,
  CombinedGameOverviewSortState,
  CombinedGameOverviewTableRow,
} from '../lib/combinedGameOverviewViewModel'

interface CombinedGameOverviewTableProps {
  rows: CombinedGameOverviewTableRow[]
  totalRowCount: number
  loading?: boolean
  error?: string | null
  searchQuery?: string
  sortState: CombinedGameOverviewSortState
  onSortChange: (key: CombinedGameOverviewSortKey) => void
}

interface CombinedCellProps {
  value: string
  support?: string | null
  title?: string | null
}

function CaveatBadge({ label, title }: { label: string; title?: string | null }) {
  const accessibleLabel = title ? `${label}: ${title}` : label

  return (
    <span
      aria-label={accessibleLabel}
      className="inline-flex h-5 shrink-0 items-center rounded border border-[var(--ghost-border-strong)] bg-[rgba(255,244,226,0.78)] px-1.5 text-[0.64rem] font-bold uppercase leading-none text-[var(--amber)]"
      title={title ?? undefined}
    >
      {label}
    </span>
  )
}

function CombinedCell({ value, support = null, title = null }: CombinedCellProps) {
  return (
    <td className="px-4 py-3 align-top" title={title ?? undefined}>
      <div className="metric-text min-h-5 whitespace-nowrap text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
      {support ? <div className="mt-1 max-w-[14rem] text-xs leading-snug text-[var(--text-muted)]">{support}</div> : null}
    </td>
  )
}

const tableColumns = [
  { key: 'canonicalName', label: 'Canonical Game' },
  { key: 'canonicalGameId', label: 'Canonical ID' },
  { key: 'steamSourceAvailable', label: 'Steam Source' },
  { key: 'chzzkMappingAvailable', label: 'Chzzk Mapping' },
  { key: 'latestBucketTime', label: 'Latest Context' },
] as const satisfies ReadonlyArray<{ key: CombinedGameOverviewSortKey; label: string }>

const getAriaSort = (columnKey: CombinedGameOverviewSortKey, sortState: CombinedGameOverviewSortState) => {
  if (sortState.key !== columnKey) {
    return 'none'
  }

  return sortState.direction === 'asc' ? 'ascending' : 'descending'
}

const getSortIndicator = (columnKey: CombinedGameOverviewSortKey, sortState: CombinedGameOverviewSortState) => {
  if (sortState.key !== columnKey) {
    return '↕'
  }

  return sortState.direction === 'asc' ? '↑' : '↓'
}

const formatCombinedRowCount = (count: number) =>
  `${count.toLocaleString('en-US')} Combined identity row${count === 1 ? '' : 's'}`

export function CombinedGameOverviewTable({
  rows,
  totalRowCount,
  loading = false,
  error = null,
  searchQuery = '',
  sortState,
  onSortChange,
}: CombinedGameOverviewTableProps) {
  const hasSearch = searchQuery.trim().length > 0
  const getNullableSupport = (value: string) => (value === '-' ? null : value)
  const resultCountLabel = hasSearch
    ? `${rows.length.toLocaleString('en-US')} of ${formatCombinedRowCount(totalRowCount)} match current search`
    : formatCombinedRowCount(totalRowCount)

  return (
    <section className="surface-low panel-worn ghost-outline rounded-[24px] px-4 py-4 lg:col-span-2 sm:px-5 sm:py-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Combined source
          </p>
          <h2 className="type-display mt-2 text-[1.65rem] font-bold text-[var(--text-primary)]">
            Identity availability
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            Canonical game identity with Steam source availability and nullable trusted Chzzk mapping identity/context
            from GET /combined/games/overview.
          </p>
        </div>

        <div className="surface-high panel-worn ghost-outline flex w-full flex-col gap-1 rounded-[18px] px-4 py-3 text-sm text-[var(--paper-dim)] md:w-auto">
          <span className="type-display font-semibold tracking-[0.02em] text-[var(--paper)]">
            Read-only · identity/source availability
          </span>
          <span>No provider fetch, write, backfill, or scheduler action is triggered by this view.</span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
        <CaveatBadge label="Identity only" title="This view exposes identity/source availability fields only." />
        <CaveatBadge label="Read-only" title="This view reads the Combined overview endpoint only." />
        <span>{resultCountLabel}</span>
      </div>

      <div className="mt-4 overflow-x-auto rounded-[18px] outline outline-1 outline-[var(--ghost-border)]">
        {error ? (
          <div className="surface-etched px-5 py-8 text-sm leading-6 text-[var(--text-secondary)]">
            <p>Combined identity/source availability view could not be loaded.</p>
            <p>{error}</p>
          </div>
        ) : loading && rows.length === 0 ? (
          <div className="surface-etched px-5 py-8 text-sm text-[var(--text-secondary)]">
            Loading Combined identity/source availability rows.
          </div>
        ) : rows.length === 0 ? (
          <div className="surface-etched px-5 py-8 text-sm text-[var(--text-secondary)]">
            {hasSearch && totalRowCount > 0
              ? 'No Combined identity/source availability rows match the current search.'
              : 'No Combined identity/source availability rows are available yet.'}
          </div>
        ) : (
          <table className="min-w-[1120px] w-full border-collapse bg-[rgba(255,249,239,0.34)] text-left">
            <thead>
              <tr className="border-b border-[var(--ghost-border)] text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">
                {tableColumns.map((column) => (
                  <th key={column.key} aria-sort={getAriaSort(column.key, sortState)} className="px-4 py-3 font-semibold">
                    <button
                      className="flex items-center gap-2 whitespace-nowrap transition hover:text-[var(--text-secondary)]"
                      onClick={() => onSortChange(column.key)}
                      type="button"
                    >
                      <span>{column.label}</span>
                      <span aria-hidden="true" className="text-[0.7rem] text-[var(--paper-dim)]">
                        {getSortIndicator(column.key, sortState)}
                      </span>
                    </button>
                  </th>
                ))}
                <th className="px-4 py-3 font-semibold">Chzzk Category</th>
                <th className="px-4 py-3 font-semibold">Category Type</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--ghost-border)]">
              {rows.map((row) => (
                <tr key={row.id} className="transition hover:bg-[rgba(255,249,239,0.42)]">
                  <td className="min-w-[240px] px-4 py-3 align-top">
                    <div className="font-semibold leading-snug text-[var(--text-primary)]">{row.canonicalName}</div>
                    <div className="mt-1 text-xs text-[var(--text-muted)]">steam_appid {row.steamAppidLabel}</div>
                  </td>
                  <CombinedCell value={String(row.canonicalGameId)} />
                  <CombinedCell title={row.steamSourceTitle} value={row.steamSourceLabel} />
                  <CombinedCell
                    support={getNullableSupport(row.chzzkCategoryIdLabel)}
                    title={row.chzzkMappingTitle}
                    value={row.chzzkMappingLabel}
                  />
                  <CombinedCell title={row.latestBucketTimeTitle} value={row.latestBucketTimeLabel} />
                  <CombinedCell support={getNullableSupport(row.chzzkCategoryIdLabel)} value={row.categoryNameLabel} />
                  <CombinedCell title={row.categoryTypeTitle} value={row.categoryTypeLabel} />
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
