from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.domain.enums import Asset
from app.domain.matching import IncomingTransfer


@dataclass(frozen=True, slots=True)
class TransferPage:
    items: list[IncomingTransfer]
    # Highest lt the provider looked at, including transactions that were not payments.
    # Without it a page full of unrelated transactions would pin the cursor forever.
    last_lt: int
    has_more: bool


class ChainProvider(Protocol):
    """Read side of the TON network. Implementations: toncenter v3, TonAPI v2."""

    name: str

    async def incoming_ton(
        self, account: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage: ...

    async def incoming_jettons(
        self, owner: str, jetton_master: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage: ...

    async def jetton_wallet_address(self, owner: str, jetton_master: str) -> str | None: ...

    async def wallet_public_key(self, address: str) -> bytes | None:
        """Live key from `get_public_key`, None when the wallet is not deployed yet."""
        ...


class RateSource(Protocol):
    async def fiat_rates(self, fiat: str) -> dict[Asset, Decimal]: ...


class EventBus(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]: ...
