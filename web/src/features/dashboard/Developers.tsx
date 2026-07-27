import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useState } from "react";

import { Button, CopyButton, EmptyState, Notice, Skeleton, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { relative } from "@/lib/format";
import type { ApiKey, Mode } from "@/lib/types";

import { PageHeader, Table, Td, Th, selectClass } from "./parts";

export function Developers() {
  const origin = window.location.origin;
  return (
    <>
      <PageHeader
        title="API keys"
        description="Your backend creates invoices with a secret key. Keep keys on the server; the payment page never needs one."
      />
      <Keys />
      <section className="mt-8 grid gap-6 lg:grid-cols-2">
        <Snippet
          title="Create an invoice"
          code={`curl ${origin}/v1/invoices \\
  -H "Authorization: Bearer sk_test_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "amount": "24.00",
    "description": "Neon Harbor live",
    "order_id": "A-1042",
    "product_kind": "offline_service",
    "return_url": "https://your-store.com/orders/A-1042"
  }'`}
          note="The response has pay_url. Redirect the buyer there or open it in the widget."
        />
        <Snippet
          title="Verify a webhook (Python)"
          code={`from standardwebhooks import Webhook

wh = Webhook(WEBHOOK_SECRET)  # whsec_...

@app.post("/webhooks/ton")
async def ton_webhook(request: Request):
    body = await request.body()
    event = wh.verify(body, dict(request.headers))
    if event["type"] == "invoice.paid":
        order_id = event["data"]["invoice"]["order_id"]
        await fulfil(order_id)  # make it idempotent
    return {"ok": True}`}
          note="Signatures follow Standard Webhooks, so the official verifier works in any language."
        />
        <Snippet
          title="Embed the checkout on your site"
          code={`<script src="${origin}/checkout.js" defer></script>
<button data-ton-checkout="inv_...">Pay with Gram</button>

<script>
  window.addEventListener("ton-checkout:paid", (e) => {
    location.href = "/thanks?invoice=" + e.detail.invoiceId;
  });
</script>`}
          note="One script tag. The button opens the payment page in a modal and fires an event when it is paid."
        />
        <Snippet
          title="Open it from a Telegram bot (aiogram)"
          code={`invoice = await checkout.create_invoice(
    amount="18.00", description="Friday Jazz Night",
    product_kind="offline_service", channel="telegram_mini_app",
)
await message.answer(
    "Your ticket is reserved for 30 minutes.",
    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Pay", web_app=WebAppInfo(url=invoice["pay_url"]))
    ]]),
)`}
          note="Full aiogram and grammY bots are in the examples folder of the repository."
        />
      </section>
    </>
  );
}

function Keys() {
  const client = useQueryClient();
  const [label, setLabel] = useState("");
  const [mode, setMode] = useState<Mode>("test");
  const keys = useQuery({
    queryKey: ["dashboard", "keys"],
    queryFn: () => api.get<ApiKey[]>("/api/dashboard/api-keys"),
  });
  const create = useMutation({
    mutationFn: () =>
      api.post<{ key: ApiKey; secret: string }>("/api/dashboard/api-keys", { label, mode }),
    onSuccess: () => {
      setLabel("");
      void client.invalidateQueries({ queryKey: ["dashboard", "keys"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.del(`/api/dashboard/api-keys/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["dashboard", "keys"] }),
  });

  return (
    <section className="space-y-4">
      <form
        className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-5 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <label className="flex-1">
          <span className="sr-only">Key name</span>
          <input
            className={inputClass}
            required
            maxLength={80}
            placeholder="Name, e.g. Production server"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <select
          className={`${selectClass} h-10`}
          aria-label="Key mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
        >
          <option value="test">Test key</option>
          <option value="live">Live key</option>
        </select>
        <Button type="submit" busy={create.isPending} icon={<KeyRound className="size-4" />}>
          Create key
        </Button>
      </form>

      {create.data && (
        <Notice tone="success" title="Copy the key now. It is shown only once.">
          <span className="mt-2 flex items-center gap-2 rounded-lg bg-surface px-3 py-2">
            <code className="min-w-0 flex-1 truncate font-mono text-xs text-ink">
              {create.data.secret}
            </code>
            <CopyButton value={create.data.secret} label="API key" />
          </span>
        </Notice>
      )}
      {create.error && (
        <Notice tone="danger" title="Key not created">
          {create.error.message}
        </Notice>
      )}

      {keys.isPending ? (
        <Skeleton className="h-32 w-full rounded-2xl" />
      ) : !keys.data?.length ? (
        <div className="rounded-2xl border border-line bg-surface">
          <EmptyState title="No keys yet">
            Create a test key to try the API from your terminal.
          </EmptyState>
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Key</Th>
              <Th>Mode</Th>
              <Th>Last used</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {keys.data.map((k) => (
              <tr key={k.id} className={k.revoked ? "text-ink-3" : undefined}>
                <Td className="font-medium">{k.label}</Td>
                <Td className="font-mono text-xs">{k.prefix}…</Td>
                <Td>{k.mode === "test" ? "Test" : "Live"}</Td>
                <Td>
                  {k.revoked ? "Revoked" : k.last_used_at ? relative(k.last_used_at) : "Never"}
                </Td>
                <Td className="text-right">
                  {!k.revoked && (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        if (
                          window.confirm(
                            `Revoke "${k.label}"? Requests with it will start failing.`,
                          )
                        )
                          revoke.mutate(k.id);
                      }}
                    >
                      Revoke
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </section>
  );
}

function Snippet({ title, code, note }: { title: string; code: string; note: string }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <CopyButton value={code} label={`${title} code`} />
      </div>
      <pre className="flex-1 overflow-x-auto bg-surface-2 p-4 font-mono text-xs leading-relaxed">
        {code}
      </pre>
      <p className="border-t border-line px-4 py-2.5 text-xs text-ink-3">{note}</p>
    </div>
  );
}
