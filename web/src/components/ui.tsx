import {
  Check,
  CircleDollarSign,
  Copy,
  Diamond,
  LoaderCircle,
  Moon,
  Star,
  Sun,
} from "lucide-react";
import {
  type ButtonHTMLAttributes,
  type ComponentProps,
  type ReactNode,
  forwardRef,
  useState,
} from "react";

import { assetLabel, statusLabel } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import type { Asset, InvoiceStatus } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-strong shadow-sm",
  secondary: "bg-surface text-ink border border-line hover:border-line-strong",
  ghost: "text-ink-2 hover:text-ink hover:bg-surface-2",
  danger: "bg-surface text-danger border border-line hover:border-danger",
};

type Size = "sm" | "md" | "lg";
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 gap-2",
  lg: "h-12 px-5 text-base gap-2",
};

/** Button look for links, so navigation stays an <a> instead of a button inside a link. */
export function buttonClass(
  variant: Variant = "primary",
  size: Size = "md",
  extra?: string,
): string {
  return cx(
    "inline-flex items-center justify-center rounded-lg font-medium transition-[background,border,color,transform] duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
    sizes[size],
    variants[variant],
    extra,
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", busy, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={buttonClass(variant, size, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

const statusTone: Record<InvoiceStatus, string> = {
  pending: "bg-accent-soft text-accent-strong",
  partially_paid: "bg-warn-soft text-warn",
  paid: "bg-paid-soft text-paid",
  expired: "bg-surface-2 text-ink-3",
  canceled: "bg-surface-2 text-ink-3",
};

export function StatusBadge({ status, short }: { status: InvoiceStatus; short?: boolean }) {
  const text = short && status === "pending" ? "Pending" : statusLabel[status];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        statusTone[status],
      )}
    >
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {text}
    </span>
  );
}

export function AssetIcon({ asset, className }: { asset: Asset; className?: string }) {
  const props = { className: cx("size-4 shrink-0", className), "aria-hidden": true } as const;
  if (asset === "TON") return <Diamond {...props} />;
  if (asset === "USDT") return <CircleDollarSign {...props} />;
  return <Star {...props} />;
}

export function AssetTag({ asset }: { asset: Asset }) {
  return (
    <span className="inline-flex items-center gap-1 text-ink-2">
      <AssetIcon asset={asset} className={asset === "XTR" ? "text-stars" : undefined} />
      {assetLabel[asset]}
    </span>
  );
}

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        } catch {
          // Clipboard can be blocked inside some webviews; the value is still selectable.
        }
      }}
      className="inline-flex size-8 items-center justify-center rounded-md text-ink-3 hover:bg-surface hover:text-ink"
      aria-label={copied ? `${label} copied` : `Copy ${label}`}
    >
      {copied ? <Check className="size-4 text-paid" /> : <Copy className="size-4" />}
    </button>
  );
}

export function Panel({ className, ...rest }: ComponentProps<"section">) {
  return (
    <section
      className={cx("rounded-2xl border border-line bg-surface shadow-panel", className)}
      {...rest}
    />
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-ink-3">
      <LoaderCircle className="size-4 animate-spin" aria-hidden />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-surface-2", className)} aria-hidden />;
}

export function Notice({
  tone = "info",
  title,
  children,
  action,
}: {
  tone?: "info" | "warn" | "danger" | "success";
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const tones = {
    info: "border-accent/25 bg-accent-soft",
    warn: "border-warn/30 bg-warn-soft",
    danger: "border-danger/30 bg-danger-soft",
    success: "border-paid/30 bg-paid-soft",
  };
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cx("rounded-xl border px-4 py-3 text-sm", tones[tone])}
    >
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-0.5 text-ink-2">{children}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <p className="font-medium">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-ink-3">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ThemeToggle() {
  const [theme, toggle] = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      className="inline-flex size-9 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink"
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "h-10 w-full rounded-lg border border-line bg-surface px-3 text-ink placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20";
