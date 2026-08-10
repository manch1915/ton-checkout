import "@/polyfills";

import { Address, beginCell, toNano } from "@ton/core";
import type { SendTransactionRequest } from "@tonconnect/ui-react";

import type { PayOption } from "./types";

const VALID_FOR_SECONDS = 5 * 60;
// Covers the jetton transfer and the notification to the merchant; the rest comes back as excess.
const JETTON_GAS = toNano("0.05");

function validUntil(): number {
  return Math.floor(Date.now() / 1000) + VALID_FOR_SECONDS;
}

export function tonTransfer(option: PayOption, recipient: string): SendTransactionRequest {
  return {
    validUntil: validUntil(),
    messages: [
      { address: recipient, amount: option.due_units, payload: option.payload ?? undefined },
    ],
  };
}

/** TEP-74 transfer: sent to the payer's own jetton wallet, which forwards to the merchant. */
export function jettonTransfer(
  option: PayOption,
  recipient: string,
  payer: string,
  payerJettonWallet: string,
  reference: string,
): SendTransactionRequest {
  const comment = beginCell().storeUint(0, 32).storeStringTail(reference).endCell();
  const body = beginCell()
    .storeUint(0x0f8a7ea5, 32)
    .storeUint(BigInt(Date.now()), 64)
    .storeCoins(BigInt(option.due_units))
    .storeAddress(Address.parse(recipient))
    .storeAddress(Address.parse(payer))
    .storeBit(false)
    // At least one nanogram forward, otherwise the merchant wallet gets no notification.
    .storeCoins(1n)
    .storeBit(true)
    .storeRef(comment)
    .endCell();
  return {
    validUntil: validUntil(),
    messages: [
      {
        address: payerJettonWallet,
        amount: JETTON_GAS.toString(),
        payload: body.toBoc().toString("base64"),
      },
    ],
  };
}
