import { useQuery } from "@tanstack/react-query";
import { Download, LoaderCircle } from "lucide-react";
import { Link, useParams } from "react-router";

import { Notice, Skeleton, buttonClass } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { ShopOrder } from "@/lib/types";

export function OrderPage() {
  const { orderId = "" } = useParams();
  const order = useQuery({
    queryKey: ["shop", "order", orderId],
    queryFn: () => api.get<ShopOrder>(`/api/shop/orders/${orderId}`),
    // The store learns about the payment from our webhook, usually within a few seconds.
    refetchInterval: (q) => (q.state.data?.status === "fulfilled" ? false : 2000),
  });

  return (
    <main className="mx-auto max-w-md px-4 pt-6 pb-16">
      {order.isPending ? (
        <Skeleton className="h-64 w-full rounded-2xl" />
      ) : order.error ? (
        <Notice tone="danger" title="Order not found">
          Check the link or start a new order.
        </Notice>
      ) : order.data.status !== "fulfilled" ? (
        <div className="rounded-2xl border border-line bg-surface p-6 text-center">
          <LoaderCircle className="mx-auto size-6 animate-spin text-accent" aria-hidden />
          <p className="mt-3 font-medium">Waiting for the store to confirm</p>
          <p className="mt-1 text-sm text-ink-3">
            The checkout sends the store a signed webhook once the payment lands.
          </p>
          <Link
            to={`/pay/${order.data.invoice_id}`}
            className={buttonClass("secondary", "md", "mt-5")}
          >
            Back to payment
          </Link>
        </div>
      ) : (
        <Ticket order={order.data} />
      )}
      <p className="mt-6 text-center">
        <Link to="/shop" className="text-sm font-medium text-accent hover:text-accent-strong">
          Continue shopping
        </Link>
      </p>
    </main>
  );
}

function Ticket({ order }: { order: ShopOrder }) {
  const digital = order.product.kind === "digital";
  return (
    <article className="overflow-hidden rounded-2xl border border-line bg-surface shadow-panel">
      <div className="bg-ink px-6 py-5 text-bg">
        <p className="text-sm opacity-70">Cellar Nine</p>
        <h1 className="mt-1 text-xl font-semibold">{order.product.title}</h1>
        <p className="mt-1 text-sm opacity-80">{order.product.subtitle}</p>
      </div>
      <div className="stub mx-4 my-5 flex items-center justify-between px-6 py-4">
        <div>
          <p className="text-xs text-ink-3">
            {digital ? "Download code" : "Show this at the door"}
          </p>
          <p className="font-mono text-2xl font-medium tracking-[0.2em]">{order.access_code}</p>
        </div>
        <span className="rounded-md border-2 border-paid px-2 py-0.5 text-sm font-semibold text-paid -rotate-6">
          Paid
        </span>
      </div>
      <div className="px-6 pb-6 text-sm text-ink-3">
        {order.fulfilled_at && <p>Issued {dateTime(order.fulfilled_at)}</p>}
        {digital && (
          <button disabled className={buttonClass("secondary", "md", "mt-4 w-full")}>
            <Download className="size-4" aria-hidden />
            Download (demo file not attached)
          </button>
        )}
      </div>
    </article>
  );
}
