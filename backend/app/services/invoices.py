from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Asset, Channel, EventType, InvoiceStatus, Mode, ProductKind
from app.domain.payment_policy import allowed_assets
from app.domain.pricing import fiat_to_units, new_reference
from app.infrastructure.db.models import Invoice, Merchant, Transfer
from app.services.events import EventRecorder
from app.services.ports import RateSource

SUPPORTED_FIAT = ("USD", "EUR")


class InvoiceError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class NewInvoice:
    fiat_amount: Decimal
    description: str
    fiat_currency: str = "USD"
    product_kind: ProductKind = ProductKind.DIGITAL
    channel: Channel = Channel.WEB
    assets: tuple[Asset, ...] | None = None
    order_id: str | None = None
    return_url: str | None = None
    ttl_minutes: int | None = None
    stars_amount: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InvoiceFilter:
    status: InvoiceStatus | None = None
    asset: Asset | None = None
    mode: Mode | None = None
    search: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class PricingConfig:
    usdt_enabled: bool
    stars_per_usd: Decimal


class InvoiceService:
    def __init__(
        self,
        session: AsyncSession,
        rates: RateSource,
        events: EventRecorder,
        pricing: PricingConfig,
    ):
        self._session = session
        self._rates = rates
        self._events = events
        self._pricing = pricing

    async def create(self, merchant: Merchant, mode: Mode, data: NewInvoice) -> Invoice:
        fiat = data.fiat_currency.upper()
        if fiat not in SUPPORTED_FIAT:
            raise InvoiceError(f"fiat currency must be one of {', '.join(SUPPORTED_FIAT)}")

        assets = self._resolve_assets(merchant, data)
        rates = await self._rates.fiat_rates(fiat)
        quotes: dict[str, str] = {}
        used_rates: dict[str, str] = {}
        for asset in assets:
            if asset is Asset.STARS:
                stars = data.stars_amount or self._stars_for(data.fiat_amount, rates, fiat)
                quotes[asset.value] = str(stars)
                continue
            rate = rates[asset].quantize(Decimal("0.0001"))
            quotes[asset.value] = str(fiat_to_units(data.fiat_amount, rate, asset))
            used_rates[asset.value] = str(rate)

        ttl = data.ttl_minutes or merchant.invoice_ttl_minutes
        invoice = Invoice(
            merchant_id=merchant.id,
            mode=mode,
            reference=new_reference(),
            status=InvoiceStatus.PENDING,
            description=data.description,
            order_id=data.order_id,
            product_kind=data.product_kind,
            channel=data.channel,
            fiat_currency=fiat,
            fiat_amount=data.fiat_amount,
            quotes=quotes,
            rates=used_rates,
            asset=assets[0] if len(assets) == 1 else None,
            received=Decimal(0),
            overpaid=Decimal(0),
            recipient_address=merchant.wallet_address,
            return_url=data.return_url,
            metadata_=data.metadata,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl),
        )
        invoice.merchant = merchant
        self._session.add(invoice)
        await self._session.flush()
        await self._events.record(invoice, EventType.INVOICE_CREATED)
        await self._events.commit_and_publish()
        return invoice

    def _resolve_assets(self, merchant: Merchant, data: NewInvoice) -> tuple[Asset, ...]:
        policy = allowed_assets(data.product_kind, data.channel)
        enabled = {
            Asset.TON: merchant.accept_ton,
            Asset.USDT: merchant.accept_usdt and self._pricing.usdt_enabled,
            Asset.STARS: merchant.accept_stars,
        }
        requested = data.assets or policy.allowed
        assets = tuple(a for a in requested if a in policy.allowed and enabled[a])
        if not assets:
            raise InvoiceError(f"no payment method is available here. {policy.note}")
        return assets

    def _stars_for(self, amount: Decimal, rates: dict[Asset, Decimal], fiat: str) -> int:
        usd = amount if fiat == "USD" else amount / rates[Asset.USDT]
        return max(1, int((usd * self._pricing.stars_per_usd).to_integral_value()))

    async def get(self, invoice_id: str) -> Invoice | None:
        return await self._session.get(Invoice, invoice_id)

    async def get_for_merchant(self, merchant_id: str, invoice_id: str) -> Invoice | None:
        invoice = await self.get(invoice_id)
        return invoice if invoice and invoice.merchant_id == merchant_id else None

    async def by_reference(self, reference: str) -> Invoice | None:
        return await self._session.scalar(select(Invoice).where(Invoice.reference == reference))

    async def page(
        self, merchant_id: str, flt: InvoiceFilter, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Invoice], int]:
        query = self._filtered(merchant_id, flt)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def export(self, merchant_id: str, flt: InvoiceFilter) -> list[Invoice]:
        rows = await self._session.scalars(
            self._filtered(merchant_id, flt).order_by(Invoice.created_at.desc()).limit(10_000)
        )
        return list(rows)

    def _filtered(self, merchant_id: str, flt: InvoiceFilter) -> Select[Invoice]:
        query = select(Invoice).where(Invoice.merchant_id == merchant_id)
        if flt.status:
            query = query.where(Invoice.status == flt.status)
        if flt.asset:
            query = query.where(Invoice.asset == flt.asset)
        if flt.mode:
            query = query.where(Invoice.mode == flt.mode)
        if flt.created_from:
            query = query.where(Invoice.created_at >= flt.created_from)
        if flt.created_to:
            query = query.where(Invoice.created_at < flt.created_to)
        if flt.search:
            term = f"%{flt.search.strip()}%"
            query = query.where(
                Invoice.id.ilike(term)
                | Invoice.reference.ilike(term)
                | Invoice.order_id.ilike(term)
                | Invoice.description.ilike(term)
            )
        return query

    async def transfers(self, invoice_id: str) -> list[Transfer]:
        rows = await self._session.scalars(
            select(Transfer).where(Transfer.invoice_id == invoice_id).order_by(Transfer.lt)
        )
        return list(rows)

    async def cancel(self, invoice: Invoice) -> Invoice:
        if not invoice.status.is_open:
            raise InvoiceError(f"invoice is {invoice.status}, only open invoices can be canceled")
        invoice.status = InvoiceStatus.CANCELED
        await self._events.record(invoice, EventType.INVOICE_CANCELED)
        await self._events.commit_and_publish()
        return invoice

    async def expire_due(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        due = await self._session.scalars(
            select(Invoice)
            .where(Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.PARTIALLY_PAID]))
            .where(Invoice.expires_at <= now)
            .limit(200)
            .with_for_update(skip_locked=True)
        )
        count = 0
        for invoice in due:
            invoice.status = InvoiceStatus.EXPIRED
            await self._events.record(invoice, EventType.INVOICE_EXPIRED)
            count += 1
        await self._events.commit_and_publish()
        return count
