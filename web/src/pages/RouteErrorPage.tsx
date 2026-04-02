import {
  Link,
  isRouteErrorResponse,
  useRouteError,
} from "react-router-dom";

export function RouteErrorPage() {
  const error = useRouteError();

  let title = "Route error";
  let detail = "The dashboard route could not be loaded.";

  if (isRouteErrorResponse(error)) {
    title = `${error.status} ${error.statusText}`;
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
          Picking My Time Sink
        </p>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight text-white">{title}</h1>
        <p className="mt-4 text-sm leading-7 text-slate-400">{detail}</p>
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
