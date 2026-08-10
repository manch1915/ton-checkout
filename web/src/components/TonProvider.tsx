import "@/polyfills";

import { THEME, TonConnectUIProvider } from "@tonconnect/ui-react";
import type { ReactNode } from "react";

/** TON Connect is heavy, so only the pages that talk to wallets mount it. */
export function TonProvider({ children }: { children: ReactNode }) {
  return (
    <TonConnectUIProvider
      manifestUrl={`${window.location.origin}/tonconnect-manifest.json`}
      uiPreferences={{
        theme: document.documentElement.dataset.theme === "dark" ? THEME.DARK : THEME.LIGHT,
      }}
    >
      {children}
    </TonConnectUIProvider>
  );
}
