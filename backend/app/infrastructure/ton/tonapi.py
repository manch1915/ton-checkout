import base64
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.enums import Asset
from app.domain.matching import IncomingTransfer
from app.infrastructure.ton.address import decode_text_comment, to_raw
from app.services.ports import TransferPage


class TonApiProvider:
    """TonAPI v2. Note: jetton history is keyed by event id, toncenter by transaction hash,
    so switching providers on a live database may report the same jetton payment twice."""

    name = "tonapi"

    def __init__(self, client: httpx.AsyncClient, *, testnet: bool, api_key: str | None = None):
        self._client = client
        self._base = "https://testnet.tonapi.io/v2" if testnet else "https://tonapi.io/v2"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

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
        data = await self._get(
            f"/blockchain/accounts/{account}/transactions",
            {"after_lt": after_lt, "limit": limit, "sort_order": "asc"},
        )
        min_time = since if after_lt == 0 and since else 0
        txs = data.get("transactions", [])
        result = []
        last_lt = after_lt
        for tx in txs:
            last_lt = max(last_lt, int(tx["lt"]))
            msg = tx.get("in_msg") or {}
            if (
                int(tx.get("utime", 0)) < min_time
                or msg.get("msg_type") != "int_msg"
                or msg.get("bounced")
                or tx.get("aborted")
                or msg.get("op_code") not in (None, "0x00000000")
            ):
                continue
            body = msg.get("decoded_body") or {}
            comment = body.get("text") or decode_text_comment(_hex_boc_to_b64(msg.get("raw_body")))
            result.append(
                IncomingTransfer(
                    tx_hash=tx["hash"],
                    lt=int(tx["lt"]),
                    asset=Asset.TON,
                    amount=int(msg.get("value") or 0),
                    sender=to_raw(msg["source"]["address"]),
                    recipient=to_raw(tx["account"]["address"]),
                    comment=comment,
                    occurred_at=datetime.fromtimestamp(int(tx["utime"]), UTC),
                )
            )
        return TransferPage(result, last_lt, has_more=len(txs) >= limit)

    async def incoming_jettons(
        self, owner: str, jetton_master: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage:
        # History is newest first, so we read one page and keep what is past the cursor.
        data = await self._get(
            f"/accounts/{owner}/jettons/{jetton_master}/history", {"limit": limit}
        )
        owner_raw = to_raw(owner)
        result = []
        last_lt = after_lt
        for event in data.get("events", []):
            lt = int(event.get("lt", 0))
            last_lt = max(last_lt, lt)
            if lt <= after_lt or (since and int(event.get("timestamp", 0)) < since):
                continue
            for action in event.get("actions", []):
                info = action.get("JettonTransfer")
                if action.get("status") != "ok" or not info:
                    continue
                recipient = to_raw(info["recipient"]["address"]) if info.get("recipient") else None
                if recipient != owner_raw:
                    continue
                result.append(
                    IncomingTransfer(
                        tx_hash=event["event_id"],
                        lt=lt,
                        asset=Asset.USDT,
                        amount=int(info["amount"]),
                        sender=to_raw(info["sender"]["address"]) if info.get("sender") else "",
                        recipient=recipient,
                        comment=info.get("comment"),
                        occurred_at=datetime.fromtimestamp(int(event["timestamp"]), UTC),
                        jetton_master=to_raw(info["jetton"]["address"]),
                    )
                )
        return TransferPage(sorted(result, key=lambda t: t.lt), last_lt, has_more=False)

    async def jetton_wallet_address(self, owner: str, jetton_master: str) -> str | None:
        try:
            data = await self._get(f"/accounts/{owner}/jettons/{jetton_master}", {})
        except httpx.HTTPStatusError:
            return None
        wallet = (data.get("wallet_address") or {}).get("address")
        return to_raw(wallet) if wallet else None

    async def wallet_public_key(self, address: str) -> bytes | None:
        try:
            data = await self._get(f"/wallet/{address}/get-account-public-key", {})
        except httpx.HTTPStatusError:
            return None
        key = data.get("public_key")
        return bytes.fromhex(key) if key else None


def _hex_boc_to_b64(raw: str | None) -> str | None:
    if not raw:
        return None
    return base64.b64encode(bytes.fromhex(raw)).decode()
