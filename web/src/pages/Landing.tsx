import { ArrowUpRight, CircleDollarSign, Diamond, FolderGit2 } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { ThemeToggle, buttonClass, cx } from "@/components/ui";

const REPO = "https://github.com/manch1915/ton-checkout";

const STEPS = [
  {
    title: "Your server creates an invoice",
    body: "One POST with the price in dollars. The checkout quotes it in Gram and USDT at the current rate and locks it for 30 minutes.",
  },
  {
    title: "The buyer pays from their own wallet",
    body: "Through TON Connect in one tap, or by QR from another phone. Every payment carries a short code that ties it to the order.",
  },
  {
    title: "The checkout finds it on chain",
    body: "A watcher reads the merchant wallet, checks amount, code and jetton contract, and handles underpaid, overpaid and late payments.",
  },
  {
    title: "Your server gets a signed webhook",
    body: "Standard Webhooks format with HMAC signatures, retries for three days and a delivery log you can replay.",
  },
];

const FEATURES = [
  [
    "Money goes straight to you",
    "Buyers pay to your wallet. The server stores no private keys and can never move funds.",
  ],
  [
    "Gram, USDT and Stars",
    "Native coin and the USDT jetton over TON Connect, Telegram Stars for digital goods in bots.",
  ],
  [
    "Follows Telegram's rules",
    "Each order gets only the methods allowed for its type and channel, Stars for digital goods inside Telegram.",
  ],
  [
    "Live status for the buyer",
    "The payment page updates over server-sent events the moment the transfer lands.",
  ],
  [
    "Nothing lost to typos",
    "Payments without a code land in a review queue where you match them to an order by hand.",
  ],
  [
    "Merchant dashboard",
    "Revenue by day and currency, filters, CSV export, API keys, webhook log and wallet login.",
  ],
  [
    "One-line widget",
    "A script tag turns any button into a checkout. Works on a site, in a Mini App or from a bot.",
  ],
  ["Test mode", "Testnet coins plus a simulator, so a whole flow can be tried without a wallet."],
];

