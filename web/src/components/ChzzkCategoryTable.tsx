import type { ChzzkCategorySortKey, ChzzkCategorySortState, ChzzkCategoryTableRow } from '../lib/chzzkCategoryViewModel'

interface ChzzkCategoryTableProps {
  rows: ChzzkCategoryTableRow[]
  totalRowCount: number
  loading?: boolean
  error?: string | null
  searchQuery?: string
  sortState: ChzzkCategorySortState
  onSortChange: (key: ChzzkCategorySortKey) => void
}

interface CategoryCellProps {
  value: string
  support?: string | null
  title?: string | null
}

function CaveatBadge({ label, title }: { label: string; title?: string | null }) {
  return (
    <span
      className="inline-flex h-5 shrink-0 items-center rounded border border-[var(--ghost-border-strong)] bg-[rgba(255,244,226,0.78)] px-1.5 text-[0.64rem] font-bold uppercase leading-none text-[var(--amber)]"
      title={title ?? undefined}
    >
      {label}
    </span>
  )
}

function CategoryMetricCell({ value, support = null, title = null }: CategoryCellProps) {
  return (
    <td className="px-4 py-3 align-top" title={title ?? undefined}>
      <div className="metric-text min-h-5 whitespace-nowrap text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
      {support ? <div className="mt-1 whitespace-nowrap text-xs text-[var(--text-muted)]">{support}</div> : null}
    </td>
  )
}

const tableColumns = [
  { key: 'category', label: 'Category' },
  { key: 'latestViewers', label: 'Latest Viewers' },
  { key: 'viewerHours', label: 'Viewer-Hours' },
  { key: 'avgViewers', label: 'Avg Viewers' },
  { key: 'peakViewers', label: 'Peak Viewers' },
  { key: 'avgChannels', label: 'Avg Channels' },
  { key: 'peakChannels', label: 'Peak Channels' },
  { key: 'viewersPerChannel', label: 'Viewers / Channel' },
] as const satisfies ReadonlyArray<{ key: ChzzkCategorySortKey; label: string }>

const getAriaSort = (columnKey: ChzzkCategorySortKey, sortState: ChzzkCategorySortState) => {
  if (sortState.key !== columnKey) {
    return 'none'
  }

  return sortState.direction === 'asc' ? 'ascending' : 'descending'
}

const getSortIndicator = (columnKey: ChzzkCategorySortKey, sortState: ChzzkCategorySortState) => {
  if (sortState.key !== columnKey) {
    return '↕'
  }

  return sortState.direction === 'asc' ? '↑' : '↓'
}

const getUniformEvidenceLabel = (
  rows: ChzzkCategoryTableRow[],
  selector: (row: ChzzkCategoryTableRow) => string | null,
  label: string,
) => {
  const values = Array.from(new Set(rows.map(selector).filter((value): value is string => value !== null)))

  if (values.length === 0) {
    return null
  }

  if (values.length === 1) {
    return `${label} ${values[0]}`
  }

  return `${label} mixed evidence`
}

export function ChzzkCategoryTable({
  rows,
  totalRowCount,
  loading = false,
  error = null,
  searchQuery = '',
  sortState,
  onSortChange,
}: ChzzkCategoryTableProps) {
  const hasSearch = searchQuery.trim().length > 0
  const evidenceLabels = [
    getUniformEvidenceLabel(rows, (row) => row.observedWindowLabel, 'Window'),
    getUniformEvidenceLabel(rows, (row) => row.coverageLabel, 'Coverage'),
  ].filter((value): value is string => value !== null)

  return (
    <section className="surface-low panel-worn ghost-outline rounded-[24px] px-4 py-4 lg:col-span-2 sm:px-5 sm:py-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Chzzk source
          </p>
          <h2 className="type-display mt-2 text-[1.65rem] font-bold text-[var(--text-primary)]">Explore</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            Category-only observed evidence from the Chzzk category overview API. Values remain bounded samples.
          </p>
        </div>

        <div className="surface-high panel-worn ghost-outline flex w-full flex-col gap-1 rounded-[18px] px-4 py-3 text-sm text-[var(--paper-dim)] md:w-auto">
          <span className="type-display font-semibold tracking-[0.02em] text-[var(--paper)]">
            Observed Sample · KR / KST
          </span>
          <span>API context label only. Observed buckets; no full-window claim.</span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
        <CaveatBadge label="Category-only" title="Chzzk category evidence only; no game mapping." />
        <CaveatBadge label="Bounded sample" title="Bounded pagination/live-list sample; not full population." />
        {evidenceLabels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-[18px] outline outline-1 outline-[var(--ghost-border)]">
        {error ? (
          <div className="surface-etched px-5 py-8 text-sm leading-6 text-[var(--text-secondary)]">{error}</div>
        ) : loading && rows.length === 0 ? (
          <div className="surface-etched px-5 py-8 text-sm text-[var(--text-secondary)]">
            Loading Chzzk category evidence.
          </div>
        ) : rows.length === 0 ? (
          <div className="surface-etched px-5 py-8 text-sm text-[var(--text-secondary)]">
            {hasSearch && totalRowCount > 0
              ? 'No Chzzk category rows match the current search.'
              : 'No Chzzk category rows are available.'}
          </div>
        ) : (
          <table className="min-w-[1080px] w-full border-collapse bg-[rgba(255,249,239,0.34)] text-left">
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
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--ghost-border)]">
              {rows.map((row) => (
                <tr key={row.id} className="transition hover:bg-[rgba(255,249,239,0.42)]">
                  <td className="min-w-[220px] px-4 py-3 align-top">
                    <div className="font-semibold leading-snug text-[var(--text-primary)]">{row.categoryName}</div>
                  </td>
                  <CategoryMetricCell
                    support={row.observedBucketLabel}
                    title={row.latestViewersTitle}
                    value={row.latestViewersLabel}
                  />
                  <CategoryMetricCell
                    support={row.boundedSampleLabel}
                    title={row.boundedSampleTitle}
                    value={row.viewerHoursLabel}
                  />
                  <CategoryMetricCell support={row.coverageLabel} value={row.avgViewersLabel} />
                  <CategoryMetricCell support={row.coverageLabel} value={row.peakViewersLabel} />
                  <CategoryMetricCell title={row.avgChannelsTitle} value={row.avgChannelsLabel} />
                  <CategoryMetricCell title={row.peakChannelsTitle} value={row.peakChannelsLabel} />
                  <CategoryMetricCell title={row.viewersPerChannelTitle} value={row.viewersPerChannelLabel} />
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
