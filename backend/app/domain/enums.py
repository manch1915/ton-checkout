from enum import StrEnum


class Asset(StrEnum):
    TON = "TON"
    USDT = "USDT"
    STARS = "XTR"

    @property
    def decimals(self) -> int:
        return {Asset.TON: 9, Asset.USDT: 6, Asset.STARS: 0}[self]

    @property
    def on_chain(self) -> bool:
        return self is not Asset.STARS


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELED = "canceled"

    @property
    def is_open(self) -> bool:
        return self in (InvoiceStatus.PENDING, InvoiceStatus.PARTIALLY_PAID)


class Mode(StrEnum):
    TEST = "test"
    LIVE = "live"


class EventType(StrEnum):
    INVOICE_CREATED = "invoice.created"
    INVOICE_PARTIALLY_PAID = "invoice.partially_paid"
    INVOICE_PAID = "invoice.paid"
    INVOICE_EXPIRED = "invoice.expired"
    INVOICE_CANCELED = "invoice.canceled"
    PAYMENT_UNMATCHED = "payment.unmatched"


class DeliveryState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProductKind(StrEnum):
    DIGITAL = "digital"
    PHYSICAL = "physical"
    OFFLINE_SERVICE = "offline_service"


class Channel(StrEnum):
    WEB = "web"
    TELEGRAM_MINI_APP = "telegram_mini_app"
    TELEGRAM_BOT = "telegram_bot"
