from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EventType
from app.infrastructure.db.models import Event, Invoice, WebhookDelivery, WebhookEndpoint
from app.services.ports import EventBus
from app.services.views import invoice_view


def invoice_channel(invoice_id: str) -> str:
    return f"invoice:{invoice_id}"


class EventRecorder:
    """Writes an event and its webhook deliveries in the caller's transaction.

    Live updates for the payment page are published only after commit, otherwise a buyer
    could see "paid" for a change that was rolled back.
    """

    def __init__(self, session: AsyncSession, bus: EventBus, *, public_url: str, testnet: bool):
        self._session = session
        self._bus = bus
        self._public_url = public_url
        self._testnet = testnet
        self._pending: list[tuple[str, dict[str, Any]]] = []

    async def record(
        self, invoice: Invoice, event_type: EventType, extra: dict[str, Any] | None = None
    ) -> Event:
        view = invoice_view(invoice, public_url=self._public_url, testnet=self._testnet)
        payload: dict[str, Any] = {"invoice": view.model_dump(mode="json")}
        if extra:
            payload.update(extra)
        event = Event(
            merchant_id=invoice.merchant_id, invoice_id=invoice.id, type=event_type, payload=payload
        )
        self._session.add(event)
        await self._session.flush()

        endpoints = await self._session.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.merchant_id == invoice.merchant_id, WebhookEndpoint.enabled
            )
        )
        now = datetime.now(UTC)
        for endpoint in endpoints:
            self._session.add(
                WebhookDelivery(event_id=event.id, endpoint_id=endpoint.id, next_attempt_at=now)
            )
        self._pending.append(
            (invoice_channel(invoice.id), {"type": event_type.value, "invoice": payload["invoice"]})
        )
        return event

    async def commit_and_publish(self) -> None:
        await self._session.commit()
        pending, self._pending = self._pending, []
        for channel, message in pending:
            await self._bus.publish(channel, message)
