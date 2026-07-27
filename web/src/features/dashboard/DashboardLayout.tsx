import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Code2,
  FileText,
  Inbox,
  LayoutGrid,
  LogOut,
  Menu,
  Settings as SettingsIcon,
  Webhook,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router";

import { Spinner, ThemeToggle, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { shortAddress } from "@/lib/format";
import type { Stats } from "@/lib/types";

import { useProfile } from "./session";

const NAV = [
  { to: "/dashboard", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/dashboard/invoices", label: "Invoices", icon: FileText },
  { to: "/dashboard/review", label: "Needs review", icon: Inbox, badge: true },
  { to: "/dashboard/webhooks", label: "Webhooks", icon: Webhook },
  { to: "/dashboard/developers", label: "API keys", icon: Code2 },
  { to: "/dashboard/settings", label: "Settings", icon: SettingsIcon },
];

export function DashboardLayout() {
  const profile = useProfile();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.title = "Dashboard | TON Checkout";
  }, []);

  if (profile.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label="Loading your store" />
      </div>
    );
  }
  if (profile.error instanceof ApiError && profile.error.status === 401) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (profile.error || !profile.data) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-6 text-center text-ink-2">
        The dashboard could not load. Check your connection and reload.
      </div>
    );
  }

  const me = profile.data;
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_1fr]">
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-line bg-surface transition-transform lg:static lg:w-auto lg:translate-x-0",
          menuOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Dashboard"
      >
        <div className="flex h-16 items-center justify-between px-5">
          <Link to="/" className="font-semibold">
            TON Checkout
          </Link>
          <button className="lg:hidden" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>
        <div className="mx-3 mb-4 rounded-xl bg-surface-2 px-3 py-2.5">
          <p className="truncate text-sm font-medium">{me.name}</p>
          <p className="truncate font-mono text-xs text-ink-3" title={me.wallet}>
            {shortAddress(me.wallet, 6)}
          </p>
        </div>
        <Nav onNavigate={() => setMenuOpen(false)} />
        <div className="mt-auto border-t border-line p-3">
          <SignOut />
        </div>
      </aside>
      {menuOpen && (
        <button
          className="fixed inset-0 z-20 bg-ink/30 lg:hidden"
          aria-label="Close menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur sm:px-6">
          <button className="lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          {me.demo && (
            <span className="hidden text-sm text-ink-3 sm:inline">
              Demo store, shared with other visitors
            </span>
          )}
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink-2">
            <span className="size-1.5 rounded-full bg-warn" aria-hidden />
            TON {me.network}
          </span>
          <ThemeToggle />
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Nav({ onNavigate }: { onNavigate: () => void }) {
  const stats = useQuery({
    queryKey: ["dashboard", "stats", 14, "all"],
    queryFn: () => api.get<Stats>("/api/dashboard/stats?days=14"),
  });
  const pending = stats.data?.unmatched_transfers ?? 0;
  return (
    <nav className="flex flex-col gap-0.5 px-3">
      {NAV.map(({ to, label, icon: Icon, end, badge }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cx(
              "flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm font-medium",
              isActive
                ? "bg-accent-soft text-accent-strong"
                : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )
          }
        >
          <Icon className="size-4" aria-hidden />
          {label}
          {badge && pending > 0 && (
            <span className="ml-auto rounded-full bg-warn-soft px-1.5 text-xs text-warn tabular">
              {pending}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function SignOut() {
  const client = useQueryClient();
  const navigate = useNavigate();
  return (
    <button
      className="flex h-9 w-full items-center gap-2.5 rounded-lg px-3 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
      onClick={async () => {
        await api.post("/api/auth/logout");
        client.clear();
        navigate("/login");
      }}
    >
      <LogOut className="size-4" aria-hidden />
      Sign out
    </button>
  );
}
