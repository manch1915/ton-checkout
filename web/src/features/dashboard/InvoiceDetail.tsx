import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router";

import { AssetTag, Button, CopyButton, Notice, Skeleton, StatusBadge, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { assetUnit, dateTime, money, shortAddress } from "@/lib/format";
import type { EventType, InvoiceDetail } from "@/lib/types";

import { DeliveryState } from "./Webhooks";

const EVENT_TEXT: Record<EventType, string> = {
  "invoice.created": "Invoice created",
  "invoice.partially_paid": "Partial payment received",
  "invoice.paid": "Paid in full",
  "invoice.expired": "Expired",
  "invoice.canceled": "Canceled",
  "payment.unmatched": "Payment could not be matched",
};

const SOURCE_TEXT = { chain: "On-chain", sandbox: "Simulated", stars: "Telegram Stars" } as const;

export function InvoiceDetailPage() {
  const { invoiceId = "" } = useParams();
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: ["dashboard", "invoice", invoiceId],
    queryFn: () => api.get<InvoiceDetail>(`/api/dashboard/invoices/${invoiceId}`),
    refetchInterval: (q) => {
      const status = q.state.data?.invoice.status;
      return status === "pending" || status === "partially_paid" ? 5000 : false;
    },
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["dashboard"] });
  const cancel = useMutation({
    mutationFn: () => api.post(`/api/dashboard/invoices/${invoiceId}/cancel`),
    onSuccess: refresh,
  });
  const rescan = useMutation({
    mutationFn: () => api.post<{ scanned: number }>(`/api/dashboard/invoices/${invoiceId}/rescan`),
    onSuccess: refresh,
  });

  if (detail.isPending) return <Skeleton className="h-96 w-full rounded-2xl" />;
  if (detail.error) {
    return (
      <Notice tone="danger" title="Invoice not found">
        {detail.error.message}
      </Notice>
    );
  }
  const { invoice, transfers, events, deliveries } = detail.data;
  const open = invoice.status === "pending" || invoice.status === "partially_paid";

  return (
    <>
      <Link
        to="/dashboard/invoices"
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink-3 hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden /> Invoices
      </Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{invoice.description}</h1>
            <StatusBadge status={invoice.status} />
          </div>
          <p className="mt-1 text-ink-2">
            {money(invoice.fiat_amount, invoice.fiat_currency)}
            {invoice.order_id && <>, order {invoice.order_id}</>}
            {invoice.mode === "test" && ", test invoice"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={invoice.pay_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-line bg-surface px-4 font-medium hover:border-line-strong"
          >
            Payment page <ArrowUpRight className="size-4" aria-hidden />
          </a>
          <Button
            variant="secondary"
            onClick={() => rescan.mutate()}
            busy={rescan.isPending}
            icon={<RefreshCw className="size-4" />}
          >
            Check the chain again
          </Button>
          {open && (
            <Button variant="danger" onClick={() => cancel.mutate()} busy={cancel.isPending}>
              Cancel invoice
            </Button>
          )}
        </div>
      </div>
      {rescan.data && (
        <div className="mb-4">
          <Notice tone="info" title={`Looked at ${rescan.data.scanned} incoming transfers`}>
            Payments seen before are skipped, so running this twice never counts money twice.
          </Notice>
        </div>
      )}
      {(cancel.error || rescan.error) && (
        <div className="mb-4">
          <Notice tone="danger" title="Action failed">
            {(cancel.error ?? rescan.error)?.message}
          </Notice>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-line bg-surface">
            <h2 className="border-b border-line px-5 py-3 font-semibold">Payments</h2>
            {transfers.length === 0 ? (
              <p className="px-5 py-6 text-sm text-ink-3">
                Nothing has arrived for this invoice yet.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {transfers.map((t) => (
                  <li
                    key={t.tx_hash}
                    className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm"
                  >
                    <div>
                      <p className="font-medium tabular">
                        {t.amount} {assetUnit[t.asset]}
                      </p>
                      <p className="text-ink-3">
                        {SOURCE_TEXT[t.source]}, {dateTime(t.occurred_at)}
                        {t.source === "chain" && <>, from {shortAddress(t.sender)}</>}
                      </p>
                    </div>
                    {t.explorer_url && (
                      <a
                        href={t.explorer_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-medium text-accent hover:text-accent-strong"
                      >
                        Tonviewer <ArrowUpRight className="size-4" aria-hidden />
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-2xl border border-line bg-surface">
            <h2 className="border-b border-line px-5 py-3 font-semibold">Webhook deliveries</h2>
            {deliveries.length === 0 ? (
              <p className="px-5 py-6 text-sm text-ink-3">
                No endpoints were set up when these events happened.{" "}
                <Link to="/dashboard/webhooks" className="font-medium text-accent">
                  Add one
                </Link>
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {deliveries.map((d) => (
                  <li
                    key={d.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="font-mono text-xs">{d.event_type}</p>
                      <p className="truncate text-ink-3">{d.endpoint_url}</p>
                    </div>
                    <Link to={`/dashboard/webhooks?delivery=${d.id}`}>
                      <DeliveryState delivery={d} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="space-y-6">
          <section className="rounded-2xl border border-line bg-surface p-5 text-sm">
            <h2 className="font-semibold">Details</h2>
            <dl className="mt-3 space-y-2.5">
              <Row label="Payment code">
                <span className="font-mono">{invoice.reference}</span>
                <CopyButton value={invoice.reference} label="payment code" />
              </Row>
              <Row label="Invoice ID">
                <span className="font-mono text-xs">{invoice.id}</span>
                <CopyButton value={invoice.id} label="invoice ID" />
              </Row>
              <Row label="Quoted">
                <span className="flex flex-col items-end">
                  {invoice.quotes.map((q) => (
                    <span key={q.asset} className="tabular">
                      {q.amount} {assetUnit[q.asset]}
                    </span>
                  ))}
                </span>
              </Row>
              {invoice.asset && (
                <Row label="Paid with">
                  <AssetTag asset={invoice.asset} />
                </Row>
              )}
              <Row label="Received">
                <span className="tabular">{invoice.received}</span>
              </Row>
              {Number(invoice.overpaid) > 0 && (
                <Row label="Overpaid">
                  <span className="text-warn tabular">{invoice.overpaid}</span>
                </Row>
              )}
              {invoice.late && (
                <Row label="Late">
                  <span className="text-warn">Paid after expiry</span>
                </Row>
              )}
              <Row label="Expires">{dateTime(invoice.expires_at)}</Row>
              <Row label="Wallet">
                <span className="font-mono text-xs" title={invoice.recipient}>
                  {shortAddress(invoice.recipient)}
                </span>
              </Row>
            </dl>
          </section>

          <section className="rounded-2xl border border-line bg-surface p-5 text-sm">
            <h2 className="font-semibold">Timeline</h2>
            <ol className="mt-3 space-y-3">
              {events.map((e, i) => (
                <li key={e.id} className="relative flex gap-3">
                  <span
                    className={cx(
                      "mt-1.5 size-2 shrink-0 rounded-full",
                      e.type === "invoice.paid"
                        ? "bg-paid"
                        : i === events.length - 1
                          ? "bg-accent"
                          : "bg-line-strong",
                    )}
                    aria-hidden
                  />
                  <div>
                    <p className="font-medium">{EVENT_TEXT[e.type]}</p>
                    <p className="text-ink-3">{dateTime(e.created_at)}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-3">{label}</dt>
      <dd className="flex items-center gap-1 text-right">{children}</dd>
    </div>
  );
}
