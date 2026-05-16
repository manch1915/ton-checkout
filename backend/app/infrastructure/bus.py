import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis


class RedisBus:
    """Pub/sub between the watcher process and API instances holding SSE connections."""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self._redis.publish(channel, json.dumps(message, default=str))

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for raw in pubsub.listen():
                if raw.get("type") == "message":
                    yield json.loads(raw["data"])
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]


class MemoryBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        for queue in self._queues[channel]:
            queue.put_nowait(message)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[channel].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues[channel].remove(queue)
