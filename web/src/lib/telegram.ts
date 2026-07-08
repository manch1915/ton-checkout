// Minimal typing for the parts of Telegram.WebApp we use. The script is loaded only
// when the page runs inside Telegram, so every call is guarded.
interface WebApp {
  initData: string;
  colorScheme: "light" | "dark";
  ready(): void;
  expand(): void;
  openInvoice(
    url: string,
    callback?: (status: "paid" | "cancelled" | "failed" | "pending") => void,
  ): void;
  openLink(url: string): void;
  HapticFeedback?: { notificationOccurred(type: "success" | "error" | "warning"): void };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: WebApp };
  }
}

export function telegram(): WebApp | null {
  const app = window.Telegram?.WebApp;
  return app && app.initData ? app : null;
}

export function isTelegram(): boolean {
  return telegram() !== null;
}

let loading: Promise<void> | null = null;

export function loadTelegramScript(): Promise<void> {
  if (window.Telegram?.WebApp) return Promise.resolve();
  loading ??= new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-web-app.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => resolve();
    document.head.appendChild(script);
  });
  return loading;
}

export function openStarsInvoice(
  url: string,
): Promise<"paid" | "cancelled" | "failed" | "pending"> {
  return new Promise((resolve) => {
    const app = telegram();
    if (!app) {
      resolve("failed");
      return;
    }
    app.openInvoice(url, resolve);
  });
}
