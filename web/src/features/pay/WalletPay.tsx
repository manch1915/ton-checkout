import { CHAIN, useTonAddress, useTonConnectUI } from "@tonconnect/ui-react";
import { Wallet } from "lucide-react";
import { useState } from "react";

import { TonProvider } from "@/components/TonProvider";
import { Button, Notice } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { amount, assetUnit, shortAddress } from "@/lib/format";
import { jettonTransfer, tonTransfer } from "@/lib/ton";
import type { PayOption, PublicInvoice } from "@/lib/types";

type SendState =
  { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; message: string };

interface Props {
  invoice: PublicInvoice;
  option: PayOption;
}

export default function WalletPayWithProvider(props: Props) {
  return (
    <TonProvider>
      <WalletPay {...props} />
    </TonProvider>
  );
}

function WalletPay({ invoice, option }: Props) {
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
