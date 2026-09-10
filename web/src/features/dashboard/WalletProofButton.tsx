import { Wallet } from "lucide-react";

import { TonProvider } from "@/components/TonProvider";
import { Button, Notice } from "@/components/ui";

import { type ProofBody, useWalletProof } from "./useWalletProof";

interface Props {
  label: string;
  variant?: "primary" | "secondary";
  errorTitle: string;
  onProof: (body: ProofBody) => Promise<void>;
}

/** Loaded lazily: TON Connect is only fetched on pages that actually show this button. */
export default function WalletProofButton(props: Props) {
  return (
    <TonProvider>
      <ProofButton {...props} />
    </TonProvider>
  );
}

function ProofButton({ label, variant = "primary", errorTitle, onProof }: Props) {
  const wallet = useWalletProof(onProof);
  return (
    <div className="space-y-3">
      <Button
        size="lg"
        variant={variant}
        className="w-full"
        onClick={wallet.start}
        busy={wallet.busy}
        icon={<Wallet className="size-4" />}
      >
        {label}
      </Button>
      {wallet.error && (
        <Notice tone="danger" title={errorTitle}>
          {wallet.error}
        </Notice>
      )}
    </div>
  );
}
