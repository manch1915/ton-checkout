"""Telegram Stars side of the checkout. The invoice payload is our invoice id."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Asset
from app.domain.matching import IncomingTransfer
from app.infrastructure.db.models import Invoice
from app.services.payments import PaymentProcessor, ProcessResult, TransferSource


class StarsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class StarsCharge:
    invoice_id: str
    amount: int
    charge_id: str
    user_id: int


async def check_pre_checkout(
    session: AsyncSession, invoice_id: str, amount: int, currency: str
) -> None:
    """Telegram waits 10 seconds for this answer, so it only does cheap lookups."""
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise StarsError("This order no longer exists.")
    if not invoice.status.is_open:
        raise StarsError("This order is already closed.")
    if invoice.expires_at < datetime.now(UTC):
        raise StarsError("This order has expired. Please start over.")
    if currency != Asset.STARS.value or invoice.quote(Asset.STARS) != amount:
        raise StarsError("The price has changed. Please start over.")


async def record_charge(
    processor: PaymentProcessor, invoice: Invoice, charge: StarsCharge
) -> ProcessResult:
    transfer = IncomingTransfer(
        tx_hash=f"stars:{charge.charge_id}",
        lt=0,
        asset=Asset.STARS,
        amount=charge.amount,
        sender=f"tg:{charge.user_id}",
        recipient=invoice.recipient_address,
        comment=invoice.reference,
        occurred_at=datetime.now(UTC),
    )
    return await processor.process(transfer, TransferSource.STARS)
