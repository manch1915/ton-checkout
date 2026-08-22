import "@/polyfills";

import { Address, Cell } from "@ton/core";
import { describe, expect, it } from "vitest";

import { jettonTransfer, tonTransfer } from "./ton";
import type { PayOption } from "./types";

const merchant = "0QD7ya0WKpRYHY4eKNdg4QE9J6CvVw-Ff7XNBAhj6eQOA_ML";
const payer = "0QBkMUiJ2SIdk9e2rhYgL10ZfPJpImuozjBcnnqkDR04tZbY";
const payerJettonWallet = "kQCrq6urq6urq6urq6urq6urq6urq6urq6urq6urq6urq9Dt";

const option = (asset: "TON" | "USDT", due: string): PayOption => ({
  asset,
  amount: "24",
  units: due,
  due_units: due,
  due: "24",
  rate: null,
  deeplink: null,
  payload: "te6cckEBAQEADQAAFgAAAABUQy1YWVo4N9I=",
  jetton_master: null,
  decimals: asset === "TON" ? 9 : 6,
});

describe("tonTransfer", () => {
  it("sends the due amount to the merchant with the comment payload", () => {
    const tx = tonTransfer(option("TON", "17778000000"), merchant);
    expect(tx.messages).toHaveLength(1);
    expect(tx.messages[0]).toMatchObject({ address: merchant, amount: "17778000000" });
    expect(tx.validUntil).toBeGreaterThan(Date.now() / 1000);
  });
});

describe("jettonTransfer", () => {
  it("builds a TEP-74 transfer to the payer's jetton wallet", () => {
    const tx = jettonTransfer(
      option("USDT", "24000000"),
      merchant,
      payer,
      payerJettonWallet,
      "TC-4QX7M2KP",
    );
    const message = tx.messages[0];
    expect(message?.address).toBe(payerJettonWallet);

    const body = Cell.fromBase64(message?.payload ?? "").beginParse();
    expect(body.loadUint(32)).toBe(0x0f8a7ea5);
    body.loadUintBig(64);
    expect(body.loadCoins()).toBe(24_000_000n);
    expect(body.loadAddress().equals(Address.parse(merchant))).toBe(true);
    expect(body.loadAddress().equals(Address.parse(payer))).toBe(true);
    expect(body.loadBit()).toBe(false);
    expect(body.loadCoins()).toBe(1n);
    expect(body.loadBit()).toBe(true);

    const comment = body.loadRef().beginParse();
    expect(comment.loadUint(32)).toBe(0);
    expect(comment.loadStringTail()).toBe("TC-4QX7M2KP");
  });
});
