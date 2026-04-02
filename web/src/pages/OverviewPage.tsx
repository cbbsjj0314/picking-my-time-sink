import type { LoaderFunctionArgs } from "react-router-dom";
import { Link, useLoaderData } from "react-router-dom";

import {
  gamesApi,
  type GameDaily90dCcu,
  type GameLatestCcu,
  type GameLatestRanking,
} from "../api/games";
import { SectionFrame } from "../components/SectionFrame";
import { SimpleHistoryChart } from "../components/SimpleHistoryChart";
import {
  formatCompactInteger,
  formatDateLabel,
  formatDateTimeLabel,
  formatInteger,
  formatSignedInteger,
  formatSignedPercent,
} from "../lib/format";

type OverviewLoaderData = {
  rankings: GameLatestRanking[];
  ccuRows: OverviewCcuRow[];
  representativeCcuRow: OverviewCcuRow | null;
  representativeCcuHistory: GameDaily90dCcu[];
};

type OverviewCcuRow = Omit<GameLatestCcu, "canonical_game_id"> & {
  canonical_game_id: number | null;
};

type StatBlockProps = {
  label: string;
  value: string;
  hint: string;
};

type PlaceholderSectionProps = {
  endpoint: string;
  label: string;
  title: string;
  description: string;
  metricLabel: string;
  metricValue: string;
  note: string;
};

export async function overviewLoader({
  request,
}: LoaderFunctionArgs): Promise<OverviewLoaderData> {
  const [rankings, ccuRows] = await Promise.all([
    gamesApi.listLatestRankings({
      limit: 12,
      signal: request.signal,
    }),
    gamesApi.listLatestCcu({
      limit: 6,
      signal: request.signal,
    }),
  ]);

  const representativeCcuRow =
    ccuRows.find((row) => row.canonical_game_id !== null) ?? null;
  const representativeCcuGameId = representativeCcuRow?.canonical_game_id ?? null;
  const representativeCcuHistory =
    representativeCcuGameId !== null
      ? await gamesApi.getGameCcuDaily90d(representativeCcuGameId, request.signal)
      : [];

  return {
    rankings,
    ccuRows,
    representativeCcuRow,
    representativeCcuHistory,
  };
}

function StatBlock({ label, value, hint }: StatBlockProps) {
  return (
    <div className="rounded-[1.75rem] border border-white/10 bg-white/[0.03] p-5">
      <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">{label}</p>
      <p className="mt-4 text-2xl font-semibold tracking-tight text-white">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-400">{hint}</p>
    </div>
  );
}

function PlaceholderSection({
  endpoint,
  label,
  title,
  description,
  metricLabel,
  metricValue,
  note,
}: PlaceholderSectionProps) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
      <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
        <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
          {endpoint}
        </p>
        <div className="mt-5 space-y-3">
          <div className="inline-flex rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-400">
            {label}
          </div>
          <h3 className="text-xl font-semibold tracking-tight text-white">{title}</h3>
          <p className="text-sm leading-7 text-slate-400">{description}</p>
        </div>
        <div className="mt-8 border-t border-white/10 pt-5">
          <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">
            {metricLabel}
          </p>
          <p className="mt-3 text-2xl font-semibold text-white">{metricValue}</p>
          <p className="mt-3 text-sm leading-6 text-slate-400">{note}</p>
        </div>
      </div>
      <div className="rounded-[2rem] border border-dashed border-white/[0.12] bg-slate-900/50 p-6">
        <div className="flex h-full min-h-[18rem] flex-col justify-between rounded-[1.5rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,33,0.62),rgba(4,8,22,0.92))] p-5">
          <div className="flex items-center justify-between text-sm text-slate-400">
            <span>Representative view</span>
            <span className="rounded-full border border-cyan-400/[0.15] bg-cyan-400/[0.08] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-cyan-200">
              Ready
            </span>
          </div>
          <div className="mt-8 space-y-5">
            <div className="h-3 w-28 rounded-full bg-white/10" />
            <div className="grid grid-cols-12 gap-2">
              {[14, 18, 16, 24, 20, 26, 19, 28, 22, 30, 26, 34].map((height, index) => (
                <div
                  key={`${label}-${index}`}
                  className="rounded-full bg-cyan-400/20"
                  style={{ height: `${height * 4}px` }}
                />
              ))}
            </div>
            <div className="grid gap-2">
              <div className="h-2 rounded-full bg-white/10" />
              <div className="h-2 w-11/12 rounded-full bg-white/[0.08]" />
              <div className="h-2 w-2/3 rounded-full bg-white/[0.08]" />
            </div>
          </div>
          <p className="mt-8 text-sm leading-6 text-slate-500">
            Structure is in place so the next slice can replace this shell with live API
            wiring without changing the overview rhythm.
          </p>
        </div>
      </div>
    </div>
  );
}

