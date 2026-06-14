import enum
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.enums import (
    Asset,
    Channel,
    DeliveryState,
    EventType,
    InvoiceStatus,
    Mode,
    ProductKind,
)

_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def new_id(prefix: str) -> str:
    return f"{prefix}_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(20))


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(cls: type[enum.Enum]) -> Enum:
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


Units = Numeric(40, 0)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSONB,
        datetime: DateTime(timezone=True),
    }


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("mer"))
    name: Mapped[str] = mapped_column(String(120))
    owner_address: Mapped[str | None] = mapped_column(String(80), unique=True)
    # One store per receiving wallet: payments are matched to stores by this address.
    wallet_address: Mapped[str] = mapped_column(String(80), unique=True)
    accept_ton: Mapped[bool] = mapped_column(Boolean, default=True)
    accept_usdt: Mapped[bool] = mapped_column(Boolean, default=True)
    accept_stars: Mapped[bool] = mapped_column(Boolean, default=True)
    invoice_ttl_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("key"))
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    mode: Mapped[Mode] = mapped_column(_enum(Mode))
    label: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(24))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_merchant_created", "merchant_id", "created_at"),
        Index("ix_invoices_open_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("inv"))
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    mode: Mapped[Mode] = mapped_column(_enum(Mode))
    reference: Mapped[str] = mapped_column(String(16), unique=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        _enum(InvoiceStatus), default=InvoiceStatus.PENDING
    )
    description: Mapped[str] = mapped_column(String(240))
    order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    product_kind: Mapped[ProductKind] = mapped_column(_enum(ProductKind))
    channel: Mapped[Channel] = mapped_column(_enum(Channel))

    fiat_currency: Mapped[str] = mapped_column(String(3))
    fiat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # Smallest units per accepted asset, fixed at creation:
    # {"TON": "1250000000", "USDT": "3900000"}.
    quotes: Mapped[dict[str, Any]]
    rates: Mapped[dict[str, Any]]

    asset: Mapped[Asset | None] = mapped_column(_enum(Asset))
    received: Mapped[Decimal] = mapped_column(Units, default=0)
    overpaid: Mapped[Decimal] = mapped_column(Units, default=0)
    late: Mapped[bool] = mapped_column(Boolean, default=False)

    recipient_address: Mapped[str] = mapped_column(String(80))
    payer_address: Mapped[str | None] = mapped_column(String(80))
    return_url: Mapped[str | None] = mapped_column(String(500))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)

    expires_at: Mapped[datetime]
    paid_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now(), onupdate=utcnow
    )

    merchant: Mapped[Merchant] = relationship(lazy="joined", innerjoin=True)

    def quote(self, asset: Asset) -> int | None:
        raw = self.quotes.get(asset.value)
        return int(raw) if raw is not None else None


class Transfer(Base):
    """Every incoming payment we have seen, matched or not. tx_hash makes processing idempotent."""

    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tx_hash: Mapped[str] = mapped_column(String(100), unique=True)
    lt: Mapped[int] = mapped_column(BigInteger)
    asset: Mapped[Asset] = mapped_column(_enum(Asset))
    amount: Mapped[Decimal] = mapped_column(Units)
    sender: Mapped[str] = mapped_column(String(80))
    recipient: Mapped[str] = mapped_column(String(80), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    jetton_master: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime]
    invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("evt"))
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    type: Mapped[EventType] = mapped_column(_enum(EventType))
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("whe"))
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_deliveries_due", "state", "next_attempt_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("whd"))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"))
    state: Mapped[DeliveryState] = mapped_column(
        _enum(DeliveryState), default=DeliveryState.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None]
    last_status_code: Mapped[int | None]
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now(), onupdate=utcnow
    )

    event: Mapped[Event] = relationship(lazy="joined", innerjoin=True)
    endpoint: Mapped[WebhookEndpoint] = relationship(lazy="joined", innerjoin=True)


class WebhookAttempt(Base):
    __tablename__ = "webhook_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    delivery_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_deliveries.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    status_code: Mapped[int | None]
    duration_ms: Mapped[int]
    error: Mapped[str | None] = mapped_column(String(300))
    response_excerpt: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())


class WatchCursor(Base):
    """Last processed logical time per watched account, so restarts do not rescan history."""

    __tablename__ = "watch_cursors"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    last_lt: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now(), onupdate=utcnow
    )
