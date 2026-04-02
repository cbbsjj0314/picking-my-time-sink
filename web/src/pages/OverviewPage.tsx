import type { LoaderFunctionArgs } from "react-router-dom";
import { Link, useLoaderData } from "react-router-dom";

import { gamesApi, type GameLatestRanking } from "../api/games";
import { SectionFrame } from "../components/SectionFrame";
import { formatDateLabel, formatInteger } from "../lib/format";

type OverviewLoaderData = {
  rankings: GameLatestRanking[];
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
  return {
    rankings: await gamesApi.listLatestRankings({
      limit: 12,
      signal: request.signal,
    }),
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

export function OverviewPage() {
  const { rankings } = useLoaderData() as OverviewLoaderData;
  const mappedRows = rankings.filter((row) => row.canonical_game_id !== null).length;
  const snapshotDate = rankings[0]?.snapshot_date;

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
              The first slice keeps one live surface around the latest ranking list, then
              leaves CCU, price, and reviews visible as structurally ready sections for the
              next wire-up pass.
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
        description="This is the only fully wired overview group in the first slice. The section shows the current ranking snapshot, the mapping coverage to canonical games, and direct navigation into the minimal detail route."
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
        title="CCU structure is present, live wiring follows"
        description="The grouped overview reserves space for the latest CCU snapshot and a representative trend view, but this first slice leaves the section as a visible scaffold instead of adding another dense live panel."
        delayMs={140}
      >
        <PlaceholderSection
          endpoint="/games/ccu/latest"
          label="Next slice"
          title="Latest player-scale panel"
          description="Ready for a short leaderboard plus one representative history chart, without collapsing the overview back into a one-screen control wall."
          metricLabel="Planned highlight"
          metricValue="Current CCU + 90d trend"
          note="The detail route already reads the fixed 90-day history endpoint, so the overview can reuse the same shape in the next pass."
        />
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
