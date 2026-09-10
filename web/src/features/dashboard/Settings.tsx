import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Suspense, lazy, useState } from "react";

import { Button, CopyButton, Field, Notice, Skeleton, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";

import { PageHeader } from "./parts";
import { profileKey, useProfile } from "./session";

const WalletProofButton = lazy(() => import("./WalletProofButton"));

export function Settings() {
  const profile = useProfile();
  if (!profile.data) return <Skeleton className="h-96 w-full rounded-2xl" />;
  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-6 lg:grid-cols-2">
        <StoreForm profile={profile.data} />
        <WalletCard profile={profile.data} />
      </div>
    </>
  );
}

function StoreForm({ profile }: { profile: Profile }) {
  const client = useQueryClient();
  const [form, setForm] = useState({
    name: profile.name,
    accept_ton: profile.accept_ton,
    accept_usdt: profile.accept_usdt,
    accept_stars: profile.accept_stars,
    invoice_ttl_minutes: profile.invoice_ttl_minutes,
  });
  const save = useMutation({
    mutationFn: () => api.patch<Profile>("/api/dashboard/settings", form),
    onSuccess: (data) => client.setQueryData(profileKey, data),
  });
  const methods = [
    { key: "accept_ton", label: "Gram", hint: "Native coin of TON, sent from any TON wallet" },
    {
      key: "accept_usdt",
      label: "USDT on TON",
      hint: profile.usdt_master
        ? "Jetton, matched only from the configured master contract"
        : "Set USDT_JETTON_MASTER on the server to enable",
    },
    {
      key: "accept_stars",
      label: "Telegram Stars",
      hint: "Digital goods inside Telegram, through your bot",
    },
  ] as const;

  return (
    <form
      className="space-y-5 rounded-2xl border border-line bg-surface p-6"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h2 className="font-semibold">Store</h2>
      <Field label="Name shown on the payment page">
        <input
          className={inputClass}
          required
          maxLength={120}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </Field>
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Accepted payment methods</legend>
        <div className="space-y-2">
          {methods.map((m) => (
            <label
              key={m.key}
              className="flex items-start gap-3 rounded-lg border border-line px-3 py-2.5"
            >
              <input
                type="checkbox"
                className="mt-1 size-4 accent-[var(--accent)]"
                checked={form[m.key]}
                onChange={(e) => setForm({ ...form, [m.key]: e.target.checked })}
              />
              <span>
                <span className="block text-sm font-medium">{m.label}</span>
                <span className="block text-xs text-ink-3">{m.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <Field
        label="Invoice lifetime, minutes"
        hint="How long the locked rate holds. 15 to 60 minutes works for most stores."
      >
        <input
          className={inputClass}
          type="number"
          min={5}
          max={1440}
          value={form.invoice_ttl_minutes}
          onChange={(e) => setForm({ ...form, invoice_ttl_minutes: Number(e.target.value) })}
        />
      </Field>
      {save.error && (
        <Notice tone="danger" title="Not saved">
          {save.error.message}
        </Notice>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" busy={save.isPending}>
          Save changes
        </Button>
        {save.isSuccess && <span className="text-sm text-paid">Saved</span>}
      </div>
    </form>
  );
}

function WalletCard({ profile }: { profile: Profile }) {
  const client = useQueryClient();
  return (
    <section className="space-y-4 rounded-2xl border border-line bg-surface p-6">
      <h2 className="font-semibold">Payout wallet</h2>
      <p className="text-sm text-ink-2">
        Buyers pay straight to this address. TON Checkout never holds the money and has no keys to
        it.
      </p>
      <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2">
        <code className="min-w-0 flex-1 truncate font-mono text-sm">{profile.wallet}</code>
        <CopyButton value={profile.wallet} label="wallet address" />
      </div>
      {profile.demo ? (
        <p className="text-sm text-ink-3">
          The demo store keeps its wallet so the shared demo keeps working.
        </p>
      ) : (
        <>
          <Suspense
            fallback={
              <Button size="lg" variant="secondary" className="w-full" busy>
                Switch to another wallet
              </Button>
            }
          >
            <WalletProofButton
              label="Switch to another wallet"
              variant="secondary"
              errorTitle="Wallet not changed"
              onProof={async (body) => {
                const updated = await api.post<Profile>("/api/dashboard/wallet", body);
                client.setQueryData(profileKey, updated);
              }}
            />
          </Suspense>
          <p className="text-xs text-ink-3">
            You will sign a message in the new wallet to prove it is yours.
          </p>
        </>
      )}
      <dl className="space-y-1.5 border-t border-line pt-4 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-ink-3">Network</dt>
          <dd>TON {profile.network}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-ink-3">Chain data</dt>
          <dd>{profile.provider}</dd>
        </div>
        {profile.usdt_master && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-3">USDT master</dt>
            <dd className="truncate font-mono text-xs" title={profile.usdt_master}>
              {profile.usdt_master}
            </dd>
          </div>
        )}
        {profile.bot_username && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-3">Stars bot</dt>
            <dd>
              <a
                href={`https://t.me/${profile.bot_username}`}
                className="text-accent"
                target="_blank"
                rel="noreferrer"
              >
                @{profile.bot_username}
              </a>
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}
