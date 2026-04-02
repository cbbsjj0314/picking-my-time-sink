import { NavLink } from "react-router-dom";

const workstreamStatus = [
  { label: "Rankings", status: "Live" },
  { label: "CCU", status: "Queued" },
  { label: "Price", status: "Queued" },
  { label: "Reviews", status: "Queued" },
];

export function NavRail() {
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-[18.5rem] border-r border-white/10 bg-slate-950/[0.84] px-6 py-7 backdrop-blur lg:flex lg:flex-col">
      <div className="flex items-center gap-3">
        <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl border border-cyan-400/25 bg-cyan-400/10 text-lg font-semibold text-cyan-100 shadow-glow">
          P
        </div>
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.34em] text-cyan-300/70">
            Steam Dashboard
          </p>
          <h1 className="mt-2 text-lg font-semibold tracking-tight text-white">
            Picking My Time Sink
          </h1>
        </div>
      </div>

      <div className="mt-12 space-y-4">
        <p className="text-[0.68rem] uppercase tracking-[0.32em] text-slate-500">
          Navigate
        </p>
        <nav className="space-y-2">
          <NavLink
            to="/overview"
            className={({ isActive }) =>
              [
                "group flex items-center justify-between rounded-2xl border px-4 py-3 text-sm transition",
                isActive
                  ? "border-cyan-400/30 bg-cyan-400/10 text-white shadow-glow"
                  : "border-white/10 bg-white/[0.03] text-slate-300 hover:border-cyan-400/20 hover:bg-white/[0.05] hover:text-white",
              ].join(" ")
            }
          >
            {({ isActive }) => (
              <>
                <span className="font-medium">Overview</span>
                <span
                  className={[
                    "text-[0.66rem] uppercase tracking-[0.28em]",
                    isActive ? "text-cyan-200" : "text-slate-500",
                  ].join(" ")}
                >
                  Route
                </span>
              </>
            )}
          </NavLink>
        </nav>
      </div>

      <div className="mt-10 space-y-4">
        <p className="text-[0.68rem] uppercase tracking-[0.32em] text-slate-500">
          Current Slice
        </p>
        <div className="space-y-3">
          {workstreamStatus.map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between border-b border-white/[0.08] pb-3 text-sm"
            >
              <span className="text-slate-300">{item.label}</span>
              <span
                className={[
                  "rounded-full px-2.5 py-1 text-[0.65rem] uppercase tracking-[0.26em]",
                  item.status === "Live"
                    ? "bg-cyan-400/[0.12] text-cyan-200"
                    : "bg-white/[0.04] text-slate-500",
                ].join(" ")}
              >
                {item.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-auto rounded-3xl border border-white/10 bg-white/[0.03] p-5">
        <p className="text-[0.68rem] uppercase tracking-[0.32em] text-slate-500">
          Scope
        </p>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          Public read-only, Steam-only, KR-focused. Search, auth, and broader filters
          stay outside this slice.
        </p>
      </div>
    </aside>
  );
}
