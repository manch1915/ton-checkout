import { ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { useParams } from "react-router";

import { TonProvider } from "@/components/TonProvider";
import { Notice, Skeleton, ThemeToggle } from "@/components/ui";
import { PayCard } from "@/features/pay/PayCard";
import { usePaymentStream } from "@/features/pay/usePaymentStream";
import { ApiError } from "@/lib/api";

export function PayPage() {
  return (
    <TonProvider>
      <Payment />
    </TonProvider>
  );
}

function Payment() {
  const { invoiceId = "" } = useParams();
  const embedded = new URLSearchParams(window.location.search).has("embed");
  const { data, error, isPending, live } = usePaymentStream(invoiceId);
  const paid = data?.status === "paid";

  useEffect(() => {
    // Inside the embed widget: tell the host page, it decides what happens next.
    if (embedded && paid && window.parent !== window) {
      window.parent.postMessage({ type: "ton-checkout:paid", invoiceId }, "*");
    }
  }, [embedded, paid, invoiceId]);

  return (
    <main className={embedded ? "p-3" : "flex min-h-dvh flex-col items-center px-4 py-8 sm:py-14"}>
      {!embedded && (
        <div className="mb-4 flex w-full max-w-[440px] items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium text-ink-2">
            <ShieldCheck className="size-4 text-accent" aria-hidden />
            Secure checkout
          </span>
          <ThemeToggle />
        </div>
      )}
      <div className="w-full max-w-[440px]">
        {isPending ? (
          <div className="space-y-4 rounded-2xl border border-line bg-surface p-6" aria-busy>
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-10 w-36" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : error ? (
          <Notice
            tone="danger"
            title={
              error instanceof ApiError && error.status === 404
                ? "Payment link not found"
                : "Could not load this payment"
            }
          >
            {error instanceof ApiError && error.status === 404
              ? "Check the link, or ask the store for a new one."
              : "Check your connection and reload the page."}
          </Notice>
        ) : (
          <PayCard invoice={data} live={live} />
        )}
        {!embedded && data && (
          <p className="mt-5 text-center text-xs leading-relaxed text-ink-3">
            The payment goes straight to {data.merchant}'s wallet, no one holds it in between.
            {data.network === "testnet" && " TON testnet: test coins only."}
          </p>
        )}
      </div>
    </main>
  );
}
