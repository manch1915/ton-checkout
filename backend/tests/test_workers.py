from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core import signing
from app.domain.enums import Asset, DeliveryState, InvoiceStatus, Mode, ProductKind
from app.infrastructure.db.models import (
    Invoice,
    Merchant,
    WatchCursor,
    WebhookAttempt,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.services.invoices import NewInvoice
from app.services.webhooks import MAX_ATTEMPTS, WebhookDispatcher, next_attempt_delay
from tests.conftest import FakeProvider, transfer

HOOK = "https://merchant.example/hooks/ton"


async def _setup(container: Container, session: AsyncSession, merchant: Merchant) -> Invoice:
    session.add(WebhookEndpoint(merchant_id=merchant.id, url=HOOK, secret=signing.new_secret()))
    await session.commit()
    data = NewInvoice(
        fiat_amount=Decimal("12"), description="Sample pack", product_kind=ProductKind.DIGITAL
    )
    return await container.invoices(session).create(merchant, Mode.TEST, data)


@respx.mock
async def test_delivery_is_signed_and_verifiable(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    await _setup(container, session, merchant)
    route = respx.post(HOOK).mock(return_value=httpx.Response(200, json={"ok": True}))

    async with httpx.AsyncClient() as http:
        sent = await WebhookDispatcher(container.sessions, http, allow_private=True).run_due()

    assert sent == 1
    request = route.calls.last.request
    async with container.sessions() as s:
        secret = (await s.scalars(select(WebhookEndpoint.secret))).one()
    assert signing.verify(secret, request.content, dict(request.headers))


@respx.mock
async def test_failed_delivery_is_retried_later(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    await _setup(container, session, merchant)
    respx.post(HOOK).mock(return_value=httpx.Response(503, text="maintenance"))

    async with httpx.AsyncClient() as http:
        await WebhookDispatcher(container.sessions, http, allow_private=True).run_due()

    async with container.sessions() as s:
        delivery = (await s.scalars(select(WebhookDelivery))).one()
        attempts = list(await s.scalars(select(WebhookAttempt)))
    assert delivery.state is DeliveryState.PENDING
    assert delivery.attempts == 1
    assert delivery.next_attempt_at is not None
    assert delivery.next_attempt_at > datetime.now(UTC)
    assert attempts[0].status_code == 503
    assert attempts[0].response_excerpt == "maintenance"


def test_retry_schedule_gives_up_after_last_attempt() -> None:
    assert next_attempt_delay(1) is not None
    assert next_attempt_delay(MAX_ATTEMPTS) is None
    total = sum(
        (next_attempt_delay(n) or timedelta()).total_seconds() for n in range(1, MAX_ATTEMPTS)
    )
    assert 2.5 * 86400 < total < 3.5 * 86400


async def test_watcher_matches_payment_and_moves_cursor(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    invoice = await _setup(container, session, merchant)
    provider = container.provider
    assert isinstance(provider, FakeProvider)
    provider.ton.append(transfer(invoice.reference, invoice.quote(Asset.TON) or 0, lt=500))
    provider.jettons.append(transfer("unrelated", 1, lt=77, asset=Asset.USDT))

    processed = await container.watcher().tick()

    assert processed == 2
    async with container.sessions() as s:
        paid = await s.get_one(Invoice, invoice.id)
        cursors = {c.key.split(":")[0]: c.last_lt for c in await s.scalars(select(WatchCursor))}
    assert paid.status is InvoiceStatus.PAID
    assert cursors == {"ton": 500, "usdt": 77}

    # Next tick reads nothing new and changes nothing.
    assert await container.watcher().tick() == 0


async def test_watcher_cursor_advances_past_pages_without_payments(
    container: Container, session: AsyncSession, merchant: Merchant
) -> None:
    """A page of unrelated transactions must not pin the cursor (regression)."""
    invoice = await _setup(container, session, merchant)
    from app.services.ports import TransferPage

    class NoisyProvider(FakeProvider):
        async def incoming_ton(
            self, account: str, after_lt: int, limit: int, since: int | None = None
        ) -> TransferPage:
            if after_lt < 1000:
                return TransferPage([], 1000, has_more=True)  # 50 jetton notifications
            items = [transfer(invoice.reference, invoice.quote(Asset.TON) or 0, lt=1001)]
            return TransferPage([i for i in items if i.lt > after_lt], 1001, has_more=False)

    container.provider = NoisyProvider()
    await container.watcher().tick()
    async with container.sessions() as s:
        assert (await s.get_one(Invoice, invoice.id)).status is InvoiceStatus.PAID
