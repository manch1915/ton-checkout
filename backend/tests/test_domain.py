from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.enums import Asset, Channel, EventType, InvoiceStatus, ProductKind
from app.domain.matching import InvoiceState, apply_transfer, normalize_comment
from app.domain.payment_policy import allowed_assets
from app.domain.pricing import fiat_to_units, format_units, new_reference
from tests.conftest import transfer

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def state(
    amount: int, received: int = 0, status: InvoiceStatus = InvoiceStatus.PENDING
) -> InvoiceState:
    return InvoiceState(status, Asset.TON, amount, received, NOW + timedelta(minutes=30))


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        ("TC-7F3K9Q2M", "TC-7F3K9Q2M"),
        ("  tc-7f3k9q2m ", "TC-7F3K9Q2M"),
        ("order TC 7F3K9Q2M thanks", "TC-7F3K9Q2M"),
        ("TC7F3K9Q2M", "TC-7F3K9Q2M"),
        ("TC-7F3K9Q2", None),
        ("hello", None),
        (None, None),
    ],
)
def test_normalize_comment(comment: str | None, expected: str | None) -> None:
    assert normalize_comment(comment) == expected


def test_reference_format_round_trips() -> None:
    ref = new_reference()
    assert normalize_comment(ref) == ref


def test_exact_payment_marks_paid() -> None:
    outcome = apply_transfer(state(1000), transfer("x", 1000, at=NOW))
    assert outcome.status is InvoiceStatus.PAID
    assert outcome.event is EventType.INVOICE_PAID
    assert outcome.overpaid == 0


def test_underpayment_then_top_up() -> None:
    first = apply_transfer(state(1000), transfer("x", 400, at=NOW))
    assert first.status is InvoiceStatus.PARTIALLY_PAID
    assert first.event is EventType.INVOICE_PARTIALLY_PAID
    second = apply_transfer(state(1000, first.received, first.status), transfer("x", 600, at=NOW))
    assert second.status is InvoiceStatus.PAID


def test_overpayment_is_recorded() -> None:
    outcome = apply_transfer(state(1000), transfer("x", 1500, at=NOW))
    assert outcome.status is InvoiceStatus.PAID
    assert outcome.overpaid == 500


def test_tolerance_covers_wallet_rounding() -> None:
    outcome = apply_transfer(state(1_000_000), transfer("x", 999_500, at=NOW), tolerance=1000)
    assert outcome.status is InvoiceStatus.PAID


def test_payment_after_expiry_is_late() -> None:
    outcome = apply_transfer(state(1000), transfer("x", 1000, at=NOW + timedelta(hours=1)))
    assert outcome.status is InvoiceStatus.PAID
    assert outcome.late


def test_second_payment_to_paid_invoice_emits_nothing() -> None:
    outcome = apply_transfer(state(1000, 1000, InvoiceStatus.PAID), transfer("x", 1000, at=NOW))
    assert outcome.event is None
    assert outcome.overpaid == 1000


def test_asset_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="asset mismatch"):
        apply_transfer(state(1000), transfer("x", 1000, asset=Asset.USDT, at=NOW))


@pytest.mark.parametrize(
    ("fiat", "rate", "asset", "units"),
    [
        (Decimal("18.00"), Decimal("1.35"), Asset.TON, 13_334_000_000),
        (Decimal("24.00"), Decimal("1"), Asset.USDT, 24_000_000),
        (Decimal("0.99"), Decimal("0.9990"), Asset.USDT, 1_000_000),
    ],
)
def test_fiat_to_units_rounds_up_to_readable_step(
    fiat: Decimal, rate: Decimal, asset: Asset, units: int
) -> None:
    assert fiat_to_units(fiat, rate, asset) == units


def test_format_units_drops_trailing_zeros() -> None:
    assert format_units(13_334_000_000, Asset.TON) == "13.334"
    assert format_units(24_000_000, Asset.USDT) == "24"


@pytest.mark.parametrize(
    ("kind", "channel", "allowed"),
    [
        (ProductKind.DIGITAL, Channel.TELEGRAM_MINI_APP, (Asset.STARS,)),
        (ProductKind.DIGITAL, Channel.TELEGRAM_BOT, (Asset.STARS,)),
        (ProductKind.OFFLINE_SERVICE, Channel.TELEGRAM_MINI_APP, (Asset.TON, Asset.USDT)),
        (ProductKind.DIGITAL, Channel.WEB, (Asset.TON, Asset.USDT)),
    ],
)
def test_payment_policy(kind: ProductKind, channel: Channel, allowed: tuple[Asset, ...]) -> None:
    assert allowed_assets(kind, channel).allowed == allowed
