import { useMutation, useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { AssetTag, Button, Notice, Skeleton, cx } from "@/components/ui";
import { api, query } from "@/lib/api";
import { money } from "@/lib/format";
import { isTelegram } from "@/lib/telegram";

import type { Channel, Product, ShopOrder } from "@/lib/types";

export function Catalog() {
  const inTelegram = isTelegram();
  const [params, setParams] = useSearchParams();
  const preview = params.get("as") === "telegram";
  const channel: Channel = inTelegram || preview ? "telegram_mini_app" : "web";

  const products = useQuery({
    queryKey: ["shop", "products", channel],
    queryFn: () => api.get<Product[]>(`/api/shop/products${query({ channel })}`),
  });

  const shows = products.data?.filter((p) => p.kind !== "digital") ?? [];
  const downloads = products.data?.filter((p) => p.kind === "digital") ?? [];

  return (
    <main className="mx-auto max-w-3xl px-4 pt-4 pb-16">
      {!inTelegram && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          <span className="text-ink-2">Show this store as</span>
          <div
            role="radiogroup"
            aria-label="Sales channel"
            className="flex rounded-lg bg-surface-2 p-0.5"
          >
            {[
              { label: "Website", value: false },
              { label: "Telegram Mini App", value: true },
            ].map((item) => (
              <button
                key={item.label}
                role="radio"
                aria-checked={preview === item.value}
                onClick={() => setParams(item.value ? { as: "telegram" } : {})}
                className={cx(
                  "h-8 rounded-md px-3 font-medium",
                  preview === item.value
                    ? "bg-surface text-ink shadow-sm"
                    : "text-ink-3 hover:text-ink",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          <span className="text-xs text-ink-3">
            Payment methods follow Telegram's rules for each channel.
          </span>
        </div>
      )}

      {products.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-2xl" />
          ))}
        </div>
      ) : products.error ? (
        <Notice tone="danger" title="The store could not load">
          Check your connection and reload the page.
        </Notice>
      ) : (
        <>
          <Section title="Shows" note={shows[0]?.policy_note}>
            {shows.map((p) => (
              <ProductRow key={p.id} product={p} channel={channel} />
            ))}
          </Section>
          <Section title="Downloads" note={downloads[0]?.policy_note}>
            {downloads.map((p) => (
              <ProductRow key={p.id} product={p} channel={channel} />
            ))}
          </Section>
        </>
      )}
    </main>
  );
}

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8 first:mt-0">
      <h2 className="text-lg font-semibold">{title}</h2>
      {note && (
        <p className="mt-1 flex items-start gap-1.5 text-sm text-ink-3">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {note}
        </p>
      )}
      <ul className="mt-3 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {children}
      </ul>
    </section>
  );
}

function ProductRow({ product, channel }: { product: Product; channel: Channel }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const starsOnly = product.methods.length === 1 && product.methods[0] === "XTR";

  const order = useMutation({
    mutationFn: () => api.post<ShopOrder>("/api/shop/orders", { product_id: product.id, channel }),
    // The payment page decides how to pay, Stars included (simulated in the demo).
    onSuccess: (created) => navigate(`/pay/${created.invoice_id}`),
    onError: (e) => setError(e instanceof Error ? e.message : "Could not start the order."),
  });

  const date = product.subtitle.match(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d+) (\w+)/);

  return (
    <li className="flex items-center gap-4 px-4 py-4 sm:px-5">
      {date ? (
        <div className="flex w-12 shrink-0 flex-col items-center rounded-lg border border-line py-1.5 text-center">
          <span className="text-[11px] text-ink-3">{date[3]}</span>
          <span className="text-lg leading-tight font-semibold tabular">{date[2]}</span>
        </div>
      ) : (
        <div className="flex w-12 shrink-0 justify-center">
          <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-3">
            {product.badge}
          </span>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="font-medium">{product.title}</p>
        <p className="truncate text-sm text-ink-3">{product.subtitle}</p>
        <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {product.methods.map((m) => (
            <AssetTag key={m} asset={m} />
          ))}
        </p>
        {error && <p className="mt-1 text-sm text-danger">{error}</p>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <span className="font-semibold tabular">
          {starsOnly ? `${product.stars} Stars` : money(product.price)}
        </span>
        <Button size="sm" onClick={() => order.mutate()} busy={order.isPending}>
          {product.kind === "digital" ? "Buy" : "Get ticket"}
        </Button>
      </div>
    </li>
  );
}
