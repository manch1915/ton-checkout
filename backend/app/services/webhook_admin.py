import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DeliveryState
from app.infrastructure.db.models import Event, WebhookAttempt, WebhookDelivery, WebhookEndpoint
from app.services.webhooks import (
    WebhookUrlError,
    new_webhook_secret,
    redeliver,
    send_test_event,
    validate_webhook_url,
)

MAX_ENDPOINTS = 5


class WebhookAdminError(Exception):
    pass


class WebhookAdmin:
    def __init__(
        self, session: AsyncSession, *, allow_private: bool, allowed_hosts: tuple[str, ...]
    ):
        self._session = session
        self._allow_private = allow_private
        self._allowed_hosts = allowed_hosts

    async def endpoints(self, merchant_id: str) -> list[WebhookEndpoint]:
        rows = await self._session.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.merchant_id == merchant_id)
            .order_by(WebhookEndpoint.created_at)
        )
        return list(rows)

    async def endpoint(self, merchant_id: str, endpoint_id: str) -> WebhookEndpoint:
        endpoint = await self._session.get(WebhookEndpoint, endpoint_id)
        if endpoint is None or endpoint.merchant_id != merchant_id:
            raise WebhookAdminError("endpoint not found")
        return endpoint

    async def create(self, merchant_id: str, url: str) -> WebhookEndpoint:
        if len(await self.endpoints(merchant_id)) >= MAX_ENDPOINTS:
            raise WebhookAdminError(f"up to {MAX_ENDPOINTS} endpoints per store")
        try:
            # getaddrinfo blocks, keep it off the event loop.
            await asyncio.to_thread(
                validate_webhook_url,
                url,
                allow_private=self._allow_private,
                allowed_hosts=self._allowed_hosts,
            )
        except WebhookUrlError as exc:
            raise WebhookAdminError(str(exc)) from exc
        endpoint = WebhookEndpoint(merchant_id=merchant_id, url=url, secret=new_webhook_secret())
        self._session.add(endpoint)
        await self._session.commit()
        return endpoint

    async def set_enabled(
        self, merchant_id: str, endpoint_id: str, enabled: bool
    ) -> WebhookEndpoint:
        endpoint = await self.endpoint(merchant_id, endpoint_id)
        endpoint.enabled = enabled
        await self._session.commit()
        return endpoint

    async def rotate_secret(self, merchant_id: str, endpoint_id: str) -> WebhookEndpoint:
        endpoint = await self.endpoint(merchant_id, endpoint_id)
        endpoint.secret = new_webhook_secret()
        await self._session.commit()
        return endpoint

    async def delete(self, merchant_id: str, endpoint_id: str) -> None:
        endpoint = await self.endpoint(merchant_id, endpoint_id)
        await self._session.delete(endpoint)
        await self._session.commit()

    async def send_test(self, merchant_id: str, endpoint_id: str) -> WebhookDelivery:
        return await send_test_event(self._session, await self.endpoint(merchant_id, endpoint_id))

    async def deliveries(
        self,
        merchant_id: str,
        *,
        endpoint_id: str | None = None,
        invoice_id: str | None = None,
        state: DeliveryState | None = None,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        query = (
            select(WebhookDelivery)
            .join(Event, Event.id == WebhookDelivery.event_id)
            .where(Event.merchant_id == merchant_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        if endpoint_id:
            query = query.where(WebhookDelivery.endpoint_id == endpoint_id)
        if invoice_id:
            query = query.where(Event.invoice_id == invoice_id)
        if state:
            query = query.where(WebhookDelivery.state == state)
        return list(await self._session.scalars(query))

    async def delivery(
        self, merchant_id: str, delivery_id: str
    ) -> tuple[WebhookDelivery, list[WebhookAttempt]]:
        delivery = await self._session.get(WebhookDelivery, delivery_id)
        if delivery is None or delivery.event.merchant_id != merchant_id:
            raise WebhookAdminError("delivery not found")
        attempts = await self._session.scalars(
            select(WebhookAttempt)
            .where(WebhookAttempt.delivery_id == delivery_id)
            .order_by(WebhookAttempt.number)
        )
        return delivery, list(attempts)

    async def resend(self, merchant_id: str, delivery_id: str) -> WebhookDelivery:
        delivery, _ = await self.delivery(merchant_id, delivery_id)
        await redeliver(self._session, delivery)
        return delivery
