import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.container import Container
from app.core.config import Settings
from app.demo_shop import models as _shop_models  # noqa: F401  (registers the table)
from app.domain.enums import Asset
from app.domain.matching import IncomingTransfer
from app.infrastructure.bus import MemoryBus
from app.infrastructure.db.models import Base, Merchant
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.nonces import MemoryNonceStore
from app.infrastructure.rates import StaticRates
from app.infrastructure.ton.address import to_raw
from app.main import create_app
from app.services.ports import TransferPage

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://checkout:checkout@127.0.0.1:5452/checkout_test"
)
MERCHANT_WALLET = to_raw("0QD7ya0WKpRYHY4eKNdg4QE9J6CvVw-Ff7XNBAhj6eQOA_ML")
USDT_MASTER = "0:" + "c5" * 32
PAYER = "0:" + "11" * 32


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.ton: list[IncomingTransfer] = []
        self.jettons: list[IncomingTransfer] = []
        self.public_keys: dict[str, bytes] = {}

    async def incoming_ton(
        self, account: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage:
        items = [t for t in self.ton if t.lt > after_lt][:limit]
        return TransferPage(items, max([after_lt, *(t.lt for t in items)]), len(items) == limit)

    async def incoming_jettons(
        self, owner: str, jetton_master: str, after_lt: int, limit: int, since: int | None = None
    ) -> TransferPage:
        items = [t for t in self.jettons if t.lt > after_lt][:limit]
        return TransferPage(items, max([after_lt, *(t.lt for t in items)]), len(items) == limit)

    async def jetton_wallet_address(self, owner: str, jetton_master: str) -> str | None:
        return "0:" + "22" * 32

    async def wallet_public_key(self, address: str) -> bytes | None:
        return self.public_keys.get(address)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        env="test",
        database_url=TEST_DB,
        usdt_jetton_master=USDT_MASTER,
        public_url="http://shop.test",
        secret_key="test-secret-key-that-is-long-enough-1234",  # type: ignore[arg-type]
        ton_proof_domain="checkout.test",
        shop_webhook_url="http://api/api/shop/webhook",
        demo_wallet_address=MERCHANT_WALLET,
    )


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[object]:
    admin_url = TEST_DB.rsplit("/", 1)[0] + "/postgres"
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = TEST_DB.rsplit("/", 1)[1]
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("select 1 from pg_database where datname = :n"), {"n": db_name}
        )
        if not exists:
            await conn.execute(text(f'create database "{db_name}"'))
    await admin.dispose()

    engine = create_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def container(settings: Settings, engine: object) -> AsyncIterator[Container]:
    from sqlalchemy.ext.asyncio import AsyncEngine

    assert isinstance(engine, AsyncEngine)
    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"truncate {tables} restart identity cascade"))
    http = httpx.AsyncClient()
    yield Container(
        settings=settings,
        engine=engine,
        sessions=create_session_factory(engine),
        http=http,
        bus=MemoryBus(),
        provider=FakeProvider(),
        rates=StaticRates({Asset.TON: Decimal("1.25"), Asset.USDT: Decimal("1")}),
        nonces=MemoryNonceStore(),
    )
    await http.aclose()


@pytest.fixture
async def session(container: Container) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as s:
        yield s


@pytest.fixture
async def merchant(session: AsyncSession) -> Merchant:
    m = Merchant(name="Cellar Nine", wallet_address=MERCHANT_WALLET, is_demo=True)
    session.add(m)
    await session.commit()
    return m


@pytest.fixture
async def client(container: Container) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(container.settings, container)
    app.state.container = container
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://checkout.test") as c:
        yield c


def transfer(
    invoice_reference: str | None,
    amount: int,
    *,
    lt: int = 1,
    asset: Asset = Asset.TON,
    recipient: str = MERCHANT_WALLET,
    tx_hash: str | None = None,
    jetton_master: str | None = None,
    at: datetime | None = None,
) -> IncomingTransfer:
    return IncomingTransfer(
        tx_hash=tx_hash or f"{lt:064x}",
        lt=lt,
        asset=asset,
        amount=amount,
        sender=PAYER,
        recipient=recipient,
        comment=invoice_reference,
        occurred_at=at or datetime.now(UTC),
        jetton_master=jetton_master
        if jetton_master is not None
        else (USDT_MASTER if asset is Asset.USDT else None),
    )
