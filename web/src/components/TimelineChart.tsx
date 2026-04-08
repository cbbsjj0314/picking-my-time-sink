import type { TimelinePoint, TimelineRange } from '../types'

interface TimelineChartProps {
  points: TimelinePoint[]
  selectedRange: TimelineRange
  onRangeChange: (range: TimelineRange) => void
}

const controls: TimelineRange[] = ['1D', '7D', '30D', '90D']

const buildPath = (
  values: number[],
  width: number,
  height: number,
  leftPadding: number,
  rightPadding: number,
  topPadding: number,
  bottomPadding: number,
) => {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const xStep = (width - leftPadding - rightPadding) / Math.max(values.length - 1, 1)
  const yRange = Math.max(max - min, 1)

  return values
    .map((value, index) => {
      const x = leftPadding + xStep * index
      const y = height - bottomPadding - ((value - min) / yRange) * (height - topPadding - bottomPadding)
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

export function TimelineChart({ points, selectedRange, onRangeChange }: TimelineChartProps) {
  const width = 860
  const height = 286
  const leftPadding = 54
  const rightPadding = 54
  const topPadding = 28
  const bottomPadding = 34
  const ccuValues = points.map((point) => point.ccu)
  const viewerValues = points.map((point) => point.viewers)
  const ccuPath = buildPath(ccuValues, width, height, leftPadding, rightPadding, topPadding, bottomPadding)
  const viewerPath = buildPath(viewerValues, width, height, leftPadding, rightPadding, topPadding, bottomPadding)
  const ccuMin = Math.min(...ccuValues)
  const ccuMax = Math.max(...ccuValues)
  const viewerMin = Math.min(...viewerValues)
  const viewerMax = Math.max(...viewerValues)

  return (
    <div className="surface-low panel-worn rounded-[28px] p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <h3 className="type-display text-[1.25rem] font-bold text-[var(--text-primary)]">Players vs Streaming Timeline</h3>

        <div className="surface-etched panel-worn flex flex-wrap items-center gap-1 rounded-full p-1">
          {controls.map((range) => {
            const selected = range === selectedRange

            return (
              <button
                key={range}
                className={`rounded-full px-3 py-2 text-xs font-semibold transition ${
                  selected ? 'paper-chip' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
                onClick={() => onRangeChange(range)}
                type="button"
              >
                {range}
              </button>
            )
          })}
        </div>
      </div>

      <div className="surface-etched panel-worn mt-5 rounded-[24px] p-4">
        <div className="mb-4 flex flex-col gap-3 text-xs lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-2 text-[var(--text-secondary)]">
              <span className="h-2.5 w-2.5 rounded-full bg-[#63B54F]" />
              CCU
            </span>
            <span className="flex items-center gap-2 text-[var(--text-secondary)]">
              <span className="h-2.5 w-2.5 rounded-full bg-[#E8639B]" />
              Avg viewers
            </span>
          </div>
          <div className="flex flex-wrap gap-4 lg:gap-6 text-[var(--text-muted)]">
            <span className="metric-text">CCU {ccuMin.toLocaleString('en-US')} - {ccuMax.toLocaleString('en-US')}</span>
            <span className="metric-text">Viewers {viewerMin.toLocaleString('en-US')} - {viewerMax.toLocaleString('en-US')}</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="min-w-[640px]">
            <svg className="w-full" viewBox={`0 0 ${width} ${height}`}>
              {[0, 1, 2, 3].map((index) => {
                const y = topPadding + ((height - topPadding - bottomPadding) / 3) * index
                return (
                  <line
                    key={index}
                    stroke="rgba(95,84,72,0.16)"
                    strokeDasharray="4 8"
                    strokeWidth="1"
                    x1={leftPadding}
                    x2={width - rightPadding}
                    y1={y}
                    y2={y}
                  />
                )
              })}

              <defs>
                <linearGradient id="viewer-line" x1="0%" x2="100%" y1="0%" y2="0%">
                  <stop offset="0%" stopColor="#E8639B" />
                  <stop offset="100%" stopColor="#E8639B" />
                </linearGradient>
                <linearGradient id="ccu-line" x1="0%" x2="100%" y1="0%" y2="0%">
                  <stop offset="0%" stopColor="#63B54F" />
                  <stop offset="100%" stopColor="#63B54F" />
                </linearGradient>
              </defs>

              <path d={ccuPath} fill="none" stroke="url(#ccu-line)" strokeLinecap="round" strokeWidth="3" />
              <path d={viewerPath} fill="none" stroke="url(#viewer-line)" strokeLinecap="round" strokeWidth="3" />

              {points.map((point, index) => {
                const x = leftPadding + ((width - leftPadding - rightPadding) / Math.max(points.length - 1, 1)) * index
                const showLabel =
                  points.length <= 7 || index === 0 || index === points.length - 1 || index % Math.ceil(points.length / 5) === 0

                return showLabel ? (
                  <text
                    key={`${point.label}-${index}`}
                    fill="rgba(95,84,72,0.78)"
                    fontSize="11"
                    textAnchor="middle"
                    x={x}
                    y={height - 10}
                  >
                    {point.label}
                  </text>
                ) : null
              })}
            </svg>
          </div>
        </div>
      </div>
    </div>
  )
}