function RankingRow({ row }: { row: GameLatestRanking }) {
  const title = row.canonical_name ?? `Steam app ${row.steam_appid}`;
  const destination = row.canonical_game_id
    ? `/games/${row.canonical_game_id}?range=90d`
    : undefined;
  const rowContent = (
    <div className="group flex items-center gap-4 px-4 py-4 transition sm:px-6">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-cyan-400/[0.18] bg-cyan-400/10 text-sm font-semibold text-cyan-100">
        #{row.rank_position}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-3">
          <p className="truncate text-base font-medium text-white">{title}</p>
          <span
            className={[
              "rounded-full px-2.5 py-1 text-[0.66rem] uppercase tracking-[0.26em]",
              row.canonical_game_id
                ? "bg-cyan-400/[0.12] text-cyan-200"
                : "bg-white/[0.05] text-slate-500",
            ].join(" ")}
          >
            {row.canonical_game_id ? "Mapped" : "Pending"}
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-400">
          Steam App ID {row.steam_appid}
          {row.canonical_game_id ? ` · Canonical ${row.canonical_game_id}` : " · Canonical mapping pending"}
        </p>
      </div>
      <div className="hidden text-right sm:block">
        <p className="text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">Action</p>
        <p className="mt-2 text-sm text-cyan-200">
          {row.canonical_game_id ? "Open detail" : "Hold"}
        </p>
      </div>
    </div>
  );

  if (!destination) {
    return (
      <li className="border-b border-white/[0.08] last:border-b-0">
        <div>{rowContent}</div>
      </li>
    );
  }

  return (
    <li className="border-b border-white/[0.08] last:border-b-0">
      <Link to={destination} className="block hover:bg-white/[0.03]">
        {rowContent}
      </Link>
    </li>
  );
}

function getGameDetailRoute(canonicalGameId: number | null): string | undefined {
  return canonicalGameId !== null ? `/games/${canonicalGameId}?range=90d` : undefined;
}

function CcuRow({
  row,
  rank,
  isRepresentative,
}: {
  row: OverviewCcuRow;
  rank: number;
  isRepresentative: boolean;
}) {
  const destination = getGameDetailRoute(row.canonical_game_id);
  const content = (
    <div className="group flex items-center gap-4 px-4 py-4 transition sm:px-5">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-cyan-400/[0.18] bg-cyan-400/10 text-sm font-semibold text-cyan-100">
        {rank}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <p className="truncate text-base font-medium text-white">{row.canonical_name}</p>
          <span
            className={[
              "rounded-full px-2.5 py-1 text-[0.66rem] uppercase tracking-[0.26em]",
              destination
                ? "bg-cyan-400/[0.12] text-cyan-200"
                : "bg-white/[0.05] text-slate-500",
            ].join(" ")}
          >
            {destination ? "Mapped" : "Pending"}
          </span>
          {isRepresentative ? (
            <span className="rounded-full border border-cyan-400/[0.16] bg-cyan-400/[0.08] px-2.5 py-1 text-[0.66rem] uppercase tracking-[0.26em] text-cyan-100">
              History
            </span>
          ) : null}
        </div>
        <p className="mt-2 text-sm text-slate-400">
          {row.bucket_time
            ? `Bucket ${formatDateTimeLabel(row.bucket_time)}`
            : "Latest bucket is pending"}
        </p>
      </div>
      <div className="text-right">
        <p className="text-base font-semibold text-white">{formatCompactInteger(row.ccu)}</p>
        <p className="mt-2 text-sm text-cyan-200">
          {row.missing_flag
            ? "No prior delta"
            : `${formatSignedInteger(row.delta_ccu_abs)} · ${formatSignedPercent(
                row.delta_ccu_pct,
              )}`}
        </p>
      </div>
    </div>
  );

  return (
    <li className="border-b border-white/[0.08] last:border-b-0">
      {destination ? (
        <Link to={destination} className="block hover:bg-white/[0.03]">
          {content}
        </Link>
      ) : (
        <div>{content}</div>
      )}
    </li>
  );
}

