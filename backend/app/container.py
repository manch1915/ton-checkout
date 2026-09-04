from dataclasses import dataclass
from decimal import Decimal

import httpx
from aiogram import Bot
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.infrastructure.bus import RedisBus
from app.infrastructure.db.models import Invoice
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.nonces import RedisNonceStore
from app.infrastructure.rates import MarketRates
from app.infrastructure.telegram import build_bot
from app.infrastructure.ton.address import to_raw
from app.infrastructure.ton.tonapi import TonApiProvider
from app.infrastructure.ton.toncenter import ToncenterProvider
from app.services.auth import NonceStore
from app.services.events import EventRecorder
from app.services.invoices import InvoiceService, PricingConfig
from app.services.payments import PaymentProcessor
from app.services.ports import ChainProvider, EventBus, RateSource
from app.services.ton_proof import MAINNET_CHAIN, TESTNET_CHAIN, TonProofVerifier
from app.services.views import InvoiceView, invoice_view
from app.services.watcher import ChainWatcher
from app.services.webhooks import WebhookDispatcher


@dataclass
class Container:
    """Everything with a lifetime longer than one request. Built once per process."""

    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    bus: EventBus
    provider: ChainProvider
    rates: RateSource
    nonces: NonceStore
    redis: Redis | None = None
    bot: Bot | None = None

    @property
    def usdt_master(self) -> str | None:
        master = self.settings.usdt_jetton_master
        return to_raw(master) if master else None

    def view(self, invoice: Invoice) -> InvoiceView:
        return invoice_view(
            invoice, public_url=self.settings.public_url, testnet=self.settings.is_testnet
        )

    def events(self, session: AsyncSession) -> EventRecorder:
        return EventRecorder(
            session, self.bus, public_url=self.settings.public_url, testnet=self.settings.is_testnet
        )

    def invoices(self, session: AsyncSession) -> InvoiceService:
        pricing = PricingConfig(
            usdt_enabled=self.usdt_master is not None,
            stars_per_usd=Decimal(str(self.settings.stars_per_usd)),
        )
        return InvoiceService(session, self.rates, self.events(session), pricing)

    def processor(self, session: AsyncSession) -> PaymentProcessor:
        return PaymentProcessor(
            session,
            self.events(session),
            usdt_master=self.usdt_master,
            tolerance_nano=self.settings.underpay_tolerance_nano,
            dust_nano=self.settings.dust_threshold_nano,
        )

    def watcher(self) -> ChainWatcher:
        keyless = self.settings.toncenter_api_key is None and self.provider.name == "toncenter"
        return ChainWatcher(
            self.sessions,
            self.provider,
            self.processor,
            usdt_master=self.usdt_master,
            request_gap=1.1 if keyless else 0.15,
        )

    def dispatcher(self) -> WebhookDispatcher:
        return WebhookDispatcher(
            self.sessions,
            self.http,
            retry_speedup=self.settings.webhook_retry_speedup,
            trusted_urls=frozenset({self.settings.shop_webhook_url}),
            allow_private=self.settings.env == "dev",
        )

    def proof_verifier(self) -> TonProofVerifier:
        domains = tuple(d.strip() for d in self.settings.ton_proof_domain.split(",") if d.strip())
        return TonProofVerifier(
            self.provider,
            allowed_domains=domains,
            network=TESTNET_CHAIN if self.settings.is_testnet else MAINNET_CHAIN,
            ttl=self.settings.ton_proof_ttl_seconds,
        )

    async def close(self) -> None:
        await self.http.aclose()
        if self.redis is not None:
            await self.redis.aclose()
        if self.bot is not None:
            await self.bot.session.close()
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url)
    http = httpx.AsyncClient(headers={"User-Agent": "ton-checkout/0.1"})
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    provider: ChainProvider
    if settings.ton_provider == "tonapi":
        key = settings.tonapi_api_key.get_secret_value() if settings.tonapi_api_key else None
        provider = TonApiProvider(http, testnet=settings.is_testnet, api_key=key)
    else:
        key = settings.toncenter_api_key.get_secret_value() if settings.toncenter_api_key else None
        provider = ToncenterProvider(http, testnet=settings.is_testnet, api_key=key)
    return Container(
        settings=settings,
        engine=engine,
        sessions=create_session_factory(engine),
        http=http,
        bus=RedisBus(redis),
        provider=provider,
        rates=MarketRates(
            http,
            ttl=settings.rates_ttl_seconds,
            fallback_ton_usd=Decimal(str(settings.fallback_ton_usd)),
        ),
        nonces=RedisNonceStore(redis),
        redis=redis,
        bot=build_bot(settings),
    )
