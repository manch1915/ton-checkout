import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import { useState } from "react";

import { Button, EmptyState, Notice, Skeleton, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { assetUnit, dateTime, shortAddress } from "@/lib/format";
import type { UnmatchedTransfer } from "@/lib/types";

import { PageHeader } from "./parts";

export function Review() {
  const transfers = useQuery({
    queryKey: ["dashboard", "unmatched"],
    queryFn: () => api.get<UnmatchedTransfer[]>("/api/dashboard/transfers/unmatched"),
  });
  return (
    <>
      <PageHeader
        title="Needs review"
        description="Payments that reached your wallet without a usable payment code. The money is yours either way; match each one to its order so the buyer gets what they paid for."
      />
      {transfers.isPending ? (
        <Skeleton className="h-40 w-full rounded-2xl" />
      ) : transfers.error ? (
        <Notice tone="danger" title="Could not load payments">
          {transfers.error.message}
        </Notice>
      ) : transfers.data.length === 0 ? (
        <div className="rounded-2xl border border-line bg-surface">
          <EmptyState title="Nothing to review">
            Every payment so far came with a valid code.
          </EmptyState>
        </div>
      ) : (
        <ul className="space-y-3">
          {transfers.data.map((t) => (
            <ReviewItem key={t.id} item={t} />
          ))}
        </ul>
      )}
    </>
  );
}

function ReviewItem({ item }: { item: UnmatchedTransfer }) {
  const client = useQueryClient();
  const [invoiceId, setInvoiceId] = useState("");
  const assign = useMutation({
    mutationFn: () =>
      api.post(`/api/dashboard/transfers/${item.id}/assign`, { invoice_id: invoiceId.trim() }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["dashboard"] }),
  });
  const t = item.transfer;
  return (
    <li className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold tabular">
            {t.amount} {assetUnit[t.asset]}
          </p>
          <p className="text-sm text-ink-3">
            {dateTime(t.occurred_at)}, from{" "}
            <span className="font-mono">{shortAddress(t.sender)}</span>
          </p>
          <p className="mt-2 text-sm">
            Comment:{" "}
            {t.comment ? (
              <q className="font-mono">{t.comment}</q>
            ) : (
              <span className="text-ink-3">none</span>
            )}
          </p>
          {item.note && <p className="text-sm text-warn">{item.note}</p>}
        </div>
        {t.explorer_url && (
          <a
            href={t.explorer_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm font-medium text-accent"
          >
            Tonviewer <ArrowUpRight className="size-4" aria-hidden />
          </a>
        )}
      </div>
      <form
        className="mt-4 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          assign.mutate();
        }}
      >
        <label className="flex-1">
          <span className="sr-only">Invoice ID</span>
          <input
            className={inputClass}
            required
            placeholder="Invoice ID, e.g. inv_8k2…"
            value={invoiceId}
            onChange={(e) => setInvoiceId(e.target.value)}
          />
        </label>
        <Button type="submit" variant="secondary" busy={assign.isPending}>
          Match to invoice
        </Button>
      </form>
      {assign.error && <p className="mt-2 text-sm text-danger">{assign.error.message}</p>}
    </li>
  );
}
