import { Link } from "react-router";

import { buttonClass } from "@/components/ui";

export function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="mt-2 text-ink-3">The link may be old or mistyped.</p>
      <Link to="/" className={buttonClass("secondary", "md", "mt-6")}>
        Go to the home page
      </Link>
    </main>
  );
}
