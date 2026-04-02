import type { LoaderFunctionArgs } from "react-router-dom";
import { Link, useLoaderData, useSearchParams } from "react-router-dom";

import { gamesApi, type GameDashboardData } from "../api/games";
import { SectionFrame } from "../components/SectionFrame";
import { SimpleHistoryChart } from "../components/SimpleHistoryChart";
import {
  formatCompactInteger,
  formatCurrencyMinor,
  formatDateLabel,
  formatDateTimeLabel,
  formatInteger,
  formatPercentRatio,
  formatSignedInteger,
  formatSignedPercent,
} from "../lib/format";

type DetailRange = "30d" | "90d";

type GameDetailLoaderData = {
  canonicalGameId: number;
  range: DetailRange;
  dashboard: GameDashboardData;
};

type MetricStripProps = {
  label: string;
  value: string;
  hint: string;
  supporting?: string;
};

const RANGE_OPTIONS: DetailRange[] = ["30d", "90d"];

function normalizeRange(value: string | null): DetailRange {
  return value === "30d" ? "30d" : "90d";
}

function MetricStrip({ label, value, hint, supporting }: MetricStripProps) {
  return (
    <div className="rounded-[1.75rem] border border-white/10 bg-white/[0.03] p-5">
      <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">{label}</p>
      <p className="mt-4 text-2xl font-semibold tracking-tight text-white">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-400">{hint}</p>
      {supporting ? <p className="mt-3 text-sm text-cyan-200">{supporting}</p> : null}
    </div>
  );
}

export async function gameDetailLoader({
  params,
  request,
}: LoaderFunctionArgs): Promise<GameDetailLoaderData> {
  const canonicalGameId = Number(params.canonical_game_id);

  if (!Number.isInteger(canonicalGameId)) {
    throw new Response("Game not found", { status: 404 });
  }

  const url = new URL(request.url);

  return {
    canonicalGameId,
    range: normalizeRange(url.searchParams.get("range")),
    dashboard: await gamesApi.getGameDashboard(canonicalGameId, request.signal),
  };
}

export function GameDetailPage() {
  const { canonicalGameId, range, dashboard } = useLoaderData() as GameDetailLoaderData;
  const [searchParams, setSearchParams] = useSearchParams();
  const visibleHistory =
    range === "30d" ? dashboard.ccuHistory.slice(-30) : dashboard.ccuHistory;
  const title =
    dashboard.ccu?.canonical_name ??
    dashboard.price?.canonical_name ??
    dashboard.reviews?.canonical_name ??
    `Canonical Game ${canonicalGameId}`;

  function applyRange(nextRange: DetailRange) {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("range", nextRange);
    setSearchParams(nextParams);
  }

  return (
    <div className="space-y-12">
      <section className="animate-section-enter rounded-[2rem] border border-white/10 bg-white/[0.035] p-6 shadow-[0_24px_70px_rgba(2,6,23,0.34)] md:p-8">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Link
              to="/overview"
              className="inline-flex items-center gap-2 text-sm text-cyan-200 transition hover:text-cyan-100"
            >
              <span aria-hidden="true">←</span>
              <span>Back to overview</span>
            </Link>
            <p className="mt-6 text-[0.68rem] uppercase tracking-[0.34em] text-cyan-300/80">
              Game Detail
            </p>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
              {title}
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-400">
              The route identity comes from the canonical game path param. The only shareable
              page state in this thin slice is the `range` query preset, which clips the
              fixed 90-day history returned by the current backend.
            </p>
          </div>

          <div className="rounded-[1.75rem] border border-cyan-400/[0.15] bg-cyan-400/[0.08] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-100">
              Route state
            </p>
            <p className="mt-4 text-2xl font-semibold tracking-tight text-white">
              /games/{canonicalGameId}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {RANGE_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => applyRange(option)}
                  className={[
                    "rounded-full border px-4 py-2 text-sm transition",
                    range === option
                      ? "border-cyan-300/40 bg-cyan-300/[0.14] text-white"
                      : "border-white/10 bg-white/[0.03] text-slate-300 hover:border-cyan-400/20 hover:text-white",
                  ].join(" ")}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <SectionFrame
        eyebrow="Summary"
        title="Latest operating snapshot"
        description="This page shell already reads the existing single-game endpoints so the route is useful now, even though richer drill-down and comparison remain out of scope."
        delayMs={80}
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <MetricStrip
            label="Latest CCU"
            value={formatCompactInteger(dashboard.ccu?.ccu)}
            hint={
              dashboard.ccu?.bucket_time
                ? `Bucket ${formatDateTimeLabel(dashboard.ccu.bucket_time)}`
                : "Latest CCU row is not available for this game."
            }
            supporting={
              dashboard.ccu
                ? `${formatSignedInteger(dashboard.ccu.delta_ccu_abs)} · ${formatSignedPercent(
                    dashboard.ccu.delta_ccu_pct,
                  )}`
                : undefined
            }
          />
          <MetricStrip
            label="Current price"
            value={formatCurrencyMinor(
              dashboard.price?.final_price_minor,
              dashboard.price?.currency_code,
            )}
            hint={
              dashboard.price?.bucket_time
                ? `KR snapshot ${formatDateTimeLabel(dashboard.price.bucket_time)}`
                : "Price wiring is still partial for this game shell."
            }
            supporting={
              dashboard.price
                ? `${dashboard.price.discount_percent}% discount`
                : undefined
            }
          />
          <MetricStrip
            label="Review sentiment"
            value={formatPercentRatio(dashboard.reviews?.positive_ratio)}
            hint={
              dashboard.reviews?.snapshot_date
                ? `Snapshot ${formatDateLabel(dashboard.reviews.snapshot_date)}`
                : "Review summary is not available for this game."
            }
            supporting={
              dashboard.reviews
                ? `${formatInteger(dashboard.reviews.total_reviews)} total reviews`
                : undefined
            }
          />
        </div>
      </SectionFrame>

      <SectionFrame
        eyebrow="History"
        title="CCU range view"
        description="The backend stays fixed at the recent 90-day history endpoint. The query string decides whether this slice shows the whole window or a clipped 30-day view."
        delayMs={140}
      >
        <SimpleHistoryChart data={visibleHistory} />
      </SectionFrame>

      <SectionFrame
        eyebrow="Secondary Panels"
        title="Price and reviews remain intentionally light"
        description="The page keeps both supporting data groups visible so the structure is stable, but it does not grow into a generalized analytics surface in this first frontend delivery."
        delayMs={200}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              Price
            </p>
            <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
              Current KR price snapshot
            </h3>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <MetricStrip
                label="Current"
                value={formatCurrencyMinor(
                  dashboard.price?.final_price_minor,
                  dashboard.price?.currency_code,
                )}
                hint="Final price from the latest KR row."
              />
              <MetricStrip
                label="Initial"
                value={formatCurrencyMinor(
                  dashboard.price?.initial_price_minor,
                  dashboard.price?.currency_code,
                )}
                hint="Initial price paired with the same row."
              />
            </div>
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              Reviews
            </p>
            <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
              Latest review shape
            </h3>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <MetricStrip
                label="Positive ratio"
                value={formatPercentRatio(dashboard.reviews?.positive_ratio)}
                hint="Calculated from the latest reviews serving row."
              />
              <MetricStrip
                label="Delta reviews"
                value={formatSignedInteger(dashboard.reviews?.delta_total_reviews)}
                hint="Day-over-day total review movement when prior data exists."
              />
            </div>
          </div>
        </div>
      </SectionFrame>
    </div>
  );
}
