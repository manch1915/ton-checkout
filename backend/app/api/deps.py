import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.domain.enums import Mode
from app.infrastructure.db.models import ApiKey, Merchant
from app.services.auth import (
    SESSION_COOKIE,
    ApiKeyService,
    AuthError,
    MerchantService,
    read_session,
)


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_merchant(
    container: ContainerDep,
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Merchant:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in first")
    try:
        merchant_id = read_session(token, secret=container.settings.secret_key.get_secret_value())
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    merchant = await MerchantService(session).get(merchant_id)
    if merchant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "merchant not found")
    return merchant


MerchantDep = Annotated[Merchant, Depends(current_merchant)]


async def api_key_auth(
    session: SessionDep, authorization: Annotated[str | None, Header()] = None
) -> tuple[Merchant, ApiKey]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "pass your secret key as 'Authorization: Bearer sk_...'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await ApiKeyService(session).authenticate(authorization[7:].strip())
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


ApiKeyDep = Annotated[tuple[Merchant, ApiKey], Depends(api_key_auth)]


def mode_of(key: ApiKey) -> Mode:
    return key.mode


async def rate_limit(request: Request, container: ContainerDep) -> None:
    """Fixed one-minute window per client IP, kept in Redis so it holds across API replicas.

    The client IP comes from uvicorn, which reads X-Forwarded-For only from trusted proxies
    (--forwarded-allow-ips), so a caller cannot pick its own bucket.
    """
    redis = container.redis
    if redis is None:
        return
    client = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)
    key = f"rl:{client}:{window}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 61)
    if count > container.settings.rate_limit_per_minute:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many requests, slow down",
            headers={"Retry-After": str(60 - int(time.time()) % 60)},
        )
