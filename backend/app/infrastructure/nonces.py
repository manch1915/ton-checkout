import time

from redis.asyncio import Redis


class RedisNonceStore:
    def __init__(self, redis: Redis, prefix: str = "tonproof:"):
        self._redis = redis
        self._prefix = prefix

    async def put(self, nonce: str, ttl: int) -> None:
        await self._redis.set(self._prefix + nonce, "1", ex=ttl)

    async def consume(self, nonce: str) -> bool:
        # GETDEL is atomic, so one payload can back exactly one login.
        return await self._redis.getdel(self._prefix + nonce) is not None


class MemoryNonceStore:
    def __init__(self) -> None:
        self._items: dict[str, float] = {}

    async def put(self, nonce: str, ttl: int) -> None:
        self._items[nonce] = time.monotonic() + ttl

    async def consume(self, nonce: str) -> bool:
        expires = self._items.pop(nonce, None)
        return expires is not None and expires > time.monotonic()
