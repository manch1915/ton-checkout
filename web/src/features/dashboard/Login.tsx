import { useQueryClient } from "@tanstack/react-query";
import { Store, Wallet } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { Button, Notice, ThemeToggle } from "@/components/ui";
import { api } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";

import { profileKey } from "./session";
import { useWalletProof } from "./useWalletProof";

export function Login() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [demoBusy, setDemoBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enter = async () => {
    await client.invalidateQueries({ queryKey: profileKey });
    navigate("/dashboard");
  };
  const wallet = useWalletProof(async (body) => {
    await api.post<SessionInfo>("/api/auth/ton-proof/verify", body);
    await enter();
  });

  const demo = async () => {
    setDemoBusy(true);
    setError(null);
    try {
      await api.post<SessionInfo>("/api/auth/demo");
      await enter();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The demo store is not available right now.");
      setDemoBusy(false);
    }
  };

  return (
    <main className="flex min-h-dvh flex-col px-4">
      <div className="mx-auto flex w-full max-w-sm items-center justify-between pt-6">
        <Link to="/" className="font-semibold">
          TON Checkout
        </Link>
        <ThemeToggle />
      </div>
      <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center pb-24">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to your store</h1>
        <p className="mt-2 text-ink-2">
          Your wallet is your account. Payments land in the wallet you sign in with, and no password
          is stored anywhere.
        </p>
        <div className="mt-8 space-y-3">
          <Button
            size="lg"
            className="w-full"
            onClick={wallet.start}
            busy={wallet.busy}
            icon={<Wallet className="size-4" />}
          >
            Sign in with a TON wallet
          </Button>
          <Button
            size="lg"
            variant="secondary"
            className="w-full"
            onClick={demo}
            busy={demoBusy}
            icon={<Store className="size-4" />}
          >
            Open the demo store
          </Button>
        </div>
        <p className="mt-3 text-sm text-ink-3">
          The demo store has two weeks of orders and is shared by everyone who opens it.
        </p>
        {(wallet.error || error) && (
          <div className="mt-6">
            <Notice tone="danger" title="Could not sign in">
              {wallet.error ?? error}
            </Notice>
          </div>
        )}
      </div>
    </main>
  );
}
