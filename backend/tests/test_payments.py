"""Payment processing against a real Postgres, including the abuse cases from the TON
payments guide: reusing a settled reference, paying less, copied comments and dust spam."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.domain.enums import Asset, Channel, EventType, InvoiceStatus, Mode, ProductKind
from app.infrastructure.db.models import (
    Event,
    Invoice,
    Merchant,
    Transfer,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.services.invoices import NewInvoice
from app.services.payments import Outcome, TransferSource
from tests.conftest import USDT_MASTER, transfer


async def _invoice(
    container: Container, session: AsyncSession, merchant: Merchant, **kw: object
) -> Invoice:
    data = NewInvoice(
        fiat_amount=Decimal("18.00"),
        description="Friday Jazz Night",
        product_kind=ProductKind.OFFLINE_SERVICE,
        **kw,
    )  # type: ignore[arg-type]
    return await container.invoices(session).create(merchant, Mode.TEST, data)


async def _process(container: Container, t: object, source: TransferSource = TransferSource.CHAIN):
    async with container.sessions() as s:
        return await container.processor(s).process(t, source)  # type: ignore[arg-type]


async def _reload(container: Container, invoice_id: str) -> Invoice:
    async with container.sessions() as s:
        return await s.get_one(Invoice, invoice_id)


async def test_invoice_is_quoted_in_every_allowed_asset(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    assert invoice.quote(Asset.TON) == 14_400_000_000  # 18 / 1.25
    assert invoice.quote(Asset.USDT) == 18_000_000
    assert invoice.quote(Asset.STARS) is None
    assert invoice.asset is None


async def test_digital_goods_in_mini_app_get_stars_only(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    data = NewInvoice(
        fiat_amount=Decimal("6"),
        description="Live recording",
        stars_amount=300,
        product_kind=ProductKind.DIGITAL,
        channel=Channel.TELEGRAM_MINI_APP,
    )
    invoice = await container.invoices(session).create(merchant, Mode.TEST, data)
    assert invoice.quotes == {"XTR": "300"}
    assert invoice.asset is Asset.STARS


async def test_full_ton_payment_marks_paid_and_queues_webhook(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    session.add(
        WebhookEndpoint(merchant_id=merchant.id, url="https://example.com/h", secret="whsec_AAAA")
    )
    await session.commit()
    invoice = await _invoice(container, session, merchant)

    result = await _process(container, transfer(invoice.reference, 14_400_000_000))

    assert result.outcome is Outcome.MATCHED
    paid = await _reload(container, invoice.id)
    assert paid.status is InvoiceStatus.PAID
    assert paid.asset is Asset.TON
    assert paid.paid_at is not None
    async with container.sessions() as s:
        types = list(await s.scalars(select(Event.type).where(Event.invoice_id == invoice.id)))
        deliveries = await s.scalar(select(func.count()).select_from(WebhookDelivery))
    assert types == [EventType.INVOICE_CREATED, EventType.INVOICE_PAID]
    assert deliveries == 2


async def test_same_transaction_twice_is_counted_once(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    t = transfer(invoice.reference, 7_000_000_000)
    assert (await _process(container, t)).outcome is Outcome.MATCHED
    assert (await _process(container, t)).outcome is Outcome.DUPLICATE
    reloaded = await _reload(container, invoice.id)
    assert reloaded.received == 7_000_000_000
    assert reloaded.status is InvoiceStatus.PARTIALLY_PAID


async def test_paying_less_keeps_invoice_open_until_topped_up(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    await _process(container, transfer(invoice.reference, 10_000_000_000, lt=1))
    assert (await _reload(container, invoice.id)).status is InvoiceStatus.PARTIALLY_PAID
    await _process(container, transfer(invoice.reference, 4_400_000_000, lt=2))
    assert (await _reload(container, invoice.id)).status is InvoiceStatus.PAID


async def test_reusing_settled_reference_does_not_pay_again(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    await _process(container, transfer(invoice.reference, 14_400_000_000, lt=1))
    await _process(container, transfer(invoice.reference, 14_400_000_000, lt=2))
    reloaded = await _reload(container, invoice.id)
    assert reloaded.status is InvoiceStatus.PAID
    assert reloaded.overpaid == 14_400_000_000
    async with container.sessions() as s:
        paid_events = await s.scalar(
            select(func.count()).select_from(Event).where(Event.type == EventType.INVOICE_PAID)
        )
    assert paid_events == 1


async def test_dust_without_reference_stays_unmatched(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    await _invoice(container, session, merchant)
    result = await _process(container, transfer("Free airdrop, claim at scam.example", 1))
    assert result.outcome is Outcome.UNMATCHED
    async with container.sessions() as s:
        row = await s.scalar(select(Transfer))
    assert row is not None
    assert row.invoice_id is None
    assert row.note


async def test_reference_paid_to_another_wallet_is_ignored(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    other = "0:" + "99" * 32
    result = await _process(container, transfer(invoice.reference, 14_400_000_000, recipient=other))
    assert result.outcome is Outcome.UNMATCHED
    assert (await _reload(container, invoice.id)).status is InvoiceStatus.PENDING


async def test_fake_usdt_jetton_is_not_accepted(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    fake = transfer(invoice.reference, 18_000_000, asset=Asset.USDT, jetton_master="0:" + "ee" * 32)
    result = await _process(container, fake)
    assert result.outcome is Outcome.UNMATCHED
    assert "master" in (result.note or "")
    real = transfer(
        invoice.reference, 18_000_000, lt=2, asset=Asset.USDT, jetton_master=USDT_MASTER
    )
    assert (await _process(container, real)).status is InvoiceStatus.PAID


async def test_first_payment_locks_the_asset(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    await _process(container, transfer(invoice.reference, 5_000_000_000, lt=1))
    usdt = transfer(invoice.reference, 18_000_000, lt=2, asset=Asset.USDT)
    result = await _process(container, usdt)
    assert result.outcome is Outcome.UNMATCHED
    assert "already being paid in TON" in (result.note or "")


async def test_sandbox_payment_rejected_for_live_invoice(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    data = NewInvoice(fiat_amount=Decimal("5"), description="Poster")
    invoice = await container.invoices(session).create(merchant, Mode.LIVE, data)
    t = transfer(invoice.reference, 4_000_000_000)
    assert (await _process(container, t, TransferSource.SANDBOX)).outcome is Outcome.UNMATCHED


async def test_unmatched_payment_can_be_assigned_by_hand(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _invoice(container, session, merchant)
    await _process(container, transfer("forgot the code", 14_400_000_000))
    async with container.sessions() as s:
        row = await s.scalar(select(Transfer))
        assert row is not None
        result = await container.processor(s).assign(row.id, invoice.id, merchant.id)
    assert result.outcome is Outcome.MATCHED
    assert (await _reload(container, invoice.id)).status is InvoiceStatus.PAID


async def test_expiry_sweeper(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    from datetime import UTC, datetime, timedelta

    invoice = await _invoice(container, session, merchant, ttl_minutes=5)
    async with container.sessions() as s:
        count = await container.invoices(s).expire_due(datetime.now(UTC) + timedelta(minutes=6))
    assert count == 1
    assert (await _reload(container, invoice.id)).status is InvoiceStatus.EXPIRED
