import {
  Link,
  isRouteErrorResponse,
  useLocation,
  useRouteError,
} from "react-router-dom";

export function RouteErrorPage() {
  const error = useRouteError();
  const location = useLocation();
  const isGameDetailRoute = location.pathname.startsWith("/games/");

  let eyebrow = "Picking My Time Sink";
  let title = isGameDetailRoute ? "Selected game details unavailable" : "Route unavailable";
  let detail = isGameDetailRoute
    ? "The current Steam evidence view could not be loaded."
    : "The dashboard route could not be loaded.";

  if (isRouteErrorResponse(error)) {
    eyebrow = error.status === 404 ? "Not Found" : "Route error";
    title =
      error.status === 404 && isGameDetailRoute
        ? "Selected game details unavailable"
        : `${error.status} ${error.statusText}`;
    detail =
      typeof error.data === "string" && error.data.length > 0
        ? error.data
        : detail;
  } else if (error instanceof Error) {
    detail = error.message;
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="max-w-lg rounded-[2rem] border border-white/10 bg-white/[0.04] p-8 text-left shadow-[0_24px_70px_rgba(2,6,23,0.34)]">
        <p className="text-[0.68rem] uppercase tracking-[0.34em] text-cyan-300/80">
          {eyebrow}
        </p>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight text-white">{title}</h1>
        <p className="mt-4 text-sm leading-7 text-slate-400">{detail}</p>
        <p className="mt-3 text-sm leading-7 text-slate-500">
          Return to overview and reopen a mapped title inside the current Steam-first,
          read-only dashboard slice.
        </p>
        <Link
          to="/overview"
          className="mt-8 inline-flex items-center rounded-full border border-cyan-400/25 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/40 hover:text-white"
        >
          Return to overview
        </Link>
      </div>
    </div>
  );
}