export function OverviewPage() {
  const { rankings, ccuRows, representativeCcuRow, representativeCcuHistory } =
    useLoaderData() as OverviewLoaderData;
  const mappedRows = rankings.filter((row) => row.canonical_game_id !== null).length;
  const snapshotDate = rankings[0]?.snapshot_date;
  const representativeDestination = getGameDetailRoute(
    representativeCcuRow?.canonical_game_id ?? null,
  );
  const ccuSnapshotTime = ccuRows[0]?.bucket_time;
  const ccuRowsWithDelta = ccuRows.filter((row) => !row.missing_flag).length;

  return (
    <div className="space-y-12">
      <section className="animate-section-enter rounded-[2rem] border border-white/10 bg-white/[0.035] p-6 shadow-[0_24px_70px_rgba(2,6,23,0.34)] md:p-8">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(17rem,0.8fr)] lg:items-end">
          <div>
            <p className="text-[0.68rem] uppercase tracking-[0.36em] text-cyan-300/80">
              Overview
            </p>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
              Steam-only monitoring, shaped as a calm grouped scroll instead of a single
              dense board.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-400">
              The current thin slice keeps ranking and CCU live inside the same grouped
              rhythm, then leaves price and reviews visible as structurally ready sections
              for the next wire-up pass.
            </p>
          </div>
          <div className="rounded-[1.75rem] border border-cyan-400/[0.15] bg-cyan-400/[0.08] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-100">
              Current baseline
            </p>
            <div className="mt-5 space-y-3 text-sm leading-7 text-cyan-50/[0.85]">
              <p>Public read-only surface on top of the existing FastAPI API.</p>
              <p>Steam-only, KR-focused, no auth, no search, no provider toggles.</p>
              <p>Route identity stays in the path. Shareable page state stays in the URL.</p>
            </div>
          </div>
        </div>
      </section>

      <SectionFrame
        id="ranking"
        eyebrow="Ranking"
        title="Latest KR top-selling list"
        description="Ranking remains the first anchored live group. The section shows the current ranking snapshot, the mapping coverage to canonical games, and direct navigation into the minimal detail route."
        delayMs={80}
      >
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <StatBlock
            label="Snapshot date"
            value={formatDateLabel(snapshotDate)}
            hint="Latest fixed KR top-selling serving snapshot."
          />
          <StatBlock
            label="Visible rows"
            value={formatInteger(rankings.length)}
            hint="Overview keeps the list short so it stays scannable."
          />
          <StatBlock
            label="Mapped rows"
            value={formatInteger(mappedRows)}
            hint="Only mapped rows expose the game detail route in this slice."
          />
        </div>

        <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-slate-900/50">
          <ul>
            {rankings.map((row) => (
              <RankingRow
                key={`${row.snapshot_date}-${row.rank_position}-${row.steam_appid}`}
                row={row}
              />
            ))}
          </ul>
        </div>
      </SectionFrame>

      <SectionFrame
        id="player-trend"
        eyebrow="Player Trend"
        title="Latest CCU snapshot with one representative history"
        description="This pass reuses the existing latest CCU list plus one fixed 90-day history read, so the overview gains live player-scale context without collapsing back into a dense one-screen board."
        delayMs={140}
      >
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <StatBlock
            label="Snapshot bucket"
            value={formatDateTimeLabel(ccuSnapshotTime)}
            hint="Latest fixed CCU serving row already exposed by the backend."
          />
          <StatBlock
            label="Visible rows"
            value={formatInteger(ccuRows.length)}
            hint="The overview keeps the CCU list short so the section stays scannable."
          />
          <StatBlock
            label="Rows with delta"
            value={formatInteger(ccuRowsWithDelta)}
            hint="Rows without a prior-day match stay visible but show a graceful delta fallback."
          />
        </div>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
          <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
            <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
              /games/ccu/latest
            </p>
            <div className="mt-5 space-y-3">
              <div className="inline-flex rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[0.68rem] uppercase tracking-[0.28em] text-slate-400">
                Live now
              </div>
              <h3 className="text-xl font-semibold tracking-tight text-white">
                Latest player-scale rows
              </h3>
              <p className="text-sm leading-7 text-slate-400">
                The list stays compact and detail-linked where a canonical route exists.
                It intentionally stops short of generalized filtering or a second large
                leaderboard.
              </p>
            </div>

            <div className="mt-8 overflow-hidden rounded-[1.5rem] border border-white/10 bg-slate-950/40">
              {ccuRows.length > 0 ? (
                <ul>
                  {ccuRows.map((row, index) => (
                    <CcuRow
                      key={`${row.canonical_game_id ?? row.canonical_name}-${row.bucket_time}`}
                      row={row}
                      rank={index + 1}
                      isRepresentative={
                        representativeCcuRow?.canonical_game_id === row.canonical_game_id
                      }
                    />
                  ))}
                </ul>
              ) : (
                <div className="flex min-h-[18rem] items-center justify-center px-6 py-10 text-sm text-slate-500">
                  Latest CCU rows are not available yet.
                </div>
              )}
            </div>
          </div>

          <div className="space-y-5">
            <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-[0.68rem] uppercase tracking-[0.32em] text-cyan-300/70">
                    Representative view
                  </p>
                  <h3 className="mt-4 text-xl font-semibold tracking-tight text-white">
                    {representativeCcuRow?.canonical_name ?? "Representative history pending"}
                  </h3>
                  <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
                    {representativeCcuRow
                      ? "One mapped game reuses the fixed 90-day history endpoint so the overview can show trend context without growing into a full comparison surface."
                      : "No mapped CCU row is available yet, so the representative chart stays in a graceful empty state."}
                  </p>
                </div>
                {representativeDestination ? (
                  <Link
                    to={representativeDestination}
                    className="inline-flex h-fit items-center rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-4 py-2 text-sm text-cyan-100 transition hover:border-cyan-300/35 hover:bg-cyan-300/[0.14]"
                  >
                    Open detail
                  </Link>
                ) : (
                  <span className="inline-flex h-fit items-center rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-sm text-slate-400">
                    Mapping pending
                  </span>
                )}
              </div>

              {representativeCcuRow ? (
                <div className="mt-6 grid gap-4 sm:grid-cols-3">
                  <StatBlock
                    label="Latest CCU"
                    value={formatCompactInteger(representativeCcuRow.ccu)}
                    hint="Current latest CCU value for the representative game."
                  />
                  <StatBlock
                    label="Delta"
                    value={
                      representativeCcuRow.missing_flag
                        ? "No prior delta"
                        : formatSignedInteger(representativeCcuRow.delta_ccu_abs)
                    }
                    hint={
                      representativeCcuRow.missing_flag
                        ? "Previous-day same-bucket baseline is missing for this row."
                        : formatSignedPercent(representativeCcuRow.delta_ccu_pct)
                    }
                  />
                  <StatBlock
                    label="History points"
                    value={formatInteger(representativeCcuHistory.length)}
                    hint="Fixed recent 90-day window from the existing detail endpoint."
                  />
                </div>
              ) : null}
            </div>

            <SimpleHistoryChart data={representativeCcuHistory} />
          </div>
        </div>
      </SectionFrame>

      <SectionFrame
        id="price"
        eyebrow="Price"
        title="Price and discount block"
        description="Price stays visible in the overview order, but the first thin slice keeps it as a placeholder shell so the ranking path can land cleanly first."
        delayMs={200}
      >
        <PlaceholderSection
          endpoint="/games/price/latest"
          label="Queued"
          title="KR price snapshot"
          description="The layout is already aligned for current price, discount percent, and a small value-led list without introducing generalized region filters."
          metricLabel="Planned highlight"
          metricValue="Current price + discount"
          note="The underlying client helper is present so this section can flip to live data in a focused follow-up."
        />
      </SectionFrame>

      <SectionFrame
        id="reviews"
        eyebrow="Reviews"
        title="Reviews and sentiment block"
        description="Reviews is intentionally last in the current overview rhythm: visible enough to anchor the roadmap, but small enough to keep the first delivery focused."
        delayMs={260}
      >
        <PlaceholderSection
          endpoint="/games/reviews/latest"
          label="Queued"
          title="Latest review momentum"
          description="Reserved for total review volume, positive ratio, and a compact movement summary once the second data group is connected."
          metricLabel="Planned highlight"
          metricValue="Review total + ratio"
          note="No generalized sentiment tooling lands here yet. The shell only preserves the information architecture."
        />
      </SectionFrame>
    </div>
  );
}
