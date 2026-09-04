"""Parsing real toncenter v3 responses, shapes copied from testnet."""

import base64

import httpx
import respx

from app.domain.enums import Asset
from app.infrastructure.ton.toncenter import ToncenterProvider

MERCHANT = "0:fbc9ad162a94581d8e1e28d760e1013d27a0af570f857fb5cd040863e9e40e03"
PAYER = "0:64314889D9221D93D7B6AE16202F5D197CF269226BA8CE305C9E7AA40D1D38B5"


def _tx(
    lt: int,
    *,
    value: str,
    comment: str | None,
    description: dict,
    opcode: str = "0x00000000",
    bounced: bool = False,
) -> dict:
    return {
        "account": MERCHANT,
        "hash": base64.b64encode(lt.to_bytes(32, "big")).decode(),
        "lt": str(lt),
        "now": 1792439178,
        "finality": "finalized",
        "description": description,
        "in_msg": {
            "source": PAYER,
            "value": value,
            "opcode": opcode,
            "bounced": bounced,
            "message_content": {
                "decoded": {"type": "text_comment", "comment": comment} if comment else None
            },
        },
    }


UNINIT_CREDIT = {
    "type": "ord",
    "aborted": True,
    "credit_ph": {"credit": "740000000"},
    "compute_ph": {"skipped": True, "reason": "no_state"},
}
BOUNCED_BACK = {"type": "ord", "aborted": True, "bounce": {"type": "ok"}}


@respx.mock
async def test_payment_to_undeployed_wallet_is_counted() -> None:
    """Regression: the first payments to a fresh wallet are 'aborted' yet credited."""
    respx.get("https://testnet.toncenter.com/api/v3/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transactions": [
                    _tx(10, value="740000000", comment="TC-DGA1H1A2", description=UNINIT_CREDIT),
                    _tx(11, value="500000000", comment="TC-XXXXXXXX", description=BOUNCED_BACK),
                    _tx(
                        12,
                        value="1",
                        comment=None,
                        description={"aborted": False},
                        opcode="0x7362d09c",
                    ),
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        page = await ToncenterProvider(client, testnet=True).incoming_ton(MERCHANT, 0, 50)

    assert [t.comment for t in page.items] == ["TC-DGA1H1A2"]
    assert page.items[0].amount == 740_000_000
    assert page.items[0].asset is Asset.TON
    assert page.last_lt == 12  # skipped transactions still move the cursor


@respx.mock
async def test_stops_before_unfinalized_transaction() -> None:
    pending = _tx(21, value="1000", comment="TC-AAAAAAAA", description={"aborted": False})
    pending["finality"] = "pending"
    respx.get("https://testnet.toncenter.com/api/v3/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transactions": [
                    _tx(20, value="1000", comment="TC-BBBBBBBB", description={"aborted": False}),
                    pending,
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        page = await ToncenterProvider(client, testnet=True).incoming_ton(MERCHANT, 0, 50)
    assert [t.lt for t in page.items] == [20]
    assert page.last_lt == 20
    assert not page.has_more
