import { formatCompactInteger, formatDateLabel } from "../lib/format";

type ChartPoint = {
  bucket_date: string;
  avg_ccu: number;
};

type SimpleHistoryChartProps = {
  data: ChartPoint[];
};

const WIDTH = 720;
const HEIGHT = 280;
const PADDING_X = 20;
const PADDING_Y = 24;

function buildPath(data: ChartPoint[]): {
  areaPath: string;
  linePath: string;
  latestX: number;
  latestY: number;
  maxValue: number;
  minValue: number;
} | null {
  if (data.length === 0) {
    return null;
  }

  const plotWidth = WIDTH - PADDING_X * 2;
  const plotHeight = HEIGHT - PADDING_Y * 2;
  const values = data.map((point) => point.avg_ccu);
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);
  const range = maxValue - minValue || 1;

  const points = data.map((point, index) => {
    const x =
      data.length === 1
        ? WIDTH / 2
        : PADDING_X + (index / (data.length - 1)) * plotWidth;
    const y =
      PADDING_Y + (1 - (point.avg_ccu - minValue) / range) * plotHeight;
    return { x, y };
  });

  const linePath = points
    .map((point, index) =>
      `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`,
    )
    .join(" ");

  const firstPoint = points[0];
  const lastPoint = points[points.length - 1]!;
  const baseline = HEIGHT - PADDING_Y;
  const areaPath = `${linePath} L ${lastPoint.x.toFixed(2)} ${baseline.toFixed(2)} L ${firstPoint.x.toFixed(2)} ${baseline.toFixed(2)} Z`;

  return {
    areaPath,
    linePath,
    latestX: lastPoint.x,
    latestY: lastPoint.y,
    maxValue,
    minValue,
  };
}

export function SimpleHistoryChart({ data }: SimpleHistoryChartProps) {
  const path = buildPath(data);

  if (!path) {
    return (
      <div className="flex h-[17.5rem] items-center justify-center rounded-[2rem] border border-dashed border-white/10 bg-white/[0.02] text-sm text-slate-500">
        No history loaded yet.
      </div>
    );
  }

  const firstDate = data[0]?.bucket_date;
  const lastDate = data[data.length - 1]?.bucket_date;

  return (
    <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-slate-900/[0.55] p-5 shadow-[0_18px_48px_rgba(2,6,23,0.36)]">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-white">Average CCU history</p>
          <p className="mt-2 text-sm text-slate-400">
            Fixed 90-day backend history, clipped by the route range preset.
          </p>
        </div>
        <div className="text-right">
          <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">
            Peak
          </p>
          <p className="mt-2 text-xl font-semibold text-cyan-100">
            {formatCompactInteger(path.maxValue)}
          </p>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-72 w-full overflow-visible"
        role="img"
        aria-label="Average CCU history chart"
      >
        {[0.25, 0.5, 0.75].map((fraction) => {
          const y = PADDING_Y + (HEIGHT - PADDING_Y * 2) * fraction;
          return (
            <line
              key={fraction}
              x1={PADDING_X}
              x2={WIDTH - PADDING_X}
              y1={y}
              y2={y}
              stroke="rgba(148, 163, 184, 0.12)"
              strokeDasharray="6 10"
            />
          );
        })}

        <path d={path.areaPath} fill="url(#history-fill)" opacity="0.9" />
        <path
          d={path.linePath}
          fill="none"
          stroke="rgba(34, 211, 238, 0.92)"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle
          cx={path.latestX}
          cy={path.latestY}
          r="6"
          fill="#67e8f9"
          stroke="rgba(8, 47, 73, 0.9)"
          strokeWidth="4"
        />
        <defs>
          <linearGradient id="history-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(34, 211, 238, 0.42)" />
            <stop offset="100%" stopColor="rgba(34, 211, 238, 0.02)" />
          </linearGradient>
        </defs>
      </svg>

      <div className="mt-5 flex items-center justify-between gap-4 text-sm text-slate-400">
        <span>{formatDateLabel(firstDate)}</span>
        <span>{formatDateLabel(lastDate)}</span>
      </div>

      <div className="mt-4 grid gap-3 border-t border-white/10 pt-4 text-sm text-slate-400 sm:grid-cols-2">
        <div>
          <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">
            Floor
          </p>
          <p className="mt-2 text-base font-medium text-white">
            {formatCompactInteger(path.minValue)}
          </p>
        </div>
        <div className="sm:text-right">
          <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">
            Latest
          </p>
          <p className="mt-2 text-base font-medium text-white">
            {formatCompactInteger(data[data.length - 1]?.avg_ccu)}
          </p>
        </div>
      </div>
    </div>
  );
}
