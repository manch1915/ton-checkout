"""Testnet helpers: demo wallets, a test USDT jetton and paying an invoice from a real wallet.

    uv run --group tools python -m tools.testnet wallets
    uv run --group tools python -m tools.testnet deploy-jetton
    uv run --group tools python -m tools.testnet mint --to <address> --amount 500
    uv run --group tools python -m tools.testnet pay <invoice_id> --asset TON

Mnemonics are kept in .testnet-wallets.json next to this file. It is git-ignored and must stay
that way: these are throwaway testnet keys, but keys all the same.
"""

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from ton_core import (
    Address,
    JettonInternalTransferBody,
    JettonMasterStandardData,
    JettonStandardMintBody,
    JettonTopUpBody,
    NetworkGlobalID,
    OnchainContent,
    to_nano,
)
from tonutils.clients import ToncenterClient
from tonutils.contracts import (
    JettonMasterStandard,
    JettonTransferBuilder,
    JettonWalletStandard,
    WalletV5R1,
)

STORE = Path(__file__).with_name(".testnet-wallets.json")
USDT_DECIMALS = 6
JETTON_METADATA = {
    "name": "Test USD (TON Checkout)",
    "symbol": "tUSDT",
    "decimals": str(USDT_DECIMALS),
    "description": "Testnet stand-in for USDT used by the TON Checkout demo. No value.",
}


def _load() -> dict[str, Any]:
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}


def _save(data: dict[str, Any]) -> None:
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _client() -> ToncenterClient:
    # Keyless toncenter allows about one request per second per IP.
    return ToncenterClient(network=NetworkGlobalID.TESTNET, rps_limit=1, rps_period=2)


def _wallet(client: ToncenterClient, role: str) -> WalletV5R1:
    words = _load()[role]["mnemonic"]
    wallet, _, _, _ = WalletV5R1.from_mnemonic(client, words)
    return wallet


async def cmd_wallets(_: argparse.Namespace) -> None:
    data = _load()
    client = _client()
    for role in ("merchant", "payer"):
        if role not in data:
            wallet, _, _, words = WalletV5R1.create(client)
            data[role] = {"mnemonic": " ".join(words)}
        else:
            wallet = _wallet(client, role)
        data[role]["address"] = wallet.address.to_str(is_bounceable=False, is_test_only=True)
        print(f"{role:9} {data[role]['address']}")
    _save(data)


async def cmd_deploy_jetton(_: argparse.Namespace) -> None:
    async with Connected() as client:
        payer = _wallet(client, "payer")
        master_data = JettonMasterStandardData(
            admin_address=payer.address,
            content=OnchainContent(JETTON_METADATA),
            jetton_wallet_code=JettonWalletStandard.get_default_code(),
        )
        master = JettonMasterStandard.from_data(client=client, data=master_data.serialize())
        await payer.transfer(
            destination=master.address,
            amount=to_nano(0.05),
            body=JettonTopUpBody().serialize(),
            state_init=master.state_init,
        )
        data = _load()
        data["jetton_master"] = master.address.to_str(is_bounceable=True, is_test_only=True)
        _save(data)
        print(f"jetton master {data['jetton_master']}  (set USDT_JETTON_MASTER to this)")


async def cmd_mint(args: argparse.Namespace) -> None:
    async with Connected() as client:
        payer = _wallet(client, "payer")
        body = JettonStandardMintBody(
            internal_transfer=JettonInternalTransferBody(
                jetton_amount=to_nano(Decimal(args.amount), decimals=USDT_DECIMALS),
                response_address=payer.address,
                forward_amount=1,
            ),
            destination=Address(args.to),
            forward_amount=to_nano(0.05),
        )
        await payer.transfer(
            destination=Address(_load()["jetton_master"]),
            amount=to_nano(0.08),
            body=body.serialize(),
        )
        print(f"minted {args.amount} tUSDT to {args.to}")


async def cmd_pay(args: argparse.Namespace) -> None:
    async with httpx.AsyncClient(timeout=15) as http:
        invoice = (await http.get(f"{args.api}/api/pay/{args.invoice_id}")).json()
    option = next(o for o in invoice["options"] if o["asset"] == args.asset)
    units = int(Decimal(option["due_units"]) * Decimal(args.fraction))
    async with Connected() as client:
        payer = _wallet(client, "payer")
        if args.asset == "TON":
            msg = await payer.transfer(
                destination=Address(invoice["recipient"]), amount=units, body=invoice["reference"]
            )
        else:
            msg = await payer.transfer_message(
                JettonTransferBuilder(
                    destination=Address(invoice["recipient"]),
                    jetton_amount=units,
                    jetton_master_address=Address(option["jetton_master"]),
                    forward_payload=invoice["reference"],
                    forward_amount=1,
                    amount=to_nano(0.05),
                )
            )
        print(f"sent {units} units of {args.asset}, message hash {msg.normalized_hash}")


class Connected:
    async def __aenter__(self) -> ToncenterClient:
        self.client = _client()
        await self.client.connect()
        return self.client

    async def __aexit__(self, *exc: object) -> None:
        await self.client.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="testnet")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("wallets").set_defaults(fn=cmd_wallets)
    sub.add_parser("deploy-jetton").set_defaults(fn=cmd_deploy_jetton)
    mint = sub.add_parser("mint")
    mint.add_argument("--to", required=True)
    mint.add_argument("--amount", default="500")
    mint.set_defaults(fn=cmd_mint)
    pay = sub.add_parser("pay")
    pay.add_argument("invoice_id")
    pay.add_argument("--asset", choices=["TON", "USDT"], default="TON")
    pay.add_argument("--fraction", default="1")
    pay.add_argument("--api", default="http://localhost:8010")
    pay.set_defaults(fn=cmd_pay)
    args = parser.parse_args()
    asyncio.run(args.fn(args))


if __name__ == "__main__":
    main()
