import time
from decimal import Decimal

import httpx
import structlog

from app.domain.enums import Asset

log = structlog.get_logger()

_COINGECKO_IDS = {Asset.TON: "the-open-network", Asset.USDT: "tether"}


class MarketRates:
    """TonAPI rates with CoinGecko as a fallback and a short in-process cache.

    Rates are only used to quote an invoice once, at creation, so a minute of staleness is fine.
    """

    def __init__(self, client: httpx.AsyncClient, *, ttl: int, fallback_ton_usd: Decimal):
        self._client = client
        self._ttl = ttl
        self._fallback = fallback_ton_usd
        self._cache: dict[str, tuple[float, dict[Asset, Decimal]]] = {}

    async def fiat_rates(self, fiat: str) -> dict[Asset, Decimal]:
        fiat = fiat.upper()
        cached = self._cache.get(fiat)
        if cached and time.monotonic() - cached[0] < self._ttl:
            return cached[1]
        rates = await self._fetch(fiat)
        self._cache[fiat] = (time.monotonic(), rates)
        return rates

    async def _fetch(self, fiat: str) -> dict[Asset, Decimal]:
        for source in (self._from_tonapi, self._from_coingecko):
            try:
                return await source(fiat)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                log.warning("rates.source_failed", source=source.__name__, error=str(exc))
        if fiat != "USD":
            raise RuntimeError(f"no rate source available for {fiat}")
        return {Asset.TON: self._fallback, Asset.USDT: Decimal(1)}

    async def _from_tonapi(self, fiat: str) -> dict[Asset, Decimal]:
        response = await self._client.get(
            "https://tonapi.io/v2/rates",
            params={"tokens": "ton,usdt", "currencies": fiat.lower()},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()["rates"]
        return {
            Asset.TON: Decimal(str(data["TON"]["prices"][fiat])),
            Asset.USDT: Decimal(str(data["USDT"]["prices"][fiat])),
        }

    async def _from_coingecko(self, fiat: str) -> dict[Asset, Decimal]:
        response = await self._client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(_COINGECKO_IDS.values()), "vs_currencies": fiat.lower()},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return {
            asset: Decimal(str(data[coin_id][fiat.lower()]))
            for asset, coin_id in _COINGECKO_IDS.items()
        }


class StaticRates:
    """Used in tests and offline demos."""

    def __init__(self, rates: dict[Asset, Decimal]):
        self._rates = rates

    async def fiat_rates(self, fiat: str) -> dict[Asset, Decimal]:
        return self._rates