export function Landing() {
  useEffect(() => {
    document.title = "TON Checkout: Gram, USDT and Stars payments to your own wallet";
  }, []);

  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="font-semibold whitespace-nowrap">TON Checkout</span>
        <nav className="flex items-center text-sm whitespace-nowrap sm:gap-1">
          <Link to="/shop" className="rounded-lg px-2 py-2 font-medium text-ink-2 hover:text-ink sm:px-3">
            Demo store
          </Link>
          <Link to="/login" className="rounded-lg px-2 py-2 font-medium text-ink-2 hover:text-ink sm:px-3">
            Dashboard
          </Link>
          <a
            href={REPO}
            className="hidden rounded-lg px-3 py-2 font-medium text-ink-2 hover:text-ink sm:block"
          >
            GitHub
          </a>
          <ThemeToggle />
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-8 pb-20 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:pt-16">
        <div>
          <h1 className="max-w-xl text-4xl leading-[1.08] font-semibold tracking-tight text-balance sm:text-5xl">
            Take Gram, USDT and Stars payments straight to your own wallet
          </h1>
          <p className="mt-5 max-w-lg text-lg text-ink-2">
            A checkout for Telegram bots, Mini Apps and websites. It creates invoices, watches the
            TON network for the payment and tells your server with a signed webhook. Nobody holds
            the money in between.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/shop" className={buttonClass("primary", "lg")}>
              Try the demo store
            </Link>
            <Link to="/login" className={buttonClass("secondary", "lg")}>
              Open the dashboard
            </Link>
          </div>
          <p className="mt-4 text-sm text-ink-3">Runs on TON testnet. No sign-up, no real money.</p>
        </div>
        <HeroCheckout />
      </section>

      <section className="border-y border-line bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight">How a payment moves</h2>
          <ol className="mt-8 grid gap-8 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, i) => (
              <li key={step.title}>
                <span className="flex size-8 items-center justify-center rounded-full border border-line-strong text-sm font-semibold tabular">
                  {i + 1}
                </span>
                <h3 className="mt-4 font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">What is in the box</h2>
          <dl className="mt-6 grid gap-x-8 gap-y-6 sm:grid-cols-2">
            {FEATURES.map(([title, body]) => (
              <div key={title}>
                <dt className="font-medium">{title}</dt>
                <dd className="mt-1 text-sm leading-relaxed text-ink-2">{body}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold tracking-tight">Ten lines to your first invoice</h2>
          <pre className="mt-6 overflow-x-auto rounded-2xl bg-[#0e1a26] p-5 font-mono text-[13px] leading-relaxed text-[#d6e2ee]">
            <code>{`curl https://checkout.example/v1/invoices \\
  -H "Authorization: Bearer sk_test_..." \\
  -d '{"amount": "24.00",
       "description": "Neon Harbor live",
       "order_id": "A-1042"}'

# 201 Created
{ "id": "inv_7h2k...", "status": "pending",
  "reference": "TC-4QX7M2KP",
  "pay_url": "https://checkout.example/pay/inv_7h2k..." }`}</code>
          </pre>
          <p className="mt-4 text-sm text-ink-2">
            FastAPI, PostgreSQL and Redis on the server, React with TON Connect on the page. Bots
            for aiogram and grammY are in the repository.
          </p>
          <a href={REPO} className={buttonClass("secondary", "md", "mt-5")}>
            <FolderGit2 className="size-4" aria-hidden />
            Source on GitHub
          </a>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-ink-3 sm:px-6">
          <span>
            Built by{" "}
            <a href="https://narcisbin.com" className="font-medium text-ink-2 hover:text-ink">
              Levon Oganesian
            </a>
            , full-stack developer in Yerevan.
          </span>
          <a
            href="https://t.me/narcisbin"
            className="inline-flex items-center gap-1 font-medium text-ink-2 hover:text-ink"
          >
            Need payments in your bot? Write on Telegram{" "}
            <ArrowUpRight className="size-4" aria-hidden />
          </a>
        </div>
      </footer>
    </div>
  );
}

function HeroCheckout() {
  const reduce = useReducedMotion();
  const [asset, setAsset] = useState<"TON" | "USDT">("TON");
  const [paid, setPaid] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setPaid(true), reduce ? 0 : 1800);
    return () => window.clearTimeout(id);
  }, [reduce]);

  return (
    <div className="relative mx-auto w-full max-w-[400px]" aria-label="Example of the payment page">
      <div className="rounded-2xl border border-line bg-surface shadow-panel">
        <div className="px-6 pt-6 pb-5">
          <p className="text-sm text-ink-3">Cellar Nine</p>
          <p className="mt-1 text-lg font-semibold">Neon Harbor live, 21 Nov</p>
          <p className="mt-3 text-[2.25rem] leading-none font-semibold tracking-tight tabular">
            $24.00
          </p>
        </div>
        <div className="border-t border-line px-6 pt-5 pb-6">
          <div className="grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
            {(["TON", "USDT"] as const).map((a) => (
              <button
                key={a}
                onClick={() => setAsset(a)}
                aria-pressed={asset === a}
                className={cx(
                  "flex h-9 items-center justify-center gap-1.5 rounded-lg text-sm font-medium",
                  asset === a ? "bg-surface text-ink shadow-sm" : "text-ink-3",
                )}
              >
                {a === "TON" ? (
                  <Diamond className="size-4" aria-hidden />
                ) : (
                  <CircleDollarSign className="size-4" aria-hidden />
                )}
                {a === "TON" ? "Gram" : "USDT"}
              </button>
            ))}
          </div>
          <div className="mt-5 flex items-baseline justify-between">
            <span className="text-sm text-ink-3">To pay</span>
            <span className="font-mono text-xl font-medium tabular">
              {asset === "TON" ? "17.778 GRAM" : "24 USDT"}
            </span>
          </div>
          <div className="stub mt-5 flex items-center justify-between px-6 py-3">
            <div>
              <p className="text-xs text-ink-3">{paid ? "Payment code" : "Comment, required"}</p>
              <p className="font-mono text-lg font-medium tracking-wide">TC-4QX7M2KP</p>
            </div>
            {paid && (
              <motion.span
                initial={reduce ? false : { scale: 1.7, opacity: 0, rotate: -16 }}
                animate={{ scale: 1, opacity: 1, rotate: -8 }}
                transition={{ type: "spring", stiffness: 420, damping: 17 }}
                className="rounded-md border-2 border-paid px-2 py-0.5 text-sm font-semibold text-paid"
              >
                Paid
              </motion.span>
            )}
          </div>
          <p className="mt-4 text-xs text-ink-3">
            {paid ? "Received 17.778 GRAM. The store was notified." : "Waiting for the payment"}
          </p>
        </div>
      </div>
    </div>
  );
}
