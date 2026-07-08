import { isRouteErrorResponse, Link, useRouteError } from "react-router";

import { buttonClass } from "@/components/ui";

export function RouteError() {
  const error = useRouteError();
  const notFound = isRouteErrorResponse(error) && error.status === 404;
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <h1 className="text-xl font-semibold">
        {notFound ? "Page not found" : "This page failed to load"}
      </h1>
      <p className="mt-2 max-w-sm text-ink-3">
        {notFound
          ? "The link may be old or mistyped."
          : "A new version may have been deployed. Reload to get it."}
      </p>
      <div className="mt-6 flex gap-2">
        <button className={buttonClass("primary")} onClick={() => window.location.reload()}>
          Reload
        </button>
        <Link to="/" className={buttonClass("secondary")}>
          Home
        </Link>
      </div>
    </main>
  );
}
