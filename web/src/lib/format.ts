import type { Asset, InvoiceStatus } from "./types";

// Toncoin was renamed Gram (GRAM) in June 2026. APIs still call it TON, people see "Gram".
export const assetLabel: Record<Asset, string> = { TON: "Gram", USDT: "USDT", XTR: "Stars" };
export const assetUnit: Record<Asset, string> = { TON: "GRAM", USDT: "USDT", XTR: "XTR" };

export const statusLabel: Record<InvoiceStatus, string> = {
  pending: "Waiting for payment",
  partially_paid: "Partly paid",
  paid: "Paid",
  expired: "Expired",
  canceled: "Canceled",
};

export function money(value: string | number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(value));
}

export function amount(value: string | number, digits = 4): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(Number(value));
}

export function shortAddress(address: string, keep = 6): string {
  return address.length <= keep * 2 + 1
    ? address
    : `${address.slice(0, keep)}…${address.slice(-keep)}`;
}

export function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function relative(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const abs = Math.abs(seconds);
  if (abs < 60) return rtf.format(seconds, "second");
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  return rtf.format(Math.round(seconds / 86400), "day");
}

export function countdown(msLeft: number): string {
  const total = Math.max(0, Math.floor(msLeft / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function percent(value: number): string {
  return `${Math.round(value * 1000) / 10}%`;
}
