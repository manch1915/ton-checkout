"""Which payment methods a checkout may offer.

Telegram's terms for bot developers require digital goods and services sold inside
bots and Mini Apps to be paid with Stars. Physical goods and services consumed
offline may use other providers, and crypto inside Mini Apps has to go through
TON Connect. Outside Telegram (a regular website) the merchant is free to choose.
"""

from dataclasses import dataclass

from app.domain.enums import Asset, Channel, ProductKind


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: tuple[Asset, ...]
    note: str


_IN_TELEGRAM = (Channel.TELEGRAM_MINI_APP, Channel.TELEGRAM_BOT)


def allowed_assets(kind: ProductKind, channel: Channel) -> PolicyDecision:
    if channel in _IN_TELEGRAM and kind is ProductKind.DIGITAL:
        return PolicyDecision(
            (Asset.STARS,),
            "Digital goods inside Telegram are sold for Stars only.",
        )
    if channel in _IN_TELEGRAM:
        return PolicyDecision(
            (Asset.TON, Asset.USDT),
            "Physical goods and offline services can be paid in TON or USDT via TON Connect.",
        )
    return PolicyDecision(
        (Asset.TON, Asset.USDT),
        "On a website any on-chain method is allowed. Stars work only inside Telegram.",
    )
