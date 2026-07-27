import { useTonConnectUI } from "@tonconnect/ui-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

export interface ProofBody {
  address: string;
  network: string;
  proof: {
    timestamp: number;
    domain: { lengthBytes: number; value: string };
    payload: string;
    signature: string;
    state_init?: string;
  };
}

/**
 * Connect a wallet with a ton_proof attached and hand the signed proof to `onProof`.
 * The backend issues a one-time payload first, so a captured proof cannot be replayed.
 */
export function useWalletProof(onProof: (body: ProofBody) => Promise<void>) {
  const [tonConnectUI] = useTonConnectUI();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const waiting = useRef(false);
  const handler = useRef(onProof);

  useEffect(() => {
    handler.current = onProof;
  }, [onProof]);

  useEffect(
    () =>
      tonConnectUI.onStatusChange(async (wallet) => {
        if (!waiting.current || !wallet) return;
        const proof = wallet.connectItems?.tonProof;
        waiting.current = false;
        if (!proof || !("proof" in proof)) {
          setError("This wallet did not sign the login request. Try another wallet.");
          setBusy(false);
          return;
        }
        try {
          await handler.current({
            address: wallet.account.address,
            network: wallet.account.chain,
            proof: { ...proof.proof, state_init: wallet.account.walletStateInit },
          });
        } catch (e) {
          setError(e instanceof Error ? e.message : "Sign-in failed.");
        } finally {
          setBusy(false);
          // The session lives in our cookie, the wallet link is not needed anymore.
          await tonConnectUI.disconnect().catch(() => undefined);
        }
      }),
    [tonConnectUI],
  );

  const start = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      if (tonConnectUI.connected) await tonConnectUI.disconnect();
      tonConnectUI.setConnectRequestParameters({ state: "loading" });
      const { payload } = await api.post<{ payload: string }>("/api/auth/ton-proof/payload");
      tonConnectUI.setConnectRequestParameters({ state: "ready", value: { tonProof: payload } });
      waiting.current = true;
      await tonConnectUI.openModal();
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "Could not start the wallet connection.");
    }
  }, [tonConnectUI]);

  useEffect(
    () =>
      tonConnectUI.onModalStateChange((state) => {
        if (state.status === "closed" && !tonConnectUI.connected) {
          waiting.current = false;
          setBusy(false);
        }
      }),
    [tonConnectUI],
  );

  return { start, busy, error };
}
