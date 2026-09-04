from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Asset, InvoiceStatus
from app.domain.matching import IncomingTransfer, InvoiceState, apply_transfer, normalize_comment
from app.infrastructure.db.models import Invoice, Transfer
from app.services.events import EventRecorder

log = structlog.get_logger()

DUST_NOTE = "dust"


def note_has_ref(note: str | None) -> bool:
    return bool(note and note.startswith("unknown reference"))


class TransferSource(StrEnum):
    CHAIN = "chain"
    SANDBOX = "sandbox"
    STARS = "stars"


class Outcome(StrEnum):
    DUPLICATE = "duplicate"
    MATCHED = "matched"
    UNMATCHED = "unmatched"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    outcome: Outcome
    invoice_id: str | None = None
    status: InvoiceStatus | None = None
    note: str | None = None


class PaymentProcessor:
    """Turns an incoming transfer into invoice state. Safe to call twice with the same transfer."""

    def __init__(
        self,
        session: AsyncSession,
        events: EventRecorder,
        *,
        usdt_master: str | None,
        tolerance_nano: int,
        dust_nano: int = 0,
    ):
        self._session = session
        self._events = events
        self._usdt_master = usdt_master
        self._tolerance = tolerance_nano
        self._dust = dust_nano

    async def process(self, transfer: IncomingTransfer, source: TransferSource) -> ProcessResult:
        inserted = await self._session.scalar(
            insert(Transfer)
            .values(
                tx_hash=transfer.tx_hash,
                lt=transfer.lt,
                asset=transfer.asset,
                amount=Decimal(transfer.amount),
                sender=transfer.sender,
                recipient=transfer.recipient,
                comment=transfer.comment,
                jetton_master=transfer.jetton_master,
                source=source.value,
                occurred_at=transfer.occurred_at,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["tx_hash"])
            .returning(Transfer.id)
        )
        if inserted is None:
            await self._session.rollback()
            return ProcessResult(Outcome.DUPLICATE)

        row = await self._session.get_one(Transfer, inserted)
        invoice, note = await self._find_invoice(transfer, source)
        if invoice is None:
            if (
                transfer.asset is Asset.TON
                and transfer.amount < self._dust
                and not note_has_ref(note)
            ):
                note = DUST_NOTE
            row.note = note
            await self._session.commit()
            log.info("payment.unmatched", tx=transfer.tx_hash, note=note)
            return ProcessResult(Outcome.UNMATCHED, note=note)

        row.invoice_id = invoice.id
        await self._apply(invoice, transfer, source)
        await self._events.commit_and_publish()
        log.info("payment.matched", tx=transfer.tx_hash, invoice=invoice.id, status=invoice.status)
        return ProcessResult(Outcome.MATCHED, invoice.id, invoice.status)

    async def assign(self, transfer_id: int, invoice_id: str, merchant_id: str) -> ProcessResult:
        """Manual recovery for a payment that came without a usable comment."""
        row = await self._session.get(Transfer, transfer_id, with_for_update=True)
        invoice = await self._session.get(Invoice, invoice_id, with_for_update=True)
        if row is None or invoice is None or invoice.merchant_id != merchant_id:
            return ProcessResult(Outcome.UNMATCHED, note="payment or invoice not found")
        if row.invoice_id is not None:
            return ProcessResult(Outcome.DUPLICATE, row.invoice_id, note="already assigned")
        if row.recipient != invoice.recipient_address:
            return ProcessResult(Outcome.UNMATCHED, note="payment went to a different wallet")
        if invoice.quote(row.asset) is None or invoice.asset not in (None, row.asset):
            return ProcessResult(Outcome.UNMATCHED, note=f"invoice does not accept {row.asset}")
        transfer = IncomingTransfer(
            tx_hash=row.tx_hash,
            lt=row.lt,
            asset=row.asset,
            amount=int(row.amount),
            sender=row.sender,
            recipient=row.recipient,
            comment=row.comment,
            occurred_at=row.occurred_at,
            jetton_master=row.jetton_master,
        )
        row.invoice_id = invoice.id
        row.note = "assigned manually"
        await self._apply(invoice, transfer, TransferSource(row.source))
        await self._events.commit_and_publish()
        return ProcessResult(Outcome.MATCHED, invoice.id, invoice.status)

    async def _find_invoice(
        self, transfer: IncomingTransfer, source: TransferSource
    ) -> tuple[Invoice | None, str | None]:
        reference = normalize_comment(transfer.comment)
        if reference is None:
            return None, "no invoice reference in comment"
        invoice = await self._session.scalar(
            select(Invoice).where(Invoice.reference == reference).with_for_update()
        )
        if invoice is None:
            return None, f"unknown reference {reference}"
        if source is TransferSource.SANDBOX and invoice.mode != "test":
            return None, "sandbox payments are accepted for test invoices only"
        if source is TransferSource.CHAIN and transfer.recipient != invoice.recipient_address:
            return None, "paid to a different wallet"
        if (
            transfer.asset is Asset.USDT
            and source is TransferSource.CHAIN
            and (not self._usdt_master or transfer.jetton_master != self._usdt_master)
        ):
            # Anyone can mint a jetton called USDT. Only the configured master counts.
            return None, "jetton is not the accepted USDT master"
        if invoice.quote(transfer.asset) is None:
            return None, f"{transfer.asset} is not accepted for this invoice"
        if invoice.asset is not None and invoice.asset is not transfer.asset:
            return None, f"invoice is already being paid in {invoice.asset}"
        return invoice, None

    async def _apply(
        self, invoice: Invoice, transfer: IncomingTransfer, source: TransferSource
    ) -> None:
        quote = invoice.quote(transfer.asset)
        assert quote is not None
        tolerance = self._tolerance if transfer.asset is Asset.TON else 0
        outcome = apply_transfer(
            InvoiceState(
                status=invoice.status,
                asset=transfer.asset,
                amount=quote,
                received=int(invoice.received),
                expires_at=invoice.expires_at,
            ),
            transfer,
            tolerance=tolerance,
        )
        invoice.asset = transfer.asset
        invoice.received = Decimal(outcome.received)
        invoice.overpaid = Decimal(outcome.overpaid)
        invoice.status = outcome.status
        if source is TransferSource.CHAIN:
            invoice.payer_address = invoice.payer_address or transfer.sender
        if outcome.event is not None and outcome.status is InvoiceStatus.PAID:
            invoice.paid_at = transfer.occurred_at
            invoice.late = outcome.late
        if outcome.event is not None:
            await self._events.record(
                invoice,
                outcome.event,
                {"payment": {"tx_hash": transfer.tx_hash, "source": source.value}},
            )
