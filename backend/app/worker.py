"""Background process: chain watcher, invoice expiry, webhook delivery and the Telegram bot."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import structlog

from app.bot.telegram import build_dispatcher
from app.container import Container, build_container
from app.core.config import get_settings
from app.core.logging import configure_logging

log = structlog.get_logger()


async def _loop(name: str, interval: float, step: Callable[[], Awaitable[int]]) -> None:
    while True:
        try:
            done = await step()
            if done:
                log.info(f"{name}.tick", count=done)
        except Exception:
            # One bad iteration must not stop payments from being picked up later.
            log.exception(f"{name}.failed")
        await asyncio.sleep(interval)


async def _expire(container: Container) -> int:
    async with container.sessions() as session:
        return await container.invoices(session).expire_due()


async def _run_bot(container: Container) -> None:
    """The bot is optional: a bad token or a Telegram outage must not stop payment processing."""
    assert container.bot is not None
    dispatcher = build_dispatcher(container)
    delay = 5.0
    while True:
        try:
            await dispatcher.start_polling(container.bot, handle_signals=False)
        except Exception:
            log.exception("bot.failed", retry_in=delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 300)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.env)
    container = build_container(settings)
    watcher = container.watcher()
    webhooks = container.dispatcher()
    tasks = [
        _loop("watcher", settings.watcher_interval_seconds, watcher.tick),
        _loop("expiry", 15, lambda: _expire(container)),
        _loop("webhooks", 2, webhooks.run_due),
    ]
    if container.bot is not None:
        tasks.append(_run_bot(container))
    log.info(
        "worker.started",
        network=settings.ton_network,
        provider=container.provider.name,
        bot=container.bot is not None,
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        await container.close()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
