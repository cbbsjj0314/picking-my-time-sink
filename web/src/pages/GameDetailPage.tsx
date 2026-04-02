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
    missingLabels.push("latest player snapshot");
  }

  if (dashboard.ccuHistory.length === 0) {
    missingLabels.push("recent player trend");
  }

  if (!dashboard.price) {
    missingLabels.push("KR price snapshot");
  }

  if (!dashboard.reviews) {
    missingLabels.push("review summary");
  }

  return {
    availableCount: 4 - missingLabels.length,
    missingLabels,
  };
}

function getCoverageDescription(dashboard: GameDashboardData): string {
  const coverage = getCoverageState(dashboard);

  if (coverage.availableCount === 4) {
    return "All current detail reads are live for this title inside the Steam-only baseline.";
  }

  if (coverage.availableCount === 0) {
    return "The canonical route is available, but the current Steam-only feeds have not populated player, price, review, or recent trend rows for this title yet.";
  }

  return `${formatLabelList(coverage.missingLabels)} ${
    coverage.missingLabels.length === 1 ? "is" : "are"
  } still pending for this title in the current read-only slice.`;
}

function getCcuSupportingText(dashboard: GameDashboardData): string | undefined {
  const ccu = dashboard.ccu;

  if (!ccu) {
    return undefined;
  }

  if (ccu.missing_flag) {
    return "Prior-day bucket delta is not available yet.";
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
    return `${formatInteger(reviews.total_reviews)} total reviews in the latest snapshot`;
  }

  return `${formatInteger(reviews.total_reviews)} total reviews · ${formatSignedInteger(
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
          ? "This game detail route is not available in the current Steam-only slice."
          : "The latest Steam detail snapshot could not be loaded right now. Please retry from overview.",
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
              Game Detail
            </p>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
              {title}
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-400">
              Steam-only detail snapshot for this title across recent player activity,
              current KR store pricing, and latest review sentiment. The route stays
              read-only and only uses the existing FastAPI detail reads already available
              in the current slice.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-300">
                Steam-only
              </span>
              <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-300">
                KR serving baseline
              </span>
              <span
                className={[
                  "rounded-full border px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em]",
                  coverage.availableCount === 4
                    ? "border-cyan-300/20 bg-cyan-300/[0.08] text-cyan-100"
                    : "border-white/10 bg-white/[0.03] text-slate-300",
                ].join(" ")}
              >
                {coverage.availableCount}/4 live groups
              </span>
              {isPendingCurrentRoute ? (
                <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-100">
                  {pendingStatusLabel}
                </span>
              ) : null}
            </div>
          </div>

          <div className="rounded-[1.75rem] border border-cyan-400/[0.15] bg-cyan-400/[0.08] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-100">
              Shareable view
            </p>
            <p className="mt-4 text-2xl font-semibold tracking-tight text-white">
              /games/{canonicalGameId}
            </p>
            <p className="mt-4 max-w-sm text-sm leading-7 text-cyan-50/[0.85]">
              The canonical game identity stays in the path. `range` remains the only
              shareable view control and only clips the fixed 90-day history already
              served by the backend.
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
                  {option}
                </button>
              ))}
            </div>
            <p className="mt-4 text-xs uppercase tracking-[0.28em] text-cyan-100/80">
              {isPendingCurrentRoute
                ? `${pendingStatusLabel}...`
                : `${historyWindowLabel} view on top of a fixed 90-day backend window`}
            </p>
          </div>
        </div>

        {coverage.availableCount < 4 ? (
          <div className="mt-8">
            <DetailStateCard
              eyebrow="Coverage"
              title={
                coverage.availableCount === 0
                  ? "Live detail feeds are still catching up"
                  : "Part of the current detail shell is still pending"
              }
              description={coverageDescription}
            />
          </div>
        ) : null}
      </section>

      <SectionFrame
        eyebrow="Summary"
        title="Current operating snapshot"
        description="The detail page keeps the latest player, price, and review reads together so the product view stays useful before broader comparison, search, or additional filters exist."
        action={
          <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-300">
            {coverage.availableCount}/4 live groups
          </span>
        }
        delayMs={80}
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <MetricStrip
            label="Players now"
            value={formatCompactInteger(dashboard.ccu?.ccu)}
            hint={
              dashboard.ccu?.bucket_time
                ? `Latest player snapshot from ${formatDateTimeLabel(
                    dashboard.ccu.bucket_time,
                  )}`
                : "A live player snapshot has not been served for this title yet."
            }
            supporting={getCcuSupportingText(dashboard)}
          />
          <MetricStrip
            label="KR price now"
            value={formatCurrencyMinor(
              dashboard.price?.final_price_minor,
              dashboard.price?.currency_code,
            )}
            hint={
              dashboard.price?.bucket_time
                ? `Latest KR store row from ${formatDateTimeLabel(
                    dashboard.price.bucket_time,
                  )}`
                : "A current KR store snapshot is not available for this title yet."
            }
            supporting={getPriceSupportingText(dashboard)}
          />
          <MetricStrip
            label="Positive share"
            value={formatPercentRatio(dashboard.reviews?.positive_ratio)}
            hint={
              dashboard.reviews?.snapshot_date
                ? `Latest review snapshot on ${formatDateLabel(
                    dashboard.reviews.snapshot_date,
                  )}`
                : "A review summary has not been served for this title yet."
            }
            supporting={getReviewsSupportingText(dashboard)}
          />
        </div>
      </SectionFrame>

      <SectionFrame
        eyebrow="History"
        title="Recent player trend"
        description="The route keeps one recent player trend view on top of the existing fixed 90-day endpoint. `range` only decides how much of that already-served window is visible."
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
            eyebrow="Trend pending"
            title="Recent player history is not available yet"
            description={
              dashboard.ccu
                ? "The latest player snapshot exists for this title, but the fixed daily trend window has not populated yet."
                : "This title does not have recent player history in the current Steam-only detail slice yet."
            }
          />
        )}
      </SectionFrame>

      <SectionFrame
        eyebrow="Secondary Panels"
        title="Supporting price and review context"
        description="The supporting panels stay readable but slightly denser, so current store posture and review shape are clear without expanding the route into a larger analytics surface."
        delayMs={200}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              Price
            </p>
            <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
              Current KR store posture
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate-400">
              Latest served KR price row for this title, kept inside the current read-only
              boundary without region filters or broader store semantics.
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
                    label="Discount posture"
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
                    label="Store context"
                    value={`${dashboard.price.region} · ${dashboard.price.currency_code}`}
                    hint="The current detail boundary keeps price reads KR-centered and read-only."
                    supporting={`Bucket ${formatDateTimeLabel(dashboard.price.bucket_time)}`}
                  />
                </div>
              </>
            ) : (
              <div className="mt-6">
                <DetailStateCard
                  eyebrow="Price pending"
                  title="Current KR price is not available yet"
                  description="This title does not have a latest KR price row in the current slice yet, so the page keeps the space visible with a clear pending state."
                />
              </div>
            )}
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              Reviews
            </p>
            <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
              Latest review shape
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate-400">
              Latest served review summary for this title, kept compact but expressive so
              sentiment and volume remain readable without opening broader review tooling.
            </p>

            {dashboard.reviews ? (
              <>
                <div className="mt-6 rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-5">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div>
                      <p className="text-[0.68rem] uppercase tracking-[0.32em] text-slate-500">
                        Positive share
                      </p>
                      <p className="mt-3 text-3xl font-semibold tracking-tight text-white">
                        {formatPercentRatio(dashboard.reviews.positive_ratio)}
                      </p>
                    </div>
                    <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-100">
                      {dashboard.reviews.missing_flag
                        ? "Stable snapshot"
                        : formatSignedRatioPoints(dashboard.reviews.delta_positive_ratio)}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-slate-400">
                    Latest review snapshot from {formatDateLabel(dashboard.reviews.snapshot_date)}
                    .
                  </p>
                </div>

                <div className="mt-6 space-y-4">
                  <SecondaryStatRow
                    label="Total reviews"
                    value={formatInteger(dashboard.reviews.total_reviews)}
                    hint="All reviews captured in the latest served summary row."
                    supporting={`${formatInteger(
                      dashboard.reviews.total_positive,
                    )} positive · ${formatInteger(dashboard.reviews.total_negative)} negative`}
                  />
                  <SecondaryStatRow
                    label="Daily movement"
                    value={
                      dashboard.reviews.missing_flag
                        ? "No prior delta"
                        : formatSignedInteger(dashboard.reviews.delta_total_reviews)
                    }
                    hint="Day-over-day total review change when a prior snapshot exists."
                    supporting={
                      dashboard.reviews.missing_flag
                        ? "Previous-day review baseline is not available for this title yet."
                        : `${formatSignedRatioPoints(
                            dashboard.reviews.delta_positive_ratio,
                          )} sentiment shift`
                    }
                  />
                  <SecondaryStatRow
                    label="Snapshot context"
                    value={formatDateLabel(dashboard.reviews.snapshot_date)}
                    hint="The current detail boundary keeps reviews on the latest served daily summary."
                    supporting={
                      dashboard.reviews.missing_flag
                        ? "Current snapshot is visible even without a prior-day comparison."
                        : `${formatSignedInteger(
                            dashboard.reviews.delta_total_reviews,
                          )} review delta in the latest day`
                    }
                  />
                </div>
              </>
            ) : (
              <div className="mt-6">
                <DetailStateCard
                  eyebrow="Reviews pending"
                  title="Latest review summary is not available yet"
                  description="This title does not have a live review summary row in the current slice yet, so the panel stays visible with a clear pending state."
                />
              </div>
            )}
          </div>
        </div>
      </SectionFrame>
    </div>
  );
}
