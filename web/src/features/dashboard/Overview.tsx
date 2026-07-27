import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType,
} from "recharts";

import { AssetTag, Notice, Skeleton, StatusBadge, cx } from "@/components/ui";
import { api, query } from "@/lib/api";
import { amount, money, percent, relative } from "@/lib/format";
import type { Invoice, Page, Stats } from "@/lib/types";

import { PageHeader, Segmented, Table, Td, Th } from "./parts";

type ModeFilter = "all" | "test" | "live";
type Range = "7" | "14" | "30";

const SERIES = [
  { key: "ton", label: "Gram", color: "var(--series-ton)" },
  { key: "usdt", label: "USDT", color: "var(--series-usdt)" },
  { key: "stars", label: "Stars", color: "var(--series-stars)" },
] as const;

export function Overview() {
  const [mode, setMode] = useState<ModeFilter>("all");
  const [range, setRange] = useState<Range>("14");
  const [asTable, setAsTable] = useState(false);
  const modeParam = mode === "all" ? undefined : mode;

  const stats = useQuery({
    queryKey: ["dashboard", "stats", Number(range), mode],
    queryFn: () => api.get<Stats>(`/api/dashboard/stats${query({ days: range, mode: modeParam })}`),
  });
  const recent = useQuery({
    queryKey: ["dashboard", "invoices", "recent", mode],
    queryFn: () =>
      api.get<Page<Invoice>>(`/api/dashboard/invoices${query({ limit: 6, mode: modeParam })}`),
  });

  return (
    <>
      <PageHeader
        title="Overview"
        actions={
          <>
            <Segmented
              label="Invoice mode"
              value={mode}
              onChange={setMode}
              options={[
                { value: "all", label: "All" },
                { value: "test", label: "Test" },
                { value: "live", label: "Live" },
              ]}
            />
            <Segmented
              label="Period"
              value={range}
              onChange={setRange}
              options={[
                { value: "7", label: "7 days" },
                { value: "14", label: "14 days" },
                { value: "30", label: "30 days" },
              ]}
            />
          </>
        }
      />

      {stats.error ? (
        <Notice tone="danger" title="Numbers could not load">
          {stats.error.message}
        </Notice>
      ) : (
        <>
          <Kpis stats={stats.data} />
          {stats.data && stats.data.unmatched_transfers > 0 && (
            <div className="mt-4">
              <Notice
                tone="warn"
                title={`${stats.data.unmatched_transfers} payment${stats.data.unmatched_transfers === 1 ? "" : "s"} arrived without a valid payment code`}
                action={
                  <Link to="/dashboard/review" className="font-medium text-warn hover:underline">
                    Match them to orders
                  </Link>
                }
              >
                The money is in your wallet, but we could not tell which order it belongs to.
              </Notice>
            </div>
          )}

          <section className="mt-6 rounded-2xl border border-line bg-surface p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold">Revenue by day</h2>
              <div className="flex items-center gap-4 text-sm">
                <ul className="flex gap-4" aria-label="Legend">
                  {SERIES.map((s) => (
                    <li key={s.key} className="flex items-center gap-1.5 text-ink-2">
                      <span
                        className="size-2.5 rounded-sm"
                        style={{ background: s.color }}
                        aria-hidden
                      />
                      {s.label}
                    </li>
                  ))}
                </ul>
                <button
                  className="font-medium text-accent hover:text-accent-strong"
                  onClick={() => setAsTable((v) => !v)}
                  aria-pressed={asTable}
                >
                  {asTable ? "Show chart" : "Show table"}
                </button>
              </div>
            </div>
            <div className="mt-4">
              {!stats.data ? (
                <Skeleton className="h-64 w-full" />
              ) : asTable ? (
                <DayTable stats={stats.data} />
              ) : (
                <RevenueChart stats={stats.data} />
              )}
            </div>
          </section>
        </>
      )}

      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Latest invoices</h2>
          <Link
            to="/dashboard/invoices"
            className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-strong"
          >
            All invoices <ArrowUpRight className="size-4" aria-hidden />
          </Link>
        </div>
        <InvoiceRows data={recent.data?.items} loading={recent.isPending} />
      </section>
    </>
  );
}

