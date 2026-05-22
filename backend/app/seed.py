"""Demo store with two weeks of history, so the dashboard has something to show on first visit.

Idempotent: does nothing if the demo merchant already exists. Historical payments are marked
as sandbox payments, they never touched the chain.
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.demo_shop.catalog import CATALOG, Product
from app.demo_shop.models import ShopOrder
from app.domain.enums import (
    Asset,
    Channel,
    DeliveryState,
    EventType,
    InvoiceStatus,
    Mode,
)
from app.domain.payment_policy import allowed_assets
from app.domain.pricing import fiat_to_units, new_reference
from app.infrastructure.db.models import (
    Event,
    Invoice,
    Merchant,
    Transfer,
    WebhookAttempt,
    WebhookDelivery,
    WebhookEndpoint,
    new_id,
)
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.ton.address import to_raw
from app.services.views import invoice_view
from app.services.webhooks import new_webhook_secret

DAYS = 14
SANDBOX_SENDER = "sandbox"


def _quotes(
    product: Product, channel: Channel, ton_rate: Decimal
) -> tuple[dict[str, str], dict[str, str]]:
    quotes: dict[str, str] = {}
    rates: dict[str, str] = {}
    for asset in allowed_assets(product.kind, channel).allowed:
        if asset is Asset.STARS:
            quotes[asset.value] = str(product.stars or int(product.price * 50))
        elif asset is Asset.TON:
            quotes[asset.value] = str(fiat_to_units(product.price, ton_rate, asset))
            rates[asset.value] = str(ton_rate)
        else:
            quotes[asset.value] = str(fiat_to_units(product.price, Decimal(1), asset))
            rates[asset.value] = "1"
    return quotes, rates


def _history(merchant: Merchant, endpoint: WebhookEndpoint, settings: Settings) -> list[object]:
    rng = random.Random(1409)  # noqa: S311  (fixed seed, demo data only)
    now = datetime.now(UTC)
    rows: list[object] = []
    for day in range(DAYS, 0, -1):
        # Weekends sell more tickets, the last few days ramp up before a big show.
        base = 5 + (3 if (now - timedelta(days=day)).weekday() >= 4 else 0) + max(0, 4 - day)
        for _ in range(rng.randint(base, base + 4)):
            created = now - timedelta(
                days=day, hours=rng.randint(0, 22), minutes=rng.randint(0, 59)
            )
            product = rng.choices(CATALOG, weights=[30, 22, 8, 14, 10, 16])[0]
            in_telegram = rng.random() < 0.55
            channel = Channel.TELEGRAM_MINI_APP if in_telegram else Channel.WEB
            ton_rate = Decimal("1.35") + Decimal(rng.randint(-6, 6)) / 100
            quotes, rates = _quotes(product, channel, ton_rate)
            options = [Asset(code) for code in quotes]
            asset = rng.choices(options, weights=[3 if a is Asset.USDT else 2 for a in options])[0]
            roll = rng.random()
            status = (
                InvoiceStatus.PAID
                if roll < 0.74
                else InvoiceStatus.EXPIRED
                if roll < 0.93
                else InvoiceStatus.CANCELED
                if roll < 0.96
                else InvoiceStatus.PARTIALLY_PAID
            )
            if status is InvoiceStatus.PARTIALLY_PAID and asset is Asset.STARS:
                status = InvoiceStatus.EXPIRED
            invoice = _invoice(
                merchant, product, channel, quotes, rates, created, status, asset, rng
            )
            rows.append(invoice)
            rows.extend(_trail(invoice, endpoint, settings, rng))
    return rows


def _invoice(
    merchant: Merchant,
    product: Product,
    channel: Channel,
    quotes: dict[str, str],
    rates: dict[str, str],
    created: datetime,
    status: InvoiceStatus,
    asset: Asset,
    rng: random.Random,
) -> Invoice:
    due = int(quotes[asset.value])
    received = 0
    overpaid = 0
    paid_at = None
    if status is InvoiceStatus.PAID:
        received = due
        if asset is Asset.TON and rng.random() < 0.08:
            overpaid = 10_000_000
            received += overpaid
        paid_at = created + timedelta(minutes=rng.randint(1, 9), seconds=rng.randint(0, 59))
    elif status is InvoiceStatus.PARTIALLY_PAID:
        # Underpaid and never topped up: by now the invoice has expired with money on it.
        received = due // 2
        status = InvoiceStatus.EXPIRED
    order_id = new_id("ord")
    invoice = Invoice(
        id=new_id("inv"),
        merchant_id=merchant.id,
        mode=Mode.TEST,
        reference=new_reference(),
        status=status,
        description=product.title,
        order_id=order_id,
        product_kind=product.kind,
        channel=channel,
        fiat_currency="USD",
        fiat_amount=product.price,
        quotes=quotes,
        rates=rates,
        asset=asset if received or len(quotes) == 1 else None,
        received=Decimal(received),
        overpaid=Decimal(overpaid),
        late=False,
        recipient_address=merchant.wallet_address,
        payer_address=None,
        metadata_={"shop_order": order_id, "product": product.id},
        expires_at=created + timedelta(minutes=30),
        paid_at=paid_at,
        created_at=created,
        updated_at=paid_at or created,
    )
    invoice.merchant = merchant
    return invoice


def _trail(
    invoice: Invoice, endpoint: WebhookEndpoint, settings: Settings, rng: random.Random
) -> list[object]:
    rows: list[object] = []
    view = invoice_view(invoice, public_url=settings.public_url, testnet=settings.is_testnet)
    created_event = Event(
        merchant_id=invoice.merchant_id,
        invoice_id=invoice.id,
        type=EventType.INVOICE_CREATED,
        payload={"invoice": view.model_dump(mode="json")},
        created_at=invoice.created_at,
    )
    rows.append(created_event)
    final = {
        InvoiceStatus.PAID: EventType.INVOICE_PAID,
        InvoiceStatus.EXPIRED: EventType.INVOICE_EXPIRED,
        InvoiceStatus.CANCELED: EventType.INVOICE_CANCELED,
        InvoiceStatus.PARTIALLY_PAID: EventType.INVOICE_PARTIALLY_PAID,
    }[invoice.status]
    if invoice.status is InvoiceStatus.EXPIRED and invoice.received:
        final = EventType.INVOICE_PARTIALLY_PAID
    at = invoice.paid_at or invoice.expires_at
    if invoice.received and invoice.asset:
        source = "stars" if invoice.asset is Asset.STARS else "sandbox"
        rows.append(
            Transfer(
                tx_hash=f"{source}:{new_id('seed')}",
                lt=0,
                asset=invoice.asset,
                amount=invoice.received,
                sender=f"tg:{rng.randint(10**8, 10**9)}" if source == "stars" else SANDBOX_SENDER,
                recipient=invoice.recipient_address,
                comment=invoice.reference,
                source=source,
                occurred_at=at,
                invoice_id=invoice.id,
                created_at=at,
            )
        )
    final_event = Event(
        merchant_id=invoice.merchant_id,
        invoice_id=invoice.id,
        type=final,
        payload={"invoice": view.model_dump(mode="json")},
        created_at=at,
    )
    rows.append(final_event)
    for event in (created_event, final_event):
        event.id = new_id("evt")
        # Roughly one in twelve deliveries needed a retry, as real endpoints sometimes hiccup.
        retried = rng.random() < 0.08
        delivery = WebhookDelivery(
            id=new_id("whd"),
            event_id=event.id,
            endpoint_id=endpoint.id,
            state=DeliveryState.SUCCEEDED,
            attempts=2 if retried else 1,
            last_status_code=200,
            created_at=event.created_at,
            updated_at=event.created_at,
        )
        rows.append(delivery)
        if retried:
            rows.append(
                WebhookAttempt(
                    delivery_id=delivery.id,
                    number=1,
                    status_code=502,
                    duration_ms=rng.randint(900, 3000),
                    response_excerpt="Bad Gateway",
                    created_at=event.created_at,
                )
            )
        rows.append(
            WebhookAttempt(
                delivery_id=delivery.id,
                number=2 if retried else 1,
                status_code=200,
                duration_ms=rng.randint(40, 260),
                response_excerpt='{"ok":true}',
                created_at=event.created_at + (timedelta(seconds=5) if retried else timedelta()),
            )
        )
    if invoice.status is InvoiceStatus.PAID:
        rows.append(
            ShopOrder(
                id=invoice.order_id,
                product_id=invoice.metadata_["product"],
                channel=invoice.channel.value,
                invoice_id=invoice.id,
                status="fulfilled",
                access_code=f"{rng.getrandbits(32):08X}",
                fulfilled_at=at,
                created_at=invoice.created_at,
            )
        )
    return rows


async def seed(settings: Settings) -> bool:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            if await session.scalar(select(Merchant).where(Merchant.is_demo)):
                return False
            if not settings.demo_wallet_address:
                raise SystemExit("DEMO_WALLET_ADDRESS is required to seed the demo store")
            merchant = Merchant(
                id=new_id("mer"),
                name="Cellar Nine",
                wallet_address=to_raw(settings.demo_wallet_address),
                is_demo=True,
                invoice_ttl_minutes=30,
                created_at=datetime.now(UTC) - timedelta(days=DAYS + 3),
            )
            endpoint = WebhookEndpoint(
                id=new_id("whe"),
                merchant_id=merchant.id,
                url=settings.shop_webhook_url,
                secret=new_webhook_secret(),
                created_at=merchant.created_at,
            )
            session.add_all([merchant, endpoint])
            await session.flush()
            rows = _history(merchant, endpoint, settings)
            # Plain FK columns without relationships are not ordered by the unit of work,
            # so parents go in first.
            for kind in (Invoice, Transfer, Event, WebhookDelivery, WebhookAttempt, ShopOrder):
                session.add_all([r for r in rows if type(r) is kind])
                await session.flush()
            await session.commit()
            return True
    finally:
        await engine.dispose()


def main() -> None:
    created = asyncio.run(seed(get_settings()))
    print("demo store seeded" if created else "demo store already exists")


if __name__ == "__main__":
    main()
