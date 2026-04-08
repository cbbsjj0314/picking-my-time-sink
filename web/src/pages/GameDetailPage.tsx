import type { ReactNode } from "react";
import type { LoaderFunctionArgs } from "react-router-dom";
import {
  Link,
  useLoaderData,
  useNavigation,
  useSearchParams,
} from "react-router-dom";

import { ApiError } from "../api/client";
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

type DetailStateCardProps = {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
};

type SecondaryStatRowProps = {
  label: string;
  value: string;
  hint: string;
  supporting?: string;
};

type HeaderVerdict = "Players healthy" | "Reviews positive" | "Price live" | "Deferred";

const RANGE_OPTIONS: DetailRange[] = ["30d", "90d"];

function normalizeRange(value: string | null): DetailRange {
  return value === "30d" ? "30d" : "90d";
}

function getRangeLabel(range: DetailRange): string {
  return range === "30d" ? "Last 30 days" : "Last 90 days";
}

function formatSignedRatioPoints(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "No prior delta";
  }

  const points = value * 100;
  const prefix = points > 0 ? "+" : "";
  return `${prefix}${points.toFixed(1)} pts`;
}

function formatLabelList(labels: string[]): string {
  if (labels.length <= 1) {
    return labels[0] ?? "";
  }

  if (labels.length === 2) {
    return `${labels[0]} and ${labels[1]}`;
  }

  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

function getCoverageState(dashboard: GameDashboardData): {
  availableCount: number;
  missingLabels: string[];
} {
  const missingLabels: string[] = [];

  if (!dashboard.ccu) {
    missingLabels.push("CCU signal");
  }

  if (dashboard.ccuHistory.length === 0) {
    missingLabels.push("CCU history");
  }

  if (!dashboard.price) {
    missingLabels.push("Price signal");
  }

  if (!dashboard.reviews) {
    missingLabels.push("Reviews signal");
  }

  return {
    availableCount: 4 - missingLabels.length,
    missingLabels,
  };
}

function getCoverageDescription(dashboard: GameDashboardData): string {
  const coverage = getCoverageState(dashboard);

  if (coverage.availableCount === 4) {
    return "CCU, CCU history, Reviews, and Price are all live for this title in the current Steam evidence set.";
  }

  if (coverage.availableCount === 0) {
    return "The canonical route is live, but the current Steam evidence set has not populated CCU, CCU history, Reviews, or Price for this title yet.";
  }

  return `${formatLabelList(coverage.missingLabels)} ${
    coverage.missingLabels.length === 1 ? "is" : "are"
  } still pending for this title in the current Steam evidence set.`;
}

function getHeaderVerdicts(dashboard: GameDashboardData): HeaderVerdict[] {
  const verdicts: HeaderVerdict[] = [];
  const coverage = getCoverageState(dashboard);

  if (dashboard.ccu && dashboard.ccuHistory.length > 0) {
    verdicts.push("Players healthy");
  }

  if (dashboard.reviews && dashboard.reviews.positive_ratio >= 0.7) {
    verdicts.push("Reviews positive");
  }

  if (verdicts.length < 2 && dashboard.price) {
    verdicts.push("Price live");
  }

  if (verdicts.length === 0 || (verdicts.length < 2 && coverage.availableCount < 4)) {
    verdicts.push("Deferred");
  }

  return verdicts.slice(0, 2);
}

function getCcuSupportingText(dashboard: GameDashboardData): string | undefined {
  const ccu = dashboard.ccu;

  if (!ccu) {
    return undefined;
  }

  if (ccu.missing_flag) {
    return "Prior-bucket comparison is still pending.";
  }

  return `${formatSignedInteger(ccu.delta_ccu_abs)} vs prior bucket · ${formatSignedPercent(
    ccu.delta_ccu_pct,
  )}`;
}

function getPriceSupportingText(dashboard: GameDashboardData): string | undefined {
  const price = dashboard.price;

  if (!price) {
    return undefined;
  }

  if (price.is_free) {
    return "Marked free in the latest KR row.";
  }

  if (price.discount_percent > 0) {
    return `${price.discount_percent}% off vs list price`;
  }

  return "No live discount in the latest KR row.";
}

function getReviewsSupportingText(dashboard: GameDashboardData): string | undefined {
  const reviews = dashboard.reviews;

  if (!reviews) {
    return undefined;
  }

  if (reviews.missing_flag) {
    return `${formatInteger(reviews.total_reviews)} lifetime reviews in the latest snapshot`;
  }

  return `${formatInteger(reviews.total_reviews)} lifetime reviews · ${formatSignedInteger(
    reviews.delta_total_reviews,
  )} vs prior day`;
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

function DetailStateCard({
  eyebrow,
  title,
  description,
  action,
}: DetailStateCardProps) {
  return (
    <div className="rounded-[1.75rem] border border-dashed border-white/10 bg-white/[0.03] p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
            {eyebrow}
          </p>
          <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">{title}</h3>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">{description}</p>
        </div>
        {action ? <div>{action}</div> : null}
      </div>
    </div>
  );
}

function SecondaryStatRow({
  label,
  value,
  hint,
  supporting,
}: SecondaryStatRowProps) {
  return (
    <div className="flex items-start justify-between gap-5 border-t border-white/[0.08] pt-4 first:border-t-0 first:pt-0">
      <div className="max-w-sm">
        <p className="text-[0.68rem] uppercase tracking-[0.28em] text-slate-500">{label}</p>
        <p className="mt-2 text-sm leading-6 text-slate-400">{hint}</p>
      </div>
      <div className="min-w-0 text-right">
        <p className="text-lg font-semibold tracking-tight text-white">{value}</p>
        {supporting ? <p className="mt-2 text-sm text-cyan-200">{supporting}</p> : null}
      </div>
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
  let dashboard: GameDashboardData;

  try {
    dashboard = await gamesApi.getGameDashboard(canonicalGameId, request.signal);
  } catch (error) {
    if (error instanceof ApiError) {
      throw new Response(
        error.status === 404
          ? "This selected game details route is not available in the current Steam-first slice."
          : "The latest Steam evidence view could not be loaded right now. Please retry from overview.",
        {
          status: error.status,
          statusText: error.status === 404 ? "Not Found" : "Unavailable",
        },
      );
    }

    throw error;
  }

  return {
    canonicalGameId,
    range: normalizeRange(url.searchParams.get("range")),
    dashboard,
  };
}

export function GameDetailPage() {
  const { canonicalGameId, range, dashboard } = useLoaderData() as GameDetailLoaderData;
  const [searchParams, setSearchParams] = useSearchParams();
  const navigation = useNavigation();
  const visibleHistory =
    range === "30d" ? dashboard.ccuHistory.slice(-30) : dashboard.ccuHistory;
  const title =
    dashboard.ccu?.canonical_name ??
    dashboard.price?.canonical_name ??
    dashboard.reviews?.canonical_name ??
    `Canonical Game ${canonicalGameId}`;
  const coverage = getCoverageState(dashboard);
  const coverageDescription = getCoverageDescription(dashboard);
  const headerVerdicts = getHeaderVerdicts(dashboard);
  const detailPath = `/games/${canonicalGameId}`;
  const isPendingCurrentRoute =
    navigation.state !== "idle" && navigation.location?.pathname === detailPath;
  const pendingRange = isPendingCurrentRoute
    ? normalizeRange(new URLSearchParams(navigation.location.search).get("range"))
    : range;
  const historyWindowLabel = getRangeLabel(range);
  const pendingStatusLabel =
    pendingRange !== range
      ? `Switching to ${getRangeLabel(pendingRange).toLowerCase()}`
      : "Refreshing latest detail snapshot";
  const historyWindowSummary =
    visibleHistory.length > 0
      ? `${visibleHistory.length} daily points · ${formatDateLabel(
          visibleHistory[0]?.bucket_date,
        )} to ${formatDateLabel(visibleHistory[visibleHistory.length - 1]?.bucket_date)}`
      : "Awaiting daily trend";

  function applyRange(nextRange: DetailRange) {
    if (nextRange === range) {
      return;
    }

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
              Selected Game Details
            </p>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
              {title}
            </h1>
            <p className="mt-5 text-sm uppercase tracking-[0.28em] text-slate-500">
              Steam source view
            </p>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400">
              Fixed Steam evidence set for this canonical route: CCU first, then Reviews,
              then Price. The route stays on the existing live API reads only.
            </p>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-500">
              Canonical {canonicalGameId} keeps the current route/API/backend semantics and
              does not add source tabs, ranking-window state, or demo labeling in this
              slice.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              {headerVerdicts.map((verdict) => (
                <span
                  key={verdict}
                  className={[
                    "rounded-full border px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em]",
                    verdict === "Deferred"
                      ? "border-white/10 bg-white/[0.03] text-slate-300"
                      : "border-cyan-300/20 bg-cyan-300/[0.08] text-cyan-100",
                  ].join(" ")}
                >
                  {verdict}
                </span>
              ))}
              {isPendingCurrentRoute ? (
                <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-100">
                  {pendingStatusLabel}
                </span>
              ) : null}
            </div>
          </div>

          <div className="rounded-[1.75rem] border border-cyan-400/[0.15] bg-cyan-400/[0.08] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-100">
              Route state
            </p>
            <p className="mt-4 text-2xl font-semibold tracking-tight text-white">
              /games/{canonicalGameId}
            </p>
            <p className="mt-4 max-w-sm text-sm leading-7 text-cyan-50/[0.85]">
              Steam source view on a canonical path with {coverage.availableCount}/4 live
              evidence reads. `range` remains the only route-level control and only clips
              the fixed CCU history already served by the backend.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {RANGE_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => applyRange(option)}
                  disabled={isPendingCurrentRoute}
                  className={[
                    "rounded-full border px-4 py-2 text-sm transition disabled:cursor-wait disabled:opacity-70",
                    range === option
                      ? "border-cyan-300/40 bg-cyan-300/[0.14] text-white"
                      : "border-white/10 bg-white/[0.03] text-slate-300 hover:border-cyan-400/20 hover:text-white",
                  ].join(" ")}
                >
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
            <p className="mt-4 text-xs uppercase tracking-[0.28em] text-cyan-100/80">
              {isPendingCurrentRoute
                ? `${pendingStatusLabel}...`
                : `${historyWindowLabel} on top of a fixed 90-day CCU backend window`}
            </p>
          </div>
        </div>

        {coverage.availableCount < 4 ? (
          <div className="mt-8">
            <DetailStateCard
              eyebrow="Pending"
              title={
                coverage.availableCount === 0
                  ? "The Steam evidence set is still populating"
                  : "Part of the Steam evidence set is still pending"
              }
              description={coverageDescription}
            />
          </div>
        ) : null}
      </section>

      <SectionFrame
        eyebrow="Selected Game Details"
        title="Steam evidence set"
        description="The detail route keeps one fixed evidence set regardless of how the title was surfaced. In this slice that means CCU, Reviews, and Price only."
        action={
          <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-300">
            {coverage.availableCount}/4 live reads
          </span>
        }
        delayMs={80}
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <MetricStrip
            label="CCU"
            value={formatCompactInteger(dashboard.ccu?.ccu)}
            hint={
              dashboard.ccu?.bucket_time
                ? `Latest CCU snapshot from ${formatDateTimeLabel(dashboard.ccu.bucket_time)}`
                : "The current CCU signal has not been served for this title yet."
            }
            supporting={getCcuSupportingText(dashboard)}
          />
          <MetricStrip
            label="Reviews"
            value={formatPercentRatio(dashboard.reviews?.positive_ratio)}
            hint={
              dashboard.reviews?.snapshot_date
                ? `Latest review snapshot on ${formatDateLabel(
                    dashboard.reviews.snapshot_date,
                  )}`
                : "The current Reviews signal has not been served for this title yet."
            }
            supporting={getReviewsSupportingText(dashboard)}
          />
          <MetricStrip
            label="Price"
            value={formatCurrencyMinor(
              dashboard.price?.final_price_minor,
              dashboard.price?.currency_code,
            )}
            hint={
              dashboard.price?.bucket_time
                ? `Latest KR store row from ${formatDateTimeLabel(
                    dashboard.price.bucket_time,
                  )}`
                : "The current Price signal has not been served for this title yet."
            }
            supporting={getPriceSupportingText(dashboard)}
          />
        </div>
      </SectionFrame>

      <SectionFrame
        eyebrow="CCU"
        title="CCU history"
        description="CCU is the main chart for the Steam detail view. `range` only decides how much of the existing fixed 90-day backend window is visible."
        action={
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-100">
              {historyWindowLabel}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-300">
              {historyWindowSummary}
            </span>
          </div>
        }
        delayMs={140}
      >
        {visibleHistory.length > 0 ? (
          <SimpleHistoryChart data={visibleHistory} />
        ) : (
          <DetailStateCard
            eyebrow="Pending"
            title="CCU history is not available yet"
            description={
              dashboard.ccu
                ? "The latest CCU snapshot exists for this title, but the fixed daily history window has not populated yet."
                : "This title does not have CCU history in the current Steam-first detail slice yet."
            }
          />
        )}
      </SectionFrame>

      <SectionFrame
        eyebrow="Supporting Panels"
        title="Reviews and Price"
        description="Supporting cards stay narrow and mechanical. Reviews uses the latest live snapshot, and Price stays on the current KR state without broader store semantics."
        delayMs={200}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              Reviews
            </p>
            <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
              Latest review signal
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate-400">
              Current live API exposes the latest review snapshot for this title, so this
              card stays on positive share, lifetime scale, and recent movement only.
            </p>

            {dashboard.reviews ? (
              <>
                <div className="mt-6 rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div>
                      <p className="text-[0.68rem] uppercase tracking-[0.32em] text-slate-500">
                        Recent positive
                      </p>
                      <p className="mt-3 text-3xl font-semibold tracking-tight text-white">
                        {formatPercentRatio(dashboard.reviews.positive_ratio)}
                      </p>
                    </div>
                    <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-100">
                      {dashboard.reviews.missing_flag
                        ? "Pending"
                        : formatSignedRatioPoints(dashboard.reviews.delta_positive_ratio)}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-slate-400">
                    Latest review snapshot from{" "}
                    {formatDateLabel(dashboard.reviews.snapshot_date)}.
                  </p>
                </div>

                <div className="mt-6 space-y-4">
                  <SecondaryStatRow
                    label="Lifetime reviews"
                    value={formatInteger(dashboard.reviews.total_reviews)}
                    hint="All reviews captured in the latest served summary row."
                    supporting={`${formatInteger(
                      dashboard.reviews.total_positive,
                    )} positive · ${formatInteger(dashboard.reviews.total_negative)} negative`}
                  />
                  <SecondaryStatRow
                    label="Recent movement"
                    value={
                      dashboard.reviews.missing_flag
                        ? "Pending"
                        : formatSignedInteger(dashboard.reviews.delta_total_reviews)
                    }
                    hint="Day-over-day change when a prior review snapshot exists."
                    supporting={
                      dashboard.reviews.missing_flag
                        ? "A prior review baseline is not available for this title yet."
                        : `${formatSignedRatioPoints(
                            dashboard.reviews.delta_positive_ratio,
                          )} positive-share shift`
                    }
                  />
                  <SecondaryStatRow
                    label="Snapshot context"
                    value={formatDateLabel(dashboard.reviews.snapshot_date)}
                    hint="The current detail route keeps Reviews on the latest served daily summary."
                    supporting="Positive share remains the current live API fallback for summary tone."
                  />
                </div>
              </>
            ) : (
              <div className="mt-6">
                <DetailStateCard
                  eyebrow="Pending"
                  title="Reviews signal is not available yet"
                  description="This title does not have a latest review snapshot in the current slice yet, so the card stays visible with a restrained pending state."
                />
              </div>
            )}
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              Price
            </p>
            <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
              Current price state
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate-400">
              Current KR price state and light purchase context from the latest served row,
              kept inside the current read-only boundary without broader store semantics.
            </p>

            {dashboard.price ? (
              <>
                <div className="mt-6 rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div>
                      <p className="text-[0.68rem] uppercase tracking-[0.32em] text-slate-500">
                        Current price
                      </p>
                      <p className="mt-3 text-3xl font-semibold tracking-tight text-white">
                        {formatCurrencyMinor(
                          dashboard.price.final_price_minor,
                          dashboard.price.currency_code,
                        )}
                      </p>
                    </div>
                    <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-100">
                      {dashboard.price.is_free
                        ? "Free"
                        : dashboard.price.discount_percent > 0
                          ? `${dashboard.price.discount_percent}% off`
                          : "Full price"}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-slate-400">
                    Latest KR store row from {formatDateTimeLabel(dashboard.price.bucket_time)}
                    .
                  </p>
                </div>

                <div className="mt-6 space-y-4">
                  <SecondaryStatRow
                    label="List price"
                    value={formatCurrencyMinor(
                      dashboard.price.initial_price_minor,
                      dashboard.price.currency_code,
                    )}
                    hint="The initial KR price paired with the same latest row."
                  />
                  <SecondaryStatRow
                    label="Discount"
                    value={
                      dashboard.price.is_free
                        ? "Free"
                        : `${dashboard.price.discount_percent}%`
                    }
                    hint="Current discount state against the same served list price."
                    supporting={
                      dashboard.price.is_free
                        ? "Marked free in the latest store row"
                        : `${formatCurrencyMinor(
                            dashboard.price.final_price_minor,
                            dashboard.price.currency_code,
                          )} now`
                    }
                  />
                  <SecondaryStatRow
                    label="Snapshot context"
                    value={`${dashboard.price.region} · ${dashboard.price.currency_code}`}
                    hint="The current detail route keeps Price KR-centered and read-only."
                    supporting={`Bucket ${formatDateTimeLabel(dashboard.price.bucket_time)}`}
                  />
                </div>
              </>
            ) : (
              <div className="mt-6">
                <DetailStateCard
                  eyebrow="Pending"
                  title="Price signal is not available yet"
                  description="This title does not have a latest KR price row in the current slice yet, so the card stays visible with a restrained pending state."
                />
              </div>
            )}
          </div>
        </div>
      </SectionFrame>
    </div>
  );
}
