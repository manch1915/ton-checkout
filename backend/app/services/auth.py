import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Mode
from app.infrastructure.db.models import ApiKey, Merchant

SESSION_COOKIE = "tc_session"
_JWT_ALG = "HS256"


class NonceStore(Protocol):
    async def put(self, nonce: str, ttl: int) -> None: ...

    async def consume(self, nonce: str) -> bool: ...


class AuthError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class IssuedKey:
    key: ApiKey
    secret: str


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_session(merchant_id: str, *, secret: str, ttl_hours: int) -> str:
    now = datetime.now(UTC)
    claims = {"sub": merchant_id, "iat": now, "exp": now + timedelta(hours=ttl_hours)}
    return jwt.encode(claims, secret, algorithm=_JWT_ALG)


def read_session(token: str, *, secret: str) -> str:
    try:
        claims = jwt.decode(token, secret, algorithms=[_JWT_ALG])
    except jwt.PyJWTError as exc:
        raise AuthError("session is invalid or expired") from exc
    return str(claims["sub"])


class ApiKeyService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def issue(self, merchant_id: str, mode: Mode, label: str) -> IssuedKey:
        raw = f"sk_{mode.value}_{secrets.token_urlsafe(24)}"
        key = ApiKey(
            merchant_id=merchant_id,
            mode=mode,
            label=label,
            prefix=raw[:12],
            key_hash=hash_api_key(raw),
        )
        self._session.add(key)
        await self._session.commit()
        return IssuedKey(key, raw)

    async def authenticate(self, raw: str) -> tuple[Merchant, ApiKey]:
        key = await self._session.scalar(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw), ApiKey.revoked_at.is_(None))
        )
        if key is None:
            raise AuthError("invalid API key")
        merchant = await self._session.get_one(Merchant, key.merchant_id)
        key.last_used_at = datetime.now(UTC)
        await self._session.commit()
        return merchant, key

    async def for_merchant(self, merchant_id: str) -> list[ApiKey]:
        rows = await self._session.scalars(
            select(ApiKey)
            .where(ApiKey.merchant_id == merchant_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(rows)

    async def revoke(self, merchant_id: str, key_id: str) -> bool:
        key = await self._session.get(ApiKey, key_id)
        if key is None or key.merchant_id != merchant_id:
            return False
        key.revoked_at = key.revoked_at or datetime.now(UTC)
        await self._session.commit()
        return True


class MerchantService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, merchant_id: str) -> Merchant | None:
        return await self._session.get(Merchant, merchant_id)

    async def login_wallet(self, owner_raw: str) -> Merchant:
        """First login with a wallet creates a merchant that receives payments to that wallet."""
        merchant = await self._session.scalar(
            select(Merchant).where(Merchant.owner_address == owner_raw)
        )
        if merchant is None:
            merchant = Merchant(name="My store", owner_address=owner_raw, wallet_address=owner_raw)
            self._session.add(merchant)
            await self._session.commit()
        return merchant

    async def demo(self) -> Merchant:
        merchant = await self._session.scalar(select(Merchant).where(Merchant.is_demo))
        if merchant is None:
            raise AuthError("demo merchant is not seeded")
        return merchant
