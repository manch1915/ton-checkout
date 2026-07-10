import { CHAIN, useTonAddress, useTonConnectUI } from "@tonconnect/ui-react";
import {
  ArrowUpRight,
  ChevronDown,
  CircleCheck,
  Clock3,
  FlaskConical,
  QrCode,
  Wallet,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";

import { AssetIcon, Button, CopyButton, Notice, buttonClass, cx } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { amount, assetLabel, assetUnit, dateTime, money, shortAddress } from "@/lib/format";
import { isTelegram, openStarsInvoice, telegram } from "@/lib/telegram";
import { jettonTransfer, tonTransfer } from "@/lib/ton";
import type { Asset, PayOption, PublicInvoice } from "@/lib/types";

import { Countdown } from "./Countdown";

type SendState =
  { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; message: string };

export function PayCard({ invoice, live }: { invoice: PublicInvoice; live: boolean }) {
  const open = invoice.status === "pending" || invoice.status === "partially_paid";
  return (
    <article className="overflow-hidden rounded-2xl border border-line bg-surface shadow-panel">
      <header className="px-6 pt-6 pb-5">
        <p className="text-sm text-ink-3">{invoice.merchant}</p>
        <h1 className="mt-1 text-lg leading-snug font-semibold text-balance">
          {invoice.description}
        </h1>
        <p className="mt-3 text-[2.25rem] leading-none font-semibold tracking-tight tabular">
          {money(invoice.fiat_amount, invoice.fiat_currency)}
        </p>
      </header>
      {invoice.mode === "test" && open && <SandboxBar invoice={invoice} />}
      <AnimatePresence mode="wait" initial={false}>
        {invoice.status === "paid" ? (
          <Paid key="paid" invoice={invoice} />
        ) : open ? (
          <Payable key="open" invoice={invoice} live={live} />
        ) : (
          <Closed key="closed" invoice={invoice} />
        )}
      </AnimatePresence>
    </article>
  );
}

function SandboxBar({ invoice }: { invoice: PublicInvoice }) {
  const [busy, setBusy] = useState<string | null>(null);
  const chain = invoice.options.find((o) => o.asset !== "XTR");
  if (!chain) return null;
  const simulate = async (fraction: string) => {
    setBusy(fraction);
    try {
      await api.post(`/api/pay/${invoice.id}/simulate`, { asset: chain.asset, fraction });
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="border-y border-warn/25 bg-warn-soft px-6 py-3 text-sm">
      <p className="flex items-center gap-2 text-ink-2">
        <FlaskConical className="size-4 shrink-0 text-warn" aria-hidden />
        Test invoice. You can pay with test coins or simulate it.
      </p>
      <div className="mt-2 flex gap-4 pl-6">
        <button
          className="font-medium text-warn underline-offset-2 hover:underline disabled:opacity-50"
          onClick={() => simulate("0.5")}
          disabled={busy !== null}
        >
          Simulate half
        </button>
        <button
          className="font-medium text-warn underline-offset-2 hover:underline disabled:opacity-50"
          onClick={() => simulate("1")}
          disabled={busy !== null}
        >
          Simulate full payment
        </button>
      </div>
    </div>
  );
}

function Payable({ invoice, live }: { invoice: PublicInvoice; live: boolean }) {
  const [selected, setSelected] = useState<Asset>(
    invoice.asset ?? invoice.options[0]?.asset ?? "TON",
  );
  const option = invoice.options.find((o) => o.asset === selected) ?? invoice.options[0];
  if (!option) return null;
  const partial = invoice.status === "partially_paid";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="px-6 pt-5 pb-6"
    >
      {invoice.options.length > 1 && (
        <div
          role="tablist"
          aria-label="Pay with"
          className="mb-5 grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1"
        >
          {invoice.options.map((o) => (
            <button
              key={o.asset}
              role="tab"
              aria-selected={o.asset === selected}
              onClick={() => setSelected(o.asset)}
              className={cx(
                "flex h-9 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors",
                o.asset === selected
                  ? "bg-surface text-ink shadow-sm"
                  : "text-ink-3 hover:text-ink",
              )}
            >
              <AssetIcon asset={o.asset} />
              {assetLabel[o.asset]}
            </button>
          ))}
        </div>
      )}

      {partial && (
        <div className="mb-4">
          <Notice tone="warn" title={`Received ${invoice.received} ${assetUnit[option.asset]}`}>
            Send the remaining amount below with the same payment code.
          </Notice>
        </div>
      )}

      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm text-ink-3">{partial ? "Still due" : "To pay"}</span>
        <span className="flex items-center gap-2 font-mono text-xl font-medium tabular">
          {amount(option.due, option.decimals)} {assetUnit[option.asset]}
          {option.asset !== "XTR" && <CopyButton value={option.due} label="amount" />}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-sm text-ink-3">
        <span>
          {option.rate && option.asset === "TON"
            ? `1 GRAM = ${money(option.rate, invoice.fiat_currency)}, rate locked`
            : option.asset === "USDT"
              ? "USDT on TON only. Other networks will not arrive."
              : "Telegram Stars"}
        </span>
        <span className="flex items-center gap-1.5" title="Time left to pay">
          <Clock3 className="size-3.5" aria-hidden />
          <Countdown expiresAt={invoice.expires_at} serverTime={invoice.server_time} />
        </span>
      </div>

      <div className="mt-5">
        {option.asset === "XTR" ? (
          <StarsPay invoice={invoice} />
        ) : (
          <WalletPay invoice={invoice} option={option} />
        )}
      </div>

      {option.asset !== "XTR" && <ManualDetails invoice={invoice} option={option} />}

      <p className="mt-5 flex items-center gap-2 text-xs text-ink-3">
        <span className={cx("size-1.5 rounded-full", live ? "bg-paid" : "bg-warn")} aria-hidden />
        {live
          ? "This page updates by itself once the payment lands."
          : "Reconnecting. Status is checked every few seconds."}
      </p>
    </motion.div>
  );
}

function WalletPay({ invoice, option }: { invoice: PublicInvoice; option: PayOption }) {
  const [tonConnectUI] = useTonConnectUI();
  const address = useTonAddress(false);
  const [state, setState] = useState<SendState>({ kind: "idle" });

  const pay = async () => {
    if (!address) {
      await tonConnectUI.openModal();
      return;
    }
    setState({ kind: "sending" });
    try {
      const network = invoice.network === "testnet" ? CHAIN.TESTNET : CHAIN.MAINNET;
      let request;
      if (option.asset === "USDT") {
        const { jetton_wallet } = await api.post<{ jetton_wallet: string }>(
          `/api/pay/${invoice.id}/jetton-wallet`,
          { owner: address },
        );
        request = jettonTransfer(
          option,
          invoice.recipient,
          address,
          jetton_wallet,
          invoice.reference,
        );
      } else {
        request = tonTransfer(option, invoice.recipient);
      }
      await tonConnectUI.sendTransaction({ ...request, network });
      setState({ kind: "sent" });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : error instanceof Error && /reject|cancel/i.test(error.message)
            ? "You closed the wallet without confirming. Nothing was sent."
            : "The wallet did not send the transaction. Try again or use the QR code below.";
      setState({ kind: "error", message });
    }
  };

  if (state.kind === "sent") {
    return (
      <Notice tone="info" title="Sent from your wallet">
        Waiting for the network to confirm, usually under 10 seconds.
      </Notice>
    );
  }
  return (
    <div className="space-y-3">
      <Button
        size="lg"
        className="w-full"
        onClick={pay}
        busy={state.kind === "sending"}
        icon={<Wallet className="size-4" />}
      >
        {address
          ? `Pay ${amount(option.due, option.decimals)} ${assetUnit[option.asset]}`
          : "Connect wallet to pay"}
      </Button>
      {address && (
        <p className="flex items-center justify-center gap-2 text-xs text-ink-3">
          From {shortAddress(address)}
          <button
            className="underline underline-offset-2 hover:text-ink"
            onClick={() => tonConnectUI.disconnect()}
          >
            Change wallet
          </button>
        </p>
      )}
      {state.kind === "error" && (
        <Notice tone="danger" title="Payment not sent">
          {state.message}
        </Notice>
      )}
    </div>
  );
}

function StarsPay({ invoice }: { invoice: PublicInvoice }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!isTelegram()) {
    return (
      <Notice tone="info" title="Stars work inside Telegram">
        Open this store from the Telegram bot to pay with Stars.
      </Notice>
    );
  }
  const pay = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await api.post<{ url: string }>(`/api/pay/${invoice.id}/stars-link`);
      const result = await openStarsInvoice(url);
      if (result === "paid") telegram()?.HapticFeedback?.notificationOccurred("success");
      if (result === "failed") setError("Telegram could not complete the payment.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open the Stars invoice.");
    } finally {
      setBusy(false);
    }
  };
  const stars = invoice.options.find((o) => o.asset === "XTR");
  return (
    <div className="space-y-3">
      <Button size="lg" className="w-full" onClick={pay} busy={busy}>
        Pay {stars?.amount} Stars
      </Button>
      {error && (
        <Notice tone="danger" title="Payment not completed">
          {error}
        </Notice>
      )}
    </div>
  );
}

