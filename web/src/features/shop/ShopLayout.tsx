import { Music2 } from "lucide-react";
import { Link, Outlet } from "react-router";

import { ThemeToggle } from "@/components/ui";
import { isTelegram } from "@/lib/telegram";

export function ShopLayout() {
  const inTelegram = isTelegram();
  return (
    <div className="min-h-dvh">
      {!inTelegram && (
        <div className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2 text-sm">
            <span className="text-ink-3">Demo store on TON testnet. Payments use test coins.</span>
            <Link to="/" className="shrink-0 font-medium text-accent hover:text-accent-strong">
              About TON Checkout
            </Link>
          </div>
        </div>
      )}
      <header className="mx-auto flex max-w-3xl items-center justify-between px-4 pt-6 pb-2">
        <Link to="/shop" className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-full bg-ink text-bg">
            <Music2 className="size-4" aria-hidden />
          </span>
          <span>
            <span className="block leading-tight font-semibold">Cellar Nine</span>
            <span className="block text-xs text-ink-3">Live music club, Yerevan</span>
          </span>
        </Link>
        {!inTelegram && <ThemeToggle />}
      </header>
      <Outlet />
    </div>
  );
}
