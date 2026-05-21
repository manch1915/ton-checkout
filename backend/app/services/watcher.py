import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import partial

import httpx
import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enums import InvoiceStatus
from app.domain.matching import IncomingTransfer
from app.infrastructure.db.models import Invoice, WatchCursor
from app.services.payments import PaymentProcessor, ProcessResult, TransferSource
from app.services.ports import ChainProvider, TransferPage

log = structlog.get_logger()

# Late payments still get matched for a day after the invoice expires.
LATE_WINDOW = timedelta(hours=24)
PAGE = 50

ProcessorFactory = Callable[[AsyncSession], PaymentProcessor]


class ChainWatcher:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        provider: ChainProvider,
        processor_factory: ProcessorFactory,
        *,
        usdt_master: str | None,
        request_gap: float = 0.0,
    ):
        self._factory = factory
        self._provider = provider
        self._processor_factory = processor_factory
        self._usdt_master = usdt_master
        # toncenter without a key allows about one request per second.
        self._gap = request_gap

    async def watched_accounts(self) -> dict[str, datetime]:
        """Merchant wallets with something to wait for, and since when to look."""
        now = datetime.now(UTC)
        async with self._factory() as session:
            rows = await session.execute(
                select(Invoice.recipient_address, Invoice.created_at).where(
                    or_(
                        Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.PARTIALLY_PAID]),
                        (Invoice.status == InvoiceStatus.EXPIRED)
                        & (Invoice.expires_at > now - LATE_WINDOW),
                    )
                )
            )
            accounts: dict[str, datetime] = {}
            for address, created in rows:
                accounts[address] = min(created, accounts.get(address, created))
            return accounts

    async def tick(self) -> int:
        processed = 0
        for account, since in (await self.watched_accounts()).items():
            processed += await self._scan(f"ton:{account}", since, partial(self._ton_page, account))
            if self._usdt_master:
                processed += await self._scan(
                    f"usdt:{account}", since, partial(self._jetton_page, account, self._usdt_master)
                )
        return processed

    async def _ton_page(self, account: str, after_lt: int, since: int) -> TransferPage:
        return await self._provider.incoming_ton(account, after_lt, PAGE, since)

    async def _jetton_page(
        self, account: str, master: str, after_lt: int, since: int
    ) -> TransferPage:
        return await self._provider.incoming_jettons(account, master, after_lt, PAGE, since)

    async def _scan(
        self,
        key: str,
        since: datetime,
        fetch: Callable[[int, int], Awaitable[TransferPage]],
    ) -> int:
        async with self._factory() as session:
            cursor = await session.get(WatchCursor, key)
            after_lt = cursor.last_lt if cursor else 0
        processed = 0
        while True:
            try:
                page = await fetch(after_lt, int(since.timestamp()) - 60)
            except httpx.HTTPError as exc:
                log.warning("watcher.provider_error", key=key, error=str(exc))
                return processed
            finally:
                if self._gap:
                    await asyncio.sleep(self._gap)
            for transfer in page.items:
                await self._process(transfer)
                processed += 1
            if page.last_lt > after_lt:
                after_lt = page.last_lt
                await self._save_cursor(key, after_lt)
            if not page.has_more:
                return processed

    async def _process(self, transfer: IncomingTransfer) -> ProcessResult:
        async with self._factory() as session:
            return await self._processor_factory(session).process(transfer, TransferSource.CHAIN)

    async def _save_cursor(self, key: str, lt: int) -> None:
        async with self._factory() as session:
            cursor = await session.get(WatchCursor, key)
            if cursor is None:
                session.add(WatchCursor(key=key, last_lt=lt))
            else:
                cursor.last_lt = max(cursor.last_lt, lt)
            await session.commit()

    async def rescan(self, account: str, since: datetime) -> int:
        """Re-read history from a point in time. Already seen transfers are skipped by tx hash."""
        processed = 0
        ton = await self._provider.incoming_ton(account, 0, 100, int(since.timestamp()))
        for transfer in ton.items:
            await self._process(transfer)
            processed += 1
        if self._usdt_master:
            jettons = await self._provider.incoming_jettons(
                account, self._usdt_master, 0, 100, int(since.timestamp())
            )
            for transfer in jettons.items:
                await self._process(transfer)
                processed += 1
        return processed
