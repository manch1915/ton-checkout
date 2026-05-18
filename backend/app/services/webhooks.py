import ipaddress
import json
import random
import socket
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.signing import new_secret, signed_headers
from app.domain.enums import DeliveryState, EventType
from app.infrastructure.db.models import Event, WebhookAttempt, WebhookDelivery, WebhookEndpoint

log = structlog.get_logger()

# Delay before attempt N+1, roughly three days in total, the same curve as Standard Webhooks.
RETRY_SCHEDULE = (
    timedelta(seconds=5),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=5),
    timedelta(hours=10),
    timedelta(hours=14),
    timedelta(hours=20),
    timedelta(hours=24),
)
MAX_ATTEMPTS = len(RETRY_SCHEDULE) + 1


class WebhookUrlError(ValueError):
    pass


def validate_webhook_url(url: str, *, allow_private: bool, allowed_hosts: tuple[str, ...]) -> str:
    """Reject URLs that would make our worker call into a private network (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebhookUrlError("URL must start with http:// or https://")
    host = parsed.hostname.lower()
    if host in allowed_hosts or allow_private:
        return url
    if parsed.scheme != "https":
        raise WebhookUrlError("use an https:// URL")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise WebhookUrlError(f"cannot resolve {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WebhookUrlError("URL points to a private network address")
    return url


def new_webhook_secret() -> str:
    return new_secret()


def event_body(event: Event) -> bytes:
    body = {
        "id": event.id,
        "type": event.type.value,
        "created_at": event.created_at.isoformat(),
        "data": event.payload,
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode()


def next_attempt_delay(attempts_made: int, *, speedup: float = 1.0) -> timedelta | None:
    if attempts_made >= MAX_ATTEMPTS:
        return None
    base = RETRY_SCHEDULE[attempts_made - 1] / speedup
    # Jitter keeps a recovering endpoint from getting every retry at the same second.
    return base * random.uniform(0.9, 1.1)  # noqa: S311


class WebhookDispatcher:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        client: httpx.AsyncClient,
        *,
        retry_speedup: float = 1.0,
    ):
        self._factory = factory
        self._client = client
        self._speedup = retry_speedup

    async def run_due(self, batch: int = 20) -> int:
        async with self._factory() as session:
            due = list(
                await session.scalars(
                    select(WebhookDelivery)
                    .where(WebhookDelivery.state == DeliveryState.PENDING)
                    .where(WebhookDelivery.next_attempt_at <= datetime.now(UTC))
                    .order_by(WebhookDelivery.next_attempt_at)
                    .limit(batch)
                    .with_for_update(skip_locked=True, of=WebhookDelivery)
                )
            )
            for delivery in due:
                await self._attempt(session, delivery)
            await session.commit()
        return len(due)

    async def _attempt(self, session: AsyncSession, delivery: WebhookDelivery) -> None:
        body = event_body(delivery.event)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "TonCheckout-Webhooks/1.0",
            **signed_headers(delivery.endpoint.secret, delivery.event.id, body),
        }
        started = time.perf_counter()
        status_code: int | None = None
        error: str | None = None
        excerpt: str | None = None
        try:
            response = await self._client.post(
                delivery.endpoint.url, content=body, headers=headers, timeout=10
            )
            status_code = response.status_code
            excerpt = response.text[:500]
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
        duration = int((time.perf_counter() - started) * 1000)

        delivery.attempts += 1
        delivery.last_status_code = status_code
        delivery.last_error = error
        session.add(
            WebhookAttempt(
                delivery_id=delivery.id,
                number=delivery.attempts,
                status_code=status_code,
                duration_ms=duration,
                error=error,
                response_excerpt=excerpt,
            )
        )
        if status_code is not None and 200 <= status_code < 300:
            delivery.state = DeliveryState.SUCCEEDED
            delivery.next_attempt_at = None
            return
        delay = next_attempt_delay(delivery.attempts, speedup=self._speedup)
        if delay is None:
            delivery.state = DeliveryState.FAILED
            delivery.next_attempt_at = None
            log.warning("webhook.gave_up", delivery=delivery.id, url=delivery.endpoint.url)
        else:
            delivery.next_attempt_at = datetime.now(UTC) + delay


async def redeliver(session: AsyncSession, delivery: WebhookDelivery) -> None:
    delivery.state = DeliveryState.PENDING
    delivery.next_attempt_at = datetime.now(UTC)
    await session.commit()


async def send_test_event(session: AsyncSession, endpoint: WebhookEndpoint) -> WebhookDelivery:
    event = Event(
        merchant_id=endpoint.merchant_id,
        type=EventType.INVOICE_PAID,
        payload={"test": True, "message": "Test delivery from the dashboard"},
    )
    session.add(event)
    await session.flush()
    delivery = WebhookDelivery(
        event_id=event.id, endpoint_id=endpoint.id, next_attempt_at=datetime.now(UTC)
    )
    session.add(delivery)
    await session.commit()
    return delivery
