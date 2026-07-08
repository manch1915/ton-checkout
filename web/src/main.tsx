import "./polyfills";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { THEME, TonConnectUIProvider } from "@tonconnect/ui-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";

import { router } from "./router";
import { applyTheme } from "./lib/theme";
import { loadTelegramScript, telegram } from "./lib/telegram";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false } },
});

async function boot() {
  const params = new URLSearchParams(window.location.search);
  // Inside Telegram the Mini App follows the client's theme.
  if (params.get("source") === "telegram" || window.location.hash.includes("tgWebAppData")) {
    await loadTelegramScript();
    const app = telegram();
    if (app) {
      app.ready();
      app.expand();
      applyTheme(app.colorScheme);
    }
  }

  const root = document.getElementById("root");
  if (!root) return;
  createRoot(root).render(
    <StrictMode>
      <TonConnectUIProvider
        manifestUrl={`${window.location.origin}/tonconnect-manifest.json`}
        uiPreferences={{
          theme: document.documentElement.dataset.theme === "dark" ? THEME.DARK : THEME.LIGHT,
        }}
      >
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </TonConnectUIProvider>
    </StrictMode>,
  );
}

void boot();
