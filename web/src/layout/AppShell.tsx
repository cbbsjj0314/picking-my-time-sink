import { Outlet, useLocation } from "react-router-dom";

import { NavRail } from "../components/NavRail";

function getPageLabel(pathname: string): string {
  if (pathname.startsWith("/games/")) {
    return "Selected Game Details";
  }

  return "Overview";
}

export function AppShell() {
  const location = useLocation();
  const pageLabel = getPageLabel(location.pathname);

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-950 text-slate-100">
      <NavRail />
      <div className="relative min-h-screen lg:pl-[18.5rem]">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/[0.88] backdrop-blur lg:hidden">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-6">
            <div>
              <p className="text-[0.7rem] uppercase tracking-[0.34em] text-cyan-300/80">
                Picking My Time Sink
              </p>
              <p className="mt-2 text-lg font-semibold text-white">{pageLabel}</p>
            </div>
            <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-medium text-cyan-100">
              Steam-only
            </div>
          </div>
        </header>
        <main className="relative">
          <div className="mx-auto flex max-w-7xl flex-col gap-10 px-5 py-8 sm:px-6 lg:px-10 lg:py-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
