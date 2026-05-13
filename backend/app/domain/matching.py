"""How an incoming on-chain transfer changes an invoice. Pure logic, no I/O."""

import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import Asset, EventType, InvoiceStatus

REFERENCE_PREFIX = "TC"
_REFERENCE_RE = re.compile(r"\bTC[-\s]?([0-9A-Z]{8})\b")


def normalize_comment(comment: str | None) -> str | None:
    """Extract an invoice reference from a free-form comment.

    People paste comments with spaces, lowercase or extra words around them,
    so we search instead of comparing the whole string.
    """
    if not comment:
        return None
    match = _REFERENCE_RE.search(comment.upper())
    return f"{REFERENCE_PREFIX}-{match.group(1)}" if match else None


@dataclass(frozen=True, slots=True)
class IncomingTransfer:
    tx_hash: str
    lt: int
    asset: Asset
    amount: int
    sender: str
    recipient: str
    comment: str | None
    occurred_at: datetime
    jetton_master: str | None = None


@dataclass(frozen=True, slots=True)
class InvoiceState:
    status: InvoiceStatus
    asset: Asset
    amount: int
    received: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    status: InvoiceStatus
    received: int
    overpaid: int
    late: bool
    event: EventType | None


def apply_transfer(
    invoice: InvoiceState, transfer: IncomingTransfer, *, tolerance: int = 0
) -> MatchOutcome:
    if transfer.asset is not invoice.asset:
        raise ValueError(f"asset mismatch: invoice {invoice.asset}, transfer {transfer.asset}")

    late = transfer.occurred_at > invoice.expires_at
    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELED):
        # Money is already on the merchant wallet, we only record it.
        return MatchOutcome(
            invoice.status,
            invoice.received + transfer.amount,
            _overpaid(invoice, invoice.received + transfer.amount),
            late,
            None,
        )

    received = invoice.received + transfer.amount
    if received + tolerance >= invoice.amount:
        return MatchOutcome(
            InvoiceStatus.PAID, received, _overpaid(invoice, received), late, EventType.INVOICE_PAID
        )

    status = (
        InvoiceStatus.EXPIRED
        if invoice.status is InvoiceStatus.EXPIRED
        else (InvoiceStatus.PARTIALLY_PAID)
    )
    return MatchOutcome(status, received, 0, late, EventType.INVOICE_PARTIALLY_PAID)


def _overpaid(invoice: InvoiceState, received: int) -> int:
    return max(0, received - invoice.amount)