function Kpis({ stats }: { stats?: Stats }) {
  const items = [
    { label: "Revenue", value: stats ? money(stats.gross_fiat) : null },
    { label: "Paid invoices", value: stats ? String(stats.paid_count) : null },
    {
      label: "Paid of created",
      value: stats ? percent(stats.conversion) : null,
      hint: stats ? `${stats.created_count} created, ${stats.expired_count} expired` : null,
    },
    { label: "Average order", value: stats ? money(stats.average_order) : null },
    {
      label: "Webhooks delivered",
      value: stats
        ? stats.webhook_success_rate === null
          ? "No data"
          : percent(stats.webhook_success_rate)
        : null,
    },
  ];
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-2xl border border-line bg-surface sm:grid-cols-3 lg:grid-cols-5">
      {items.map((item, i) => (
        <div
          key={item.label}
          className={cx(
            "border-line px-5 py-4",
            i > 0 && "border-l",
            i >= 2 && "max-sm:border-t",
            i === 2 && "max-sm:border-l-0",
            i === 4 && "max-sm:border-l-0",
            i >= 3 && "sm:max-lg:border-t",
            i === 3 && "sm:max-lg:border-l-0",
          )}
        >
          <dt className="text-sm text-ink-3">{item.label}</dt>
          <dd className="mt-1 text-xl font-semibold tabular">
            {item.value ?? <Skeleton className="h-7 w-20" />}
          </dd>
          {item.hint && <dd className="mt-0.5 text-xs text-ink-3">{item.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

function RevenueChart({ stats }: { stats: Stats }) {
  const data = stats.days.map((d) => ({
    day: d.day,
    ton: Number(d.ton),
    usdt: Number(d.usdt),
    stars: Number(d.stars),
    paid: d.paid,
  }));
  if (data.every((d) => d.ton + d.usdt + d.stars === 0)) {
    return (
      <p className="py-16 text-center text-sm text-ink-3">No paid invoices in this period yet.</p>
    );
  }
  return (
    <div
      className="h-64"
      role="img"
      aria-label="Stacked bar chart of daily revenue in US dollars by payment method"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 4, right: 4, left: -8, bottom: 0 }}
          barCategoryGap="28%"
        >
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis
            dataKey="day"
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
            tickFormatter={(d: string) =>
              new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
            }
            minTickGap={16}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={48}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
            tickFormatter={(v: number) => `$${v}`}
          />
          <Tooltip cursor={{ fill: "var(--surface-2)" }} content={ChartTooltip} />
          {SERIES.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId="revenue"
              fill={s.color}
              stroke="var(--surface)"
              strokeWidth={2}
              radius={i === SERIES.length - 1 ? [4, 4, 0, 0] : 0}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: TooltipContentProps<TooltipValueType, string | number>) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((sum, p) => sum + Number(p.value ?? 0), 0);
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-panel">
      <p className="font-medium">
        {new Date(String(label)).toLocaleDateString("en-GB", {
          weekday: "short",
          day: "numeric",
          month: "short",
        })}
      </p>
      <ul className="mt-1 space-y-0.5">
        {payload.map((p) => (
          <li key={String(p.dataKey)} className="flex items-center justify-between gap-6">
            <span className="flex items-center gap-1.5 text-ink-2">
              <span className="size-2 rounded-sm" style={{ background: p.color }} aria-hidden />
              {p.name}
            </span>
            <span className="tabular">{money(Number(p.value ?? 0))}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 flex justify-between border-t border-line pt-1 font-medium">
        <span>Total</span>
        <span className="tabular">{money(total)}</span>
      </p>
    </div>
  );
}

function DayTable({ stats }: { stats: Stats }) {
  return (
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface text-left text-ink-3">
          <tr>
            <th className="py-2 font-medium">Day</th>
            {SERIES.map((s) => (
              <th key={s.key} className="py-2 text-right font-medium">
                {s.label}
              </th>
            ))}
            <th className="py-2 text-right font-medium">Paid</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {stats.days.map((d) => (
            <tr key={d.day} className="border-t border-line">
              <td className="py-1.5">{d.day}</td>
              <td className="py-1.5 text-right">{money(d.ton)}</td>
              <td className="py-1.5 text-right">{money(d.usdt)}</td>
              <td className="py-1.5 text-right">{money(d.stars)}</td>
              <td className="py-1.5 text-right">{d.paid}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InvoiceRows({ data, loading }: { data?: Invoice[]; loading: boolean }) {
  const navigate = useNavigate();
  if (loading) return <Skeleton className="h-48 w-full rounded-2xl" />;
  if (!data?.length) {
    return (
      <div className="rounded-2xl border border-line bg-surface px-6 py-12 text-center text-sm text-ink-3">
        No invoices match these filters.
      </div>
    );
  }
  return (
    <Table>
      <thead>
        <tr>
          <Th>Created</Th>
          <Th>Order</Th>
          <Th className="text-right">Amount</Th>
          <Th>Paid with</Th>
          <Th>Status</Th>
        </tr>
      </thead>
      <tbody>
        {data.map((inv) => (
          <tr
            key={inv.id}
            className="cursor-pointer hover:bg-surface-2"
            onClick={() => navigate(`/dashboard/invoices/${inv.id}`)}
          >
            <Td className="whitespace-nowrap text-ink-3">{relative(inv.created_at)}</Td>
            <Td>
              <Link
                to={`/dashboard/invoices/${inv.id}`}
                className="font-medium hover:text-accent"
                onClick={(e) => e.stopPropagation()}
              >
                {inv.description}
              </Link>
              <span className="block font-mono text-xs text-ink-3">{inv.reference}</span>
            </Td>
            <Td className="text-right whitespace-nowrap tabular">
              {money(inv.fiat_amount, inv.fiat_currency)}
              {inv.asset && inv.status === "paid" && (
                <span className="block text-xs text-ink-3">
                  {amount(inv.received)} {inv.asset === "TON" ? "GRAM" : inv.asset}
                </span>
              )}
            </Td>
            <Td>
              {inv.asset ? (
                <AssetTag asset={inv.asset} />
              ) : (
                <span className="text-ink-3">Not chosen</span>
              )}
            </Td>
            <Td>
              <span className="flex items-center gap-2">
                <StatusBadge status={inv.status} short />
                {inv.mode === "test" && <span className="text-xs text-ink-3">test</span>}
              </span>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
