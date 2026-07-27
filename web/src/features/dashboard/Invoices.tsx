import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Button, CopyButton, Field, Notice, buttonClass, inputClass } from "@/components/ui";
import { api, query } from "@/lib/api";
import type { Invoice, Page } from "@/lib/types";

import { InvoiceRows } from "./Overview";
import { PageHeader, selectClass } from "./parts";

const PAGE_SIZE = 25;
const FILTERS = ["status", "asset", "mode", "q", "from", "to"] as const;

export function Invoices() {
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const offset = Number(params.get("offset") ?? 0);
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? undefined]));

  const invoices = useQuery({
    queryKey: ["dashboard", "invoices", filters, offset],
    queryFn: () =>
      api.get<Page<Invoice>>(
        `/api/dashboard/invoices${query({ ...filters, limit: PAGE_SIZE, offset })}`,
      ),
    placeholderData: (previous) => previous,
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("offset");
    setParams(next, { replace: true });
  };
  const hasFilters = FILTERS.some((k) => params.get(k));
  const total = invoices.data?.total ?? 0;

  return (
    <>
      <PageHeader
        title="Invoices"
        description="Every payment request your store created, with its status on the chain."
        actions={
          <>
            <a
              href={`/api/dashboard/invoices/export.csv${query(filters)}`}
              className={buttonClass("secondary")}
              download
            >
              <Download className="size-4" aria-hidden />
              Export CSV
            </a>
            <Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
              New invoice
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SearchBox value={params.get("q") ?? ""} onChange={(v) => set("q", v)} />
        <select
          className={selectClass}
          aria-label="Status"
          value={params.get("status") ?? ""}
          onChange={(e) => set("status", e.target.value)}
        >
          <option value="">Any status</option>
          <option value="pending">Waiting for payment</option>
          <option value="partially_paid">Partly paid</option>
          <option value="paid">Paid</option>
          <option value="expired">Expired</option>
          <option value="canceled">Canceled</option>
        </select>
        <select
          className={selectClass}
          aria-label="Paid with"
          value={params.get("asset") ?? ""}
          onChange={(e) => set("asset", e.target.value)}
        >
          <option value="">Any method</option>
          <option value="TON">Gram</option>
          <option value="USDT">USDT</option>
          <option value="XTR">Stars</option>
        </select>
        <select
          className={selectClass}
          aria-label="Mode"
          value={params.get("mode") ?? ""}
          onChange={(e) => set("mode", e.target.value)}
        >
          <option value="">Test and live</option>
          <option value="test">Test only</option>
          <option value="live">Live only</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-ink-3">
          From
          <input
            type="date"
            className={selectClass}
            value={params.get("from") ?? ""}
            onChange={(e) => set("from", e.target.value)}
          />
        </label>
        <label className="flex items-center gap-1.5 text-sm text-ink-3">
          to
          <input
            type="date"
            className={selectClass}
            value={params.get("to") ?? ""}
            onChange={(e) => set("to", e.target.value)}
          />
        </label>
        {hasFilters && (
          <button
            className="inline-flex items-center gap-1 text-sm font-medium text-ink-2 hover:text-ink"
            onClick={() => setParams({})}
          >
            <X className="size-4" aria-hidden /> Clear
          </button>
        )}
      </div>

      {invoices.error ? (
        <Notice tone="danger" title="Invoices could not load">
          {invoices.error.message}
        </Notice>
      ) : (
        <InvoiceRows data={invoices.data?.items} loading={invoices.isPending} />
      )}

      {total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm text-ink-3">
          <span className="tabular">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={offset === 0}
              onClick={() => set("offset", String(Math.max(0, offset - PAGE_SIZE)))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set("offset", String(offset + PAGE_SIZE));
                setParams(next);
              }}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {creating && <NewInvoiceDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function SearchBox({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (text !== value) onChange(text);
    }, 300);
    return () => window.clearTimeout(id);
  }, [text, value, onChange]);
  return (
    <label className="relative min-w-56 flex-1 sm:flex-none">
      <span className="sr-only">Search invoices</span>
      <Search
        className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-3"
        aria-hidden
      />
      <input
        className={`${selectClass} w-full pl-8`}
        placeholder="Order, code or invoice ID"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </label>
  );
}

function NewInvoiceDialog({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const [form, setForm] = useState({
    amount: "25.00",
    description: "",
    product_kind: "offline_service",
    mode: "test",
  });

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const create = useMutation({
    mutationFn: () => api.post<Invoice>("/api/dashboard/invoices", form),
    onSuccess: () => client.invalidateQueries({ queryKey: ["dashboard"] }),
  });

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      className="m-auto w-[min(440px,calc(100%-2rem))] rounded-2xl border border-line bg-surface p-0 text-ink shadow-panel backdrop:bg-ink/40"
      aria-labelledby="new-invoice-title"
    >
      <div className="p-6">
        <h2 id="new-invoice-title" className="text-lg font-semibold">
          New invoice
        </h2>
        {create.data ? (
          <div className="mt-4 space-y-4">
            <Notice tone="success" title="Invoice created">
              Send this link to the buyer. The price in Gram is locked for the invoice lifetime.
            </Notice>
            <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2">
              <span className="min-w-0 flex-1 truncate font-mono text-sm">
                {create.data.pay_url}
              </span>
              <CopyButton value={create.data.pay_url} label="payment link" />
            </div>
            <div className="flex justify-end gap-2">
              <Link
                to={`/dashboard/invoices/${create.data.id}`}
                className={buttonClass("secondary")}
              >
                Open invoice
              </Link>
              <Button onClick={() => dialog.current?.close()}>Done</Button>
            </div>
          </div>
        ) : (
          <form
            className="mt-4 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Field label="Amount, USD">
              <input
                className={inputClass}
                inputMode="decimal"
                required
                pattern="^\d+(\.\d{1,2})?$"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </Field>
            <Field label="What it is for" hint="The buyer sees this on the payment page.">
              <input
                className={inputClass}
                required
                maxLength={240}
                placeholder="Table for two, Friday Jazz Night"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>
            <Field label="Type">
              <select
                className={inputClass}
                value={form.product_kind}
                onChange={(e) => setForm({ ...form, product_kind: e.target.value })}
              >
                <option value="offline_service">Ticket or service</option>
                <option value="physical">Physical goods</option>
                <option value="digital">Digital goods</option>
              </select>
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-[var(--accent)]"
                checked={form.mode === "test"}
                onChange={(e) => setForm({ ...form, mode: e.target.checked ? "test" : "live" })}
              />
              Test invoice (can be paid with the simulator)
            </label>
            {create.error && (
              <Notice tone="danger" title="Invoice not created">
                {create.error.message}
              </Notice>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => dialog.current?.close()}>
                Cancel
              </Button>
              <Button type="submit" busy={create.isPending}>
                Create invoice
              </Button>
            </div>
          </form>
        )}
      </div>
    </dialog>
  );
}
