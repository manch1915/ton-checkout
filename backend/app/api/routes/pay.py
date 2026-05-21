"""Endpoints behind the buyer's payment page.

No auth: knowing the invoice id is enough to pay it, the same as a payment link.
"""

import asyncio
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, SessionDep, rate_limit
from app.domain.enums import Asset, InvoiceStatus, Mode
from app.domain.matching import IncomingTransfer
from app.domain.pricing import format_units
from app.infrastructure.db.models import Invoice, new_id
from app.infrastructure.telegram import create_stars_link
from app.infrastructure.ton.address import comment_payload, is_valid, to_friendly, to_raw
from app.services.events import invoice_channel
from app.services.payments import Outcome, TransferSource
from app.services.stars import StarsError
from app.services.views import TransferView, transfer_view

router = APIRouter(prefix="/api/pay", tags=["payment page"], dependencies=[Depends(rate_limit)])

HEARTBEAT_SECONDS = 15


class PayOption(BaseModel):
    asset: Asset
    amount: str
    units: str
    due_units: str
    due: str
    rate: str | None
    deeplink: str | None
    payload: str | None
    jetton_master: str | None = None
    decimals: int


class PublicInvoice(BaseModel):
    id: str
    status: InvoiceStatus
    mode: Mode
    network: str
    merchant: str
    description: str
    fiat_amount: Decimal
    fiat_currency: str
    reference: str
    recipient: str
    asset: Asset | None
    options: list[PayOption]
    received: str
    overpaid: str
    late: bool
    expires_at: datetime
    paid_at: datetime | None
    return_url: str | None
    transfers: list[TransferView]
    server_time: datetime


class JettonWalletRequest(BaseModel):
    owner: str = Field(max_length=80)


class JettonWalletResponse(BaseModel):
    jetton_wallet: str


class SimulateRequest(BaseModel):
    asset: Asset = Asset.TON
    # Share of the due amount, so the sandbox can show underpayment and overpayment too.
    fraction: Decimal = Field(default=Decimal(1), gt=0, le=2)


class SimulateResponse(BaseModel):
    outcome: Outcome
    status: InvoiceStatus | None


def _deeplink(invoice: Invoice, asset: Asset, due: int, master: str | None, testnet: bool) -> str:
    to = to_friendly(invoice.recipient_address, testnet=testnet)
    text = quote(invoice.reference)
    if asset is Asset.TON:
        return f"ton://transfer/{to}?amount={due}&text={text}"
    jetton = to_friendly(master or "", testnet=testnet, bounceable=True)
    return f"ton://transfer/{to}?jetton={jetton}&amount={due}&text={text}"


async def build_public(
    invoice: Invoice, container: ContainerDep, session: SessionDep
) -> PublicInvoice:
    testnet = container.settings.is_testnet
    master = container.usdt_master
    options = []
    for code in invoice.quotes:
        asset = Asset(code)
        if invoice.asset is not None and asset is not invoice.asset:
            continue
        units = invoice.quote(asset) or 0
        due = max(0, units - (int(invoice.received) if invoice.asset is asset else 0))
        on_chain = asset.on_chain and due > 0
        options.append(
            PayOption(
                asset=asset,
                amount=format_units(units, asset),
                units=str(units),
                due_units=str(due),
                due=format_units(due, asset),
                rate=invoice.rates.get(code),
                deeplink=_deeplink(invoice, asset, due, master, testnet) if on_chain else None,
                payload=comment_payload(invoice.reference) if on_chain else None,
                jetton_master=to_friendly(master, testnet=testnet, bounceable=True)
                if asset is Asset.USDT and master
                else None,
                decimals=asset.decimals,
            )
        )
    transfers = await container.invoices(session).transfers(invoice.id)
    locked = invoice.asset
    return PublicInvoice(
        id=invoice.id,
        status=invoice.status,
        mode=invoice.mode,
        network=container.settings.ton_network,
        merchant=invoice.merchant.name,
        description=invoice.description,
        fiat_amount=invoice.fiat_amount,
        fiat_currency=invoice.fiat_currency,
        reference=invoice.reference,
        recipient=to_friendly(invoice.recipient_address, testnet=testnet),
        asset=locked,
        options=options,
        received=format_units(int(invoice.received), locked) if locked else "0",
        overpaid=format_units(int(invoice.overpaid), locked) if locked else "0",
        late=invoice.late,
        expires_at=invoice.expires_at,
        paid_at=invoice.paid_at,
        return_url=invoice.return_url,
        transfers=[transfer_view(t, testnet=testnet) for t in transfers],
        server_time=datetime.now(UTC),
    )


