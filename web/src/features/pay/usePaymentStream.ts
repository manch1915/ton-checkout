import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { PublicInvoice } from "@/lib/types";

const EVENTS = [
  "snapshot",
  "invoice.created",
  "invoice.partially_paid",
  "invoice.paid",
  "invoice.expired",
  "invoice.canceled",
];

/** Invoice state for the payment page: one fetch, then live updates over SSE.
 *  If the stream drops (proxies, flaky mobile networks) it falls back to polling. */
export function usePaymentStream(invoiceId: string) {
  const client = useQueryClient();
  const [streamOk, setStreamOk] = useState(() => typeof EventSource !== "undefined");
  const key = ["pay", invoiceId];

  const result = useQuery({
    queryKey: key,
    queryFn: () => api.get<PublicInvoice>(`/api/pay/${invoiceId}`),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      const open = status === "pending" || status === "partially_paid";
      return open && !streamOk ? 5000 : false;
    },
    retry: (count, error) =>
      count < 3 && !(error instanceof Error && error.message.includes("not found")),
  });

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/pay/${invoiceId}/events`);
    const onMessage = (event: MessageEvent<string>) => {
      client.setQueryData(["pay", invoiceId], JSON.parse(event.data) as PublicInvoice);
      setStreamOk(true);
    };
    for (const name of EVENTS) source.addEventListener(name, onMessage as EventListener);
    source.onerror = () => setStreamOk(false);
    return () => source.close();
  }, [client, invoiceId]);

  return { ...result, live: streamOk };
}
