from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.enums import Asset
from app.domain.matching import IncomingTransfer
from app.infrastructure.ton.address import b64_hash_to_hex, decode_text_comment, to_raw
from app.services.ports import TransferPage

# Plain transfers carry no body or a text comment. Anything else (jetton notifications,
# NFT transfers, excesses) is not a TON payment to us.
_PAYMENT_OPCODES = {None, "0x00000000"}


class ToncenterProvider:
    name = "toncenter"

    def __init__(self, client: httpx.AsyncClient, *, testnet: bool, api_key: str | None = None):
        host = "https://testnet.toncenter.com" if testnet else "https://toncenter.com"
        self._client = client
        self._base = f"{host}/api/v3"
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.get(
            f"{self._base}{path}", params=params, headers=self._headers, timeout=15
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def incoming_ton(
        self, account: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage:
        params: dict[str, Any] = {"account": account, "limit": limit, "sort": "asc"}
        params.update(_window(after_lt, since))
        data = await self._get("/transactions", params)
        txs = data.get("transactions", [])
        result: list[IncomingTransfer] = []
        last_lt = after_lt
        for tx in txs:
            if tx.get("finality", "finalized") != "finalized":
                # Stop here: the cursor must not move past a transaction that can still change.
                return TransferPage(result, last_lt, has_more=False)
            last_lt = int(tx["lt"])
            transfer = self._parse_ton(tx)
            if transfer:
                result.append(transfer)
        return TransferPage(result, last_lt, has_more=len(txs) >= limit)

    def _parse_ton(self, tx: dict[str, Any]) -> IncomingTransfer | None:
        msg = tx.get("in_msg") or {}
        if not msg.get("source") or msg.get("bounced") or msg.get("opcode") not in _PAYMENT_OPCODES:
            return None
        description = tx.get("description") or {}
        # A wallet that is not deployed yet still keeps non-bounceable payments: the transaction
        # is "aborted" (no code to run) but the credit phase holds the money. What matters is
        # whether the value was bounced back, not whether compute ran.
        if description.get("bounce"):
            return None
        credited = (description.get("credit_ph") or {}).get("credit")
        content = msg.get("message_content") or {}
        decoded = content.get("decoded") or {}
        comment = decoded.get("comment") or decode_text_comment(content.get("body"))
        return IncomingTransfer(
            tx_hash=b64_hash_to_hex(tx["hash"]),
            lt=int(tx["lt"]),
            asset=Asset.TON,
            amount=int(credited if credited is not None else msg.get("value") or 0),
            sender=to_raw(msg["source"]),
            recipient=to_raw(tx["account"]),
            comment=comment,
            occurred_at=datetime.fromtimestamp(int(tx["now"]), UTC),
        )

    async def incoming_jettons(
        self, owner: str, jetton_master: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage:
        params: dict[str, Any] = {
            "owner_address": owner,
            "jetton_master": jetton_master,
            "direction": "in",
            "limit": limit,
            "sort": "asc",
        }
        params.update(_window(after_lt, since))
        data = await self._get("/jetton/transfers", params)
        items = data.get("jetton_transfers", [])
        result = []
        last_lt = after_lt
        for item in items:
            last_lt = max(last_lt, int(item["transaction_lt"]))
            if item.get("transaction_aborted"):
                continue
            decoded = item.get("decoded_forward_payload") or {}
            comment = decoded.get("comment") if isinstance(decoded, dict) else None
            result.append(
                IncomingTransfer(
                    tx_hash=b64_hash_to_hex(item["transaction_hash"]),
                    lt=int(item["transaction_lt"]),
                    asset=Asset.USDT,
                    amount=int(item["amount"]),
                    sender=to_raw(item["source"]),
                    recipient=to_raw(item["destination"]),
                    comment=comment or decode_text_comment(item.get("forward_payload")),
                    occurred_at=datetime.fromtimestamp(int(item["transaction_now"]), UTC),
                    jetton_master=to_raw(item["jetton_master"]),
                )
            )
        return TransferPage(result, last_lt, has_more=len(items) >= limit)

    async def jetton_wallet_address(self, owner: str, jetton_master: str) -> str | None:
        data = await self._get(
            "/jetton/wallets", {"owner_address": owner, "jetton_address": jetton_master, "limit": 1}
        )
        wallets = data.get("jetton_wallets") or []
        return to_raw(wallets[0]["address"]) if wallets else None

    async def wallet_public_key(self, address: str) -> bytes | None:
        response = await self._client.post(
            f"{self._base}/runGetMethod",
            json={"address": address, "method": "get_public_key", "stack": []},
            headers=self._headers,
            timeout=15,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
        stack = data.get("stack") or []
        if data.get("exit_code") != 0 or not stack or stack[0].get("type") != "num":
            return None
        return int(stack[0]["value"], 16).to_bytes(32, "big")


def _window(after_lt: int, since: int | None) -> dict[str, int]:
    # A fresh cursor starts from a point in time, otherwise an old wallet would be scanned
    # from its very first transaction.
    if after_lt > 0:
        return {"start_lt": after_lt + 1}
    return {"start_utime": since} if since else {}
