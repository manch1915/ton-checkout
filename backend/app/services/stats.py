from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Asset, DeliveryState, InvoiceStatus, Mode
from app.domain.pricing import units_to_decimal
from app.infrastructure.db.models import Event, Invoice, Merchant, Transfer, WebhookDelivery


@dataclass(frozen=True, slots=True)
class DayVolume:
    day: date
    fiat: Decimal
    # Fiat value per asset, so a chart can stack Gram, USDT and Stars on one axis.
    fiat_by_asset: dict[Asset, Decimal]
    paid: int


@dataclass(frozen=True, slots=True)
class Summary:
    days: list[DayVolume]
    gross_fiat: Decimal
    paid_count: int
    created_count: int
    expired_count: int
    conversion: float
    average_order: Decimal
    volume_by_asset: dict[Asset, Decimal]
    unmatched_transfers: int
    webhook_success_rate: float | None


class StatsService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def summary(self, merchant_id: str, mode: Mode | None, days: int) -> Summary:
        since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=days - 1
        )
        scope = [Invoice.merchant_id == merchant_id]
        if mode is not None:
            scope.append(Invoice.mode == mode)

        day = cast(func.date_trunc("day", Invoice.paid_at), Date)
        rows = await self._session.execute(
            select(
                day,
                Invoice.asset,
                func.sum(Invoice.fiat_amount),
                func.sum(Invoice.received),
                func.count(),
            )
            .where(*scope, Invoice.status == InvoiceStatus.PAID, Invoice.paid_at >= since)
            .group_by(day, Invoice.asset)
        )
        per_day: dict[date, DayVolume] = {}
        for i in range(days):
            d = (since + timedelta(days=i)).date()
            per_day[d] = DayVolume(d, Decimal(0), {a: Decimal(0) for a in Asset}, 0)
        totals = {a: Decimal(0) for a in Asset}
        for d, asset, fiat, received, count in rows:
            if d not in per_day or asset is None:
                continue
            bucket = per_day[d]
            bucket.fiat_by_asset[asset] += fiat or 0
            totals[asset] += units_to_decimal(int(received or 0), asset)
            per_day[d] = DayVolume(
                d, bucket.fiat + (fiat or 0), bucket.fiat_by_asset, bucket.paid + count
            )

        counts = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count().filter(Invoice.status == InvoiceStatus.PAID),
                    func.count().filter(Invoice.status == InvoiceStatus.EXPIRED),
                    func.coalesce(
                        func.sum(case((Invoice.status == InvoiceStatus.PAID, Invoice.fiat_amount))),
                        0,
                    ),
                ).where(*scope, Invoice.created_at >= since)
            )
        ).one()
        created, paid, expired, gross = (
            int(counts[0]),
            int(counts[1]),
            int(counts[2]),
            Decimal(counts[3]),
        )

        wallet = select(Merchant.wallet_address).where(Merchant.id == merchant_id).scalar_subquery()
        unmatched = await self._session.scalar(
            select(func.count())
            .select_from(Transfer)
            .where(Transfer.invoice_id.is_(None), Transfer.recipient == wallet)
        )
        deliveries = (
            await self._session.execute(
                select(
                    func.count().filter(WebhookDelivery.state == DeliveryState.SUCCEEDED),
                    func.count().filter(WebhookDelivery.state == DeliveryState.FAILED),
                )
                .join(Event, Event.id == WebhookDelivery.event_id)
                .where(Event.merchant_id == merchant_id, WebhookDelivery.created_at >= since)
            )
        ).one()
        finished = deliveries[0] + deliveries[1]

        return Summary(
            days=list(per_day.values()),
            gross_fiat=gross,
            paid_count=paid,
            created_count=created,
            expired_count=expired,
            conversion=paid / created if created else 0.0,
            average_order=(gross / paid).quantize(Decimal("0.01")) if paid else Decimal(0),
            volume_by_asset=totals,
            unmatched_transfers=int(unmatched or 0),
            webhook_success_rate=deliveries[0] / finished if finished else None,
        )
