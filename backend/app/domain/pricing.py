import secrets
from decimal import ROUND_CEILING, Decimal

from app.domain.enums import Asset
from app.domain.matching import REFERENCE_PREFIX

# Crockford-style alphabet: no I, L, O, U, so a reference survives being read aloud or retyped.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Wallets display a handful of decimals, so the price is rounded up to a step a human can read.
_DISPLAY_STEP = {Asset.TON: 1_000_000, Asset.USDT: 10_000, Asset.STARS: 1}


def new_reference() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{REFERENCE_PREFIX}-{body}"


def fiat_to_units(fiat_amount: Decimal, rate: Decimal, asset: Asset) -> int:
    """Convert a fiat price to the smallest units of an asset, rounding up.

    `rate` is the fiat price of one whole coin, e.g. 3.12 USD per TON.
    """
    if fiat_amount <= 0 or rate <= 0:
        raise ValueError("amount and rate must be positive")
    whole = fiat_amount / rate
    units = int((whole * (Decimal(10) ** asset.decimals)).to_integral_value(ROUND_CEILING))
    step = _DISPLAY_STEP[asset]
    return -(-units // step) * step


def units_to_decimal(units: int, asset: Asset) -> Decimal:
    return Decimal(units) / (Decimal(10) ** asset.decimals)


def format_units(units: int, asset: Asset) -> str:
    return f"{units_to_decimal(units, asset).normalize():f}"
