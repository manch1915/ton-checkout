"""Public shapes of our objects. The same models go into API responses and webhook payloads,
so a merchant sees one format everywhere."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.domain.enums import Asset, Channel, InvoiceStatus, Mode, ProductKind
from app.domain.pricing import format_units
from app.infrastructure.db.models import Invoice, Transfer
from app.infrastructure.ton.address import to_friendly


class QuoteView(BaseModel):
    asset: Asset
    amount: str
    units: str
    rate: str | None


class InvoiceView(BaseModel):
    id: str
    object: str = "invoice"
    mode: Mode
    status: InvoiceStatus
    reference: str
    description: str
    order_id: str | None
    product_kind: ProductKind
    channel: Channel
    fiat_amount: Decimal
    fiat_currency: str
    quotes: list[QuoteView]
    asset: Asset | None
    received: str
    overpaid: str
    late: bool
    recipient: str
    payer: str | None
    pay_url: str
    return_url: str | None
    metadata: dict[str, Any]
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime


class TransferView(BaseModel):
    tx_hash: str
    asset: Asset
    amount: str
    sender: str
    comment: str | None
    source: str
    occurred_at: datetime
    explorer_url: str | None


def invoice_view(invoice: Invoice, *, public_url: str, testnet: bool) -> InvoiceView:
    asset = invoice.asset
    quotes = [
        QuoteView(
            asset=Asset(code),
            amount=format_units(int(units), Asset(code)),
            units=str(units),
            rate=invoice.rates.get(code),
        )
        for code, units in invoice.quotes.items()
    ]
    return InvoiceView(
        id=invoice.id,
        mode=invoice.mode,
        status=invoice.status,
        reference=invoice.reference,
        description=invoice.description,
        order_id=invoice.order_id,
        product_kind=invoice.product_kind,
        channel=invoice.channel,
        fiat_amount=invoice.fiat_amount,
        fiat_currency=invoice.fiat_currency,
        quotes=quotes,
        asset=asset,
        received=format_units(int(invoice.received), asset) if asset else "0",
        overpaid=format_units(int(invoice.overpaid), asset) if asset else "0",
        late=invoice.late,
        recipient=to_friendly(invoice.recipient_address, testnet=testnet),
        payer=invoice.payer_address,
        pay_url=f"{public_url}/pay/{invoice.id}",
        return_url=invoice.return_url,
        metadata=invoice.metadata_,
        expires_at=invoice.expires_at,
        paid_at=invoice.paid_at,
        created_at=invoice.created_at,
    )


def transfer_view(transfer: Transfer, *, testnet: bool) -> TransferView:
    explorer = None
    if transfer.source == "chain":
        host = "testnet.tonviewer.com" if testnet else "tonviewer.com"
        explorer = f"https://{host}/transaction/{transfer.tx_hash}"
    return TransferView(
        tx_hash=transfer.tx_hash,
        asset=transfer.asset,
        amount=format_units(int(transfer.amount), transfer.asset),
        sender=to_friendly(transfer.sender, testnet=testnet)
        if transfer.source == "chain"
        else transfer.sender,
        comment=transfer.comment,
        source=transfer.source,
        occurred_at=transfer.occurred_at,
        explorer_url=explorer,
    )
