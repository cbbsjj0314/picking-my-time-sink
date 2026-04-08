import type { SteamCcuPoint, SteamChartRange, SteamChartState } from '../types'

interface SteamCcuChartProps {
  points: SteamCcuPoint[]
  selectedRange: SteamChartRange
  onRangeChange: (range: SteamChartRange) => void
  state?: SteamChartState
}

const controls: Array<{ value: SteamChartRange; label: string }> = [
  { value: '7D', label: '7D' },
  { value: '30D', label: '30D' },
  { value: '90D', label: '90D' },
]

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

export function SteamCcuChart({ points, selectedRange, onRangeChange, state }: SteamCcuChartProps) {
  const width = 860
  const height = 286
  const leftPadding = 54
  const rightPadding = 54
  const topPadding = 28
  const bottomPadding = 34
  const hasPoints = points.length > 0
  const ccuValues = hasPoints ? points.map((point) => point.ccu) : []
  const ccuPath = hasPoints ? buildPath(ccuValues, width, height, leftPadding, rightPadding, topPadding, bottomPadding) : ''
  const ccuMin = hasPoints ? Math.min(...ccuValues) : null
  const ccuMax = hasPoints ? Math.max(...ccuValues) : null

  return (
    <div className="surface-low panel-worn rounded-[28px] p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div>
          <h3 className="type-display text-[1.25rem] font-bold text-[var(--text-primary)]">CCU</h3>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">차트 기간 변경은 이 CCU 히스토리 그래프에만 적용됩니다.</p>
        </div>

        <div className="surface-etched panel-worn flex flex-wrap items-center gap-1 rounded-full p-1">
          {controls.map((control) => {
            const selected = control.value === selectedRange

            return (
              <button
                key={control.value}
                className={`rounded-full px-3 py-2 text-xs font-semibold transition ${
                  selected ? 'paper-chip' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
                onClick={() => onRangeChange(control.value)}
                type="button"
              >
                {control.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="surface-etched panel-worn mt-5 rounded-[24px] p-4">
        <div className="mb-4 flex flex-col gap-3 text-xs lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-2 text-[var(--text-secondary)]">
            <span className="h-2.5 w-2.5 rounded-full bg-[#63B54F]" />
            CCU
          </div>
          <span className="metric-text text-[var(--text-muted)]">
            {ccuMin !== null && ccuMax !== null ? `CCU ${ccuMin.toLocaleString('en-US')} - ${ccuMax.toLocaleString('en-US')}` : 'CCU 히스토리를 기다리는 중'}
          </span>
        </div>

        {hasPoints ? (
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
                  <linearGradient id="steam-ccu-line" x1="0%" x2="100%" y1="0%" y2="0%">
                    <stop offset="0%" stopColor="#63B54F" />
                    <stop offset="100%" stopColor="#4F9FE2" />
                  </linearGradient>
                </defs>

                <path d={ccuPath} fill="none" stroke="url(#steam-ccu-line)" strokeLinecap="round" strokeWidth="3" />

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
        ) : (
          <div className="flex min-h-[220px] items-center justify-center rounded-[18px] border border-dashed border-[rgba(95,84,72,0.28)] px-5 py-8 text-center text-sm leading-6 text-[var(--text-secondary)]">
            {state?.message ?? '선택한 게임의 CCU 히스토리가 아직 없습니다.'}
          </div>
        )}
      </div>
    </div>
  )
}
