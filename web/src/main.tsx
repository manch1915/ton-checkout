import "./index.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";

import { queryClient } from "./lib/queryClient";
import { router } from "./router";
import { applyTheme } from "./lib/theme";
import { loadTelegramScript, telegram } from "./lib/telegram";

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
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
}

void boot();
