import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Plus, RotateCcw, Send, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { Button, CopyButton, EmptyState, Notice, Skeleton, cx, inputClass } from "@/components/ui";
import { api, query } from "@/lib/api";
import { dateTime, relative } from "@/lib/format";
import type { Delivery, DeliveryDetail, Endpoint } from "@/lib/types";

import { PageHeader, Table, Td, Th, selectClass } from "./parts";

export function DeliveryState({ delivery }: { delivery: Delivery }) {
  const tone = {
    succeeded: "bg-paid-soft text-paid",
    pending: delivery.attempts > 0 ? "bg-warn-soft text-warn" : "bg-accent-soft text-accent-strong",
    failed: "bg-danger-soft text-danger",
  }[delivery.state];
  const text =
    delivery.state === "succeeded"
      ? `Delivered${delivery.last_status_code ? `, ${delivery.last_status_code}` : ""}`
      : delivery.state === "failed"
        ? "Gave up"
        : delivery.attempts > 0
          ? `Retrying, attempt ${delivery.attempts + 1}`
          : "Queued";
  return (
    <span className={cx("rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", tone)}>
      {text}
    </span>
  );
}

export function Webhooks() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("delivery");
  const [state, setState] = useState("");

  const deliveries = useQuery({
    queryKey: ["dashboard", "deliveries", state],
    queryFn: () => api.get<Delivery[]>(`/api/dashboard/deliveries${query({ state })}`),
    refetchInterval: 5000,
  });

  return (
    <>
      <PageHeader
        title="Webhooks"
        description="Your server gets a signed POST for every invoice event. Failed deliveries are retried for about three days."
      />
      <Endpoints />

      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Delivery log</h2>
          <select
            className={selectClass}
            aria-label="Delivery state"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option value="">All deliveries</option>
            <option value="pending">Queued or retrying</option>
            <option value="succeeded">Delivered</option>
            <option value="failed">Gave up</option>
          </select>
        </div>
        {deliveries.isPending ? (
          <Skeleton className="h-48 w-full rounded-2xl" />
        ) : !deliveries.data?.length ? (
          <div className="rounded-2xl border border-line bg-surface">
            <EmptyState title="No deliveries yet">
              Add an endpoint and send a test event to see it here.
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Event</Th>
                <Th>Endpoint</Th>
                <Th>Result</Th>
                <Th>Attempts</Th>
                <Th>When</Th>
              </tr>
            </thead>
            <tbody>
              {deliveries.data.map((d) => (
                <tr
                  key={d.id}
                  className={cx(
                    "cursor-pointer hover:bg-surface-2",
                    selected === d.id && "bg-accent-soft",
                  )}
                  onClick={() => setParams({ delivery: d.id })}
                >
                  <Td>
                    <button
                      className="font-mono text-xs hover:text-accent"
                      onClick={() => setParams({ delivery: d.id })}
                    >
                      {d.event_type}
                    </button>
                  </Td>
                  <Td className="max-w-64 truncate text-ink-3">{d.endpoint_url}</Td>
                  <Td>
                    <DeliveryState delivery={d} />
                  </Td>
                  <Td className="tabular">{d.attempts}</Td>
                  <Td className="whitespace-nowrap text-ink-3">{relative(d.created_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>

      {selected && <DeliveryDrawer id={selected} onClose={() => setParams({})} />}
    </>
  );
}

function Endpoints() {
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const endpoints = useQuery({
    queryKey: ["dashboard", "endpoints"],
    queryFn: () => api.get<Endpoint[]>("/api/dashboard/webhooks"),
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["dashboard"] });
  const create = useMutation({
    mutationFn: () => api.post<Endpoint>("/api/dashboard/webhooks", { url }),
    onSuccess: () => {
      setUrl("");
      void refresh();
    },
  });

  return (
    <section className="rounded-2xl border border-line bg-surface">
      <div className="border-b border-line px-5 py-3">
        <h2 className="font-semibold">Endpoints</h2>
      </div>
      {endpoints.isPending ? (
        <div className="p-5">
          <Skeleton className="h-12 w-full" />
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {endpoints.data?.map((e) => (
            <EndpointRow key={e.id} endpoint={e} onChange={refresh} />
          ))}
        </ul>
      )}
      <form
        className="flex flex-col gap-2 border-t border-line p-5 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <label className="flex-1">
          <span className="sr-only">Endpoint URL</span>
          <input
            className={inputClass}
            type="url"
            required
            placeholder="https://your-server.com/webhooks/ton"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <Button type="submit" busy={create.isPending} icon={<Plus className="size-4" />}>
          Add endpoint
        </Button>
      </form>
      {create.error && (
        <div className="px-5 pb-5">
          <Notice tone="danger" title="Endpoint not added">
            {create.error.message}
          </Notice>
        </div>
      )}
    </section>
  );
}

function EndpointRow({ endpoint, onChange }: { endpoint: Endpoint; onChange: () => void }) {
  const [reveal, setReveal] = useState(false);
  const act = useMutation({
    mutationFn: (action: "toggle" | "rotate" | "test" | "delete") => {
      const base = `/api/dashboard/webhooks/${endpoint.id}`;
      if (action === "toggle") return api.patch(base, { enabled: !endpoint.enabled });
      if (action === "rotate") return api.post(`${base}/rotate-secret`);
      if (action === "test") return api.post(`${base}/test`);
      return api.del(base);
    },
    onSuccess: onChange,
  });
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={cx("size-2 rounded-full", endpoint.enabled ? "bg-paid" : "bg-line-strong")}
          aria-hidden
        />
        <span className="min-w-0 flex-1 truncate font-mono text-sm" title={endpoint.url}>
          {endpoint.url}
        </span>
        <div className="flex gap-1">
          <Button
            size="sm"
            variant="ghost"
            icon={<Send className="size-4" />}
            onClick={() => act.mutate("test")}
            busy={act.isPending && act.variables === "test"}
          >
            Send test
          </Button>
          <Button size="sm" variant="ghost" onClick={() => act.mutate("toggle")}>
            {endpoint.enabled ? "Pause" : "Resume"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Delete endpoint"
            icon={<Trash2 className="size-4" />}
            onClick={() => {
              if (window.confirm("Delete this endpoint? Its delivery history goes with it."))
                act.mutate("delete");
            }}
          />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 pl-5 text-sm">
        <span className="text-ink-3">Signing secret</span>
        <code className="rounded bg-surface-2 px-2 py-0.5 font-mono text-xs">
          {reveal ? endpoint.secret : "whsec_••••••••••••••••"}
        </code>
        <button
          className="text-ink-3 hover:text-ink"
          onClick={() => setReveal((v) => !v)}
          aria-label={reveal ? "Hide secret" : "Show secret"}
        >
          {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
        <CopyButton value={endpoint.secret} label="signing secret" />
        <button
          className="inline-flex items-center gap-1 text-ink-3 hover:text-ink"
          onClick={() => {
            if (window.confirm("Rotate the secret? Your server must switch to the new one."))
              act.mutate("rotate");
          }}
        >
          <RotateCcw className="size-3.5" aria-hidden /> Rotate
        </button>
      </div>
      {act.error && <p className="mt-2 pl-5 text-sm text-danger">{act.error.message}</p>}
    </li>
  );
}

function DeliveryDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const detail = useQuery({
    queryKey: ["dashboard", "delivery", id],
    queryFn: () => api.get<DeliveryDetail>(`/api/dashboard/deliveries/${id}`),
    refetchInterval: 3000,
  });
  const resend = useMutation({
    mutationFn: () => api.post(`/api/dashboard/deliveries/${id}/resend`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["dashboard"] }),
  });

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      className="mr-0 ml-auto h-dvh max-h-none w-[min(560px,100%)] border-l border-line bg-surface p-0 text-ink backdrop:bg-ink/40"
      aria-label="Delivery details"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-semibold">Delivery</h2>
          <Button size="sm" variant="ghost" onClick={() => dialog.current?.close()}>
            Close
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 text-sm">
          {!detail.data ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-mono">{detail.data.delivery.event_type}</p>
                  <p className="text-ink-3">{detail.data.delivery.endpoint_url}</p>
                </div>
                <DeliveryState delivery={detail.data.delivery} />
              </div>
              {detail.data.delivery.next_attempt_at && detail.data.delivery.state === "pending" && (
                <p className="mt-2 text-ink-3">
                  Next attempt {relative(detail.data.delivery.next_attempt_at)}
                </p>
              )}
              <h3 className="mt-6 font-semibold">Attempts</h3>
              {detail.data.attempts.length === 0 ? (
                <p className="mt-2 text-ink-3">Not sent yet.</p>
              ) : (
                <ol className="mt-2 space-y-2">
                  {detail.data.attempts.map((a) => (
                    <li key={a.number} className="rounded-lg border border-line p-3">
                      <div className="flex justify-between gap-3">
                        <span className="font-medium">
                          #{a.number}{" "}
                          {a.status_code ? (
                            <span className={a.status_code < 300 ? "text-paid" : "text-danger"}>
                              HTTP {a.status_code}
                            </span>
                          ) : (
                            <span className="text-danger">No response</span>
                          )}
                        </span>
                        <span className="text-ink-3 tabular">
                          {a.duration_ms} ms, {dateTime(a.created_at)}
                        </span>
                      </div>
                      {(a.error || a.response_excerpt) && (
                        <pre className="mt-2 overflow-x-auto rounded bg-surface-2 p-2 font-mono text-xs whitespace-pre-wrap text-ink-2">
                          {a.error ?? a.response_excerpt}
                        </pre>
                      )}
                    </li>
                  ))}
                </ol>
              )}
              <h3 className="mt-6 font-semibold">Payload</h3>
              <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-surface-2 p-3 font-mono text-xs leading-relaxed">
                {JSON.stringify(detail.data.payload, null, 2)}
              </pre>
            </>
          )}
        </div>
        <div className="border-t border-line px-5 py-4">
          <Button
            onClick={() => resend.mutate()}
            busy={resend.isPending}
            icon={<RotateCcw className="size-4" />}
          >
            Send again
          </Button>
          {resend.isSuccess && (
            <span className="ml-3 text-sm text-ink-3">Queued, it goes out within seconds.</span>
          )}
        </div>
      </div>
    </dialog>
  );
}