function ManualDetails({ invoice, option }: { invoice: PublicInvoice; option: PayOption }) {
  const [openQr, setOpenQr] = useState(false);
  return (
    <div className="mt-5">
      <button
        className="flex w-full items-center justify-between rounded-lg py-2 text-sm font-medium text-ink-2 hover:text-ink"
        aria-expanded={openQr}
        onClick={() => setOpenQr((v) => !v)}
      >
        <span className="flex items-center gap-2">
          <QrCode className="size-4" aria-hidden />
          Pay from another device
        </span>
        <ChevronDown
          className={cx("size-4 transition-transform", openQr && "rotate-180")}
          aria-hidden
        />
      </button>
      <AnimatePresence initial={false}>
        {openQr && option.deeplink && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            className="overflow-hidden"
          >
            <div className="flex flex-col items-center gap-3 pt-3 pb-1">
              <div className="rounded-xl bg-white p-3">
                <QRCodeSVG value={option.deeplink} size={176} level="M" />
              </div>
              <a
                href={option.deeplink}
                className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-strong"
              >
                Open in wallet app <ArrowUpRight className="size-4" aria-hidden />
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <dl className="mt-3 space-y-2 text-sm">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-ink-3">Address</dt>
          <dd className="flex min-w-0 items-center gap-1 font-mono">
            <span className="truncate" title={invoice.recipient}>
              {shortAddress(invoice.recipient, 8)}
            </span>
            <CopyButton value={invoice.recipient} label="address" />
          </dd>
        </div>
      </dl>
      <ReferenceStub reference={invoice.reference} />
    </div>
  );
}

export function ReferenceStub({ reference, stamped }: { reference: string; stamped?: boolean }) {
  const reduce = useReducedMotion();
  return (
    <div className="stub mt-3 flex items-center justify-between gap-3 px-6 py-3">
      <div>
        <p className="text-xs text-ink-3">{stamped ? "Payment code" : "Comment, required"}</p>
        <p className="font-mono text-lg font-medium tracking-wide">{reference}</p>
      </div>
      {stamped ? (
        <motion.span
          initial={reduce ? false : { scale: 1.6, opacity: 0, rotate: -14 }}
          animate={{ scale: 1, opacity: 1, rotate: -8 }}
          transition={{ type: "spring", stiffness: 420, damping: 18, delay: 0.15 }}
          className="rounded-md border-2 border-paid px-2 py-0.5 text-sm font-semibold text-paid"
        >
          Paid
        </motion.span>
      ) : (
        <CopyButton value={reference} label="payment code" />
      )}
    </div>
  );
}

function Paid({ invoice }: { invoice: PublicInvoice }) {
  const tx = invoice.transfers.at(-1);
  const unit = invoice.asset ? assetUnit[invoice.asset] : "";
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="px-6 pt-5 pb-6">
      <div className="flex items-center gap-3">
        <CircleCheck className="size-7 text-paid" aria-hidden />
        <div>
          <p className="font-semibold">Payment received</p>
          <p className="text-sm text-ink-3">
            {invoice.received} {unit}
            {invoice.paid_at && `, ${dateTime(invoice.paid_at)}`}
            {tx?.source === "sandbox" && ", simulated"}
          </p>
        </div>
      </div>
      <ReferenceStub reference={invoice.reference} stamped />
      {invoice.late && (
        <div className="mt-3">
          <Notice tone="warn" title="Paid after the deadline">
            The store has been told. They decide whether to honour the old price.
          </Notice>
        </div>
      )}
      {Number(invoice.overpaid) > 0 && (
        <p className="mt-3 text-sm text-ink-3">
          You sent {invoice.overpaid} {unit} more than needed. Contact {invoice.merchant} for a
          refund.
        </p>
      )}
      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        {invoice.return_url && (
          <a href={invoice.return_url} className={buttonClass("primary", "lg", "sm:flex-1")}>
            Back to {invoice.merchant}
          </a>
        )}
        {tx?.explorer_url && (
          <a
            href={tx.explorer_url}
            target="_blank"
            rel="noreferrer"
            className={buttonClass("secondary", "lg", "sm:flex-1")}
          >
            <ArrowUpRight className="size-4" aria-hidden />
            View transaction
          </a>
        )}
      </div>
    </motion.div>
  );
}

function Closed({ invoice }: { invoice: PublicInvoice }) {
  const expired = invoice.status === "expired";
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="px-6 pt-5 pb-6">
      <Notice
        tone="warn"
        title={expired ? "This payment link has expired" : "This order was canceled"}
        action={
          invoice.return_url ? (
            <a
              href={invoice.return_url}
              className="font-medium text-accent hover:text-accent-strong"
            >
              Back to {invoice.merchant}
            </a>
          ) : undefined
        }
      >
        {expired
          ? "The price was locked for a limited time. Start the order again to get a fresh rate."
          : "The store canceled it before payment."}
        {Number(invoice.received) > 0 &&
          ` ${invoice.received} ${invoice.asset ? assetUnit[invoice.asset] : ""} arrived before that, keep the payment code ${invoice.reference} when you contact the store.`}
      </Notice>
    </motion.div>
  );
}