async def _load(invoice_id: str, container: ContainerDep, session: SessionDep) -> Invoice:
    invoice = await container.invoices(session).get(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return invoice


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str, container: ContainerDep, session: SessionDep
) -> PublicInvoice:
    return await build_public(await _load(invoice_id, container, session), container, session)


@router.get("/{invoice_id}/events", response_class=EventSourceResponse)
async def invoice_events(
    invoice_id: str, container: ContainerDep, session: SessionDep
) -> AsyncIterable[ServerSentEvent]:
    invoice = await _load(invoice_id, container, session)
    snapshot = await build_public(invoice, container, session)
    await session.close()
    yield ServerSentEvent(data=snapshot.model_dump(mode="json"), event="snapshot")

    stream = container.bus.subscribe(invoice_channel(invoice_id)).__aiter__()
    pending: asyncio.Task[dict[str, Any]] | None = None
    try:
        while True:
            pending = pending or asyncio.ensure_future(anext(stream))
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_SECONDS)
            if not done:
                yield ServerSentEvent(comment="ping")
                continue
            message = pending.result()
            pending = None
            async with container.sessions() as fresh:
                current = await fresh.get(Invoice, invoice_id)
                if current is not None:
                    public = await build_public(current, container, fresh)
                    yield ServerSentEvent(
                        data=public.model_dump(mode="json"), event=message["type"]
                    )
    finally:
        if pending is not None:
            pending.cancel()


@router.post("/{invoice_id}/jetton-wallet")
async def payer_jetton_wallet(
    invoice_id: str, body: JettonWalletRequest, container: ContainerDep, session: SessionDep
) -> JettonWalletResponse:
    """A jetton transfer is sent to the payer's own jetton wallet, so the page needs its address."""
    await _load(invoice_id, container, session)
    master = container.usdt_master
    if not master:
        raise HTTPException(status.HTTP_409_CONFLICT, "USDT is not configured")
    if not is_valid(body.owner):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid wallet address")
    wallet = await container.provider.jetton_wallet_address(to_raw(body.owner), master)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this wallet holds no test USDT yet")
    return JettonWalletResponse(
        jetton_wallet=to_friendly(wallet, testnet=container.settings.is_testnet, bounceable=True)
    )


@router.post("/{invoice_id}/simulate")
async def simulate_payment(
    invoice_id: str, body: SimulateRequest, container: ContainerDep, session: SessionDep
) -> SimulateResponse:
    """Sandbox payment for test-mode invoices. Goes through the same processor as chain payments."""
    invoice = await _load(invoice_id, container, session)
    if invoice.mode is not Mode.TEST:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "simulation works for test-mode invoices only"
        )
    units = invoice.quote(body.asset)
    if units is None or not body.asset.on_chain:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{body.asset} is not on this invoice"
        )
    due = units - (int(invoice.received) if invoice.asset is body.asset else 0)
    amount = int((Decimal(max(due, 1)) * body.fraction).to_integral_value())
    transfer = IncomingTransfer(
        tx_hash=new_id("sandbox"),
        lt=0,
        asset=body.asset,
        amount=amount,
        sender="sandbox",
        recipient=invoice.recipient_address,
        comment=invoice.reference,
        occurred_at=datetime.now(UTC),
    )
    result = await container.processor(session).process(transfer, TransferSource.SANDBOX)
    return SimulateResponse(outcome=result.outcome, status=result.status)


class StarsLinkResponse(BaseModel):
    url: str


@router.post("/{invoice_id}/stars-link")
async def stars_link(
    invoice_id: str, container: ContainerDep, session: SessionDep
) -> StarsLinkResponse:
    """Invoice link for `Telegram.WebApp.openInvoice`. Works only inside Telegram."""
    invoice = await _load(invoice_id, container, session)
    if container.bot is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "the Telegram bot is not configured"
        )
    if not invoice.status.is_open:
        raise HTTPException(status.HTTP_409_CONFLICT, f"invoice is {invoice.status}")
    try:
        url = await create_stars_link(container.bot, invoice)
    except StarsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return StarsLinkResponse(url=url)
