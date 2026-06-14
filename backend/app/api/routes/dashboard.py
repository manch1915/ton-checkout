import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import ContainerDep, MerchantDep, SessionDep, rate_limit
from app.api.schemas import CreateInvoiceRequest, InvoicePage, VerifyRequest, verify_wallet_proof
from app.domain.enums import Asset, DeliveryState, EventType, InvoiceStatus, Mode
from app.domain.pricing import format_units
from app.infrastructure.db.models import (
    ApiKey,
    Event,
    Invoice,
    Merchant,
    Transfer,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.infrastructure.ton.address import to_friendly
from app.services.auth import ApiKeyService
from app.services.invoices import InvoiceError, InvoiceFilter
from app.services.payments import Outcome
from app.services.stats import StatsService
from app.services.views import InvoiceView, TransferView, transfer_view
from app.services.webhook_admin import WebhookAdmin, WebhookAdminError

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(rate_limit)])


class MerchantProfile(BaseModel):
    id: str
    name: str
    wallet: str
    owner: str | None
    demo: bool
    accept_ton: bool
    accept_usdt: bool
    accept_stars: bool
    invoice_ttl_minutes: int
    network: str
    usdt_master: str | None
    provider: str
    bot_username: str | None


class SettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    accept_ton: bool | None = None
    accept_usdt: bool | None = None
    accept_stars: bool | None = None
    invoice_ttl_minutes: int | None = Field(default=None, ge=5, le=1440)


class DayPoint(BaseModel):
    day: date
    fiat: Decimal
    ton: Decimal
    usdt: Decimal
    stars: Decimal
    paid: int


class StatsResponse(BaseModel):
    days: list[DayPoint]
    gross_fiat: Decimal
    paid_count: int
    created_count: int
    expired_count: int
    conversion: float
    average_order: Decimal
    volume: dict[Asset, Decimal]
    unmatched_transfers: int
    webhook_success_rate: float | None


class EventView(BaseModel):
    id: str
    type: EventType
    created_at: datetime


class DeliveryView(BaseModel):
    id: str
    event_id: str
    event_type: EventType
    invoice_id: str | None
    endpoint_url: str
    state: DeliveryState
    attempts: int
    last_status_code: int | None
    last_error: str | None
    next_attempt_at: datetime | None
    created_at: datetime


class AttemptView(BaseModel):
    number: int
    status_code: int | None
    duration_ms: int
    error: str | None
    response_excerpt: str | None
    created_at: datetime


class DeliveryDetail(BaseModel):
    delivery: DeliveryView
    payload: dict[str, object]
    attempts: list[AttemptView]


class InvoiceDetail(BaseModel):
    invoice: InvoiceView
    transfers: list[TransferView]
    events: list[EventView]
    deliveries: list[DeliveryView]


class UnmatchedTransfer(BaseModel):
    id: int
    transfer: TransferView
    note: str | None


class AssignRequest(BaseModel):
    invoice_id: str


class AssignResponse(BaseModel):
    outcome: Outcome
    status: InvoiceStatus | None
    note: str | None


class ApiKeyView(BaseModel):
    id: str
    label: str
    mode: Mode
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class NewApiKeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    mode: Mode = Mode.TEST


class NewApiKeyResponse(BaseModel):
    key: ApiKeyView
    secret: str


class EndpointView(BaseModel):
    id: str
    url: str
    enabled: bool
    secret: str
    created_at: datetime


class NewEndpointRequest(BaseModel):
    url: str = Field(max_length=500)


class EndpointToggle(BaseModel):
    enabled: bool


class CreateDashboardInvoice(CreateInvoiceRequest):
    mode: Mode = Mode.TEST


def _profile(merchant: MerchantDep, container: ContainerDep) -> MerchantProfile:
    testnet = container.settings.is_testnet
    master = container.usdt_master
    return MerchantProfile(
        id=merchant.id,
        name=merchant.name,
        wallet=to_friendly(merchant.wallet_address, testnet=testnet),
        owner=to_friendly(merchant.owner_address, testnet=testnet)
        if merchant.owner_address
        else None,
        demo=merchant.is_demo,
        accept_ton=merchant.accept_ton,
        accept_usdt=merchant.accept_usdt,
        accept_stars=merchant.accept_stars,
        invoice_ttl_minutes=merchant.invoice_ttl_minutes,
        network=container.settings.ton_network,
        usdt_master=to_friendly(master, testnet=testnet, bounceable=True) if master else None,
        provider=container.provider.name,
        bot_username=container.settings.telegram_bot_username or None,
    )


def _delivery_view(delivery: WebhookDelivery) -> DeliveryView:
    return DeliveryView(
        id=delivery.id,
        event_id=delivery.event_id,
        event_type=delivery.event.type,
        invoice_id=delivery.event.invoice_id,
        endpoint_url=delivery.endpoint.url,
        state=delivery.state,
        attempts=delivery.attempts,
        last_status_code=delivery.last_status_code,
        last_error=delivery.last_error,
        next_attempt_at=delivery.next_attempt_at,
        created_at=delivery.created_at,
    )


def _webhooks(session: SessionDep, container: ContainerDep, merchant: Merchant) -> WebhookAdmin:
    # Only the demo store may point at our internal shop endpoint.
    trusted = {container.settings.shop_webhook_url} if merchant.is_demo else set()
    return WebhookAdmin(
        session, allow_private=container.settings.env == "dev", trusted_urls=frozenset(trusted)
    )


def _filter(
    status_: InvoiceStatus | None,
    asset: Asset | None,
    mode: Mode | None,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
) -> InvoiceFilter:
    return InvoiceFilter(
        status=status_,
        asset=asset,
        mode=mode,
        search=q,
        created_from=datetime.combine(date_from, time.min).astimezone() if date_from else None,
        created_to=datetime.combine(date_to + timedelta(days=1), time.min).astimezone()
        if date_to
        else None,
    )


FilterStatus = Annotated[InvoiceStatus | None, Query(alias="status")]
FilterFrom = Annotated[date | None, Query(alias="from")]
FilterTo = Annotated[date | None, Query(alias="to")]
FilterQ = Annotated[str | None, Query(max_length=80)]


@router.get("/me")
async def me(merchant: MerchantDep, container: ContainerDep) -> MerchantProfile:
    return _profile(merchant, container)


@router.patch("/settings")
async def update_settings(
    body: SettingsUpdate, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> MerchantProfile:
    for field in ("name", "accept_ton", "accept_usdt", "accept_stars", "invoice_ttl_minutes"):
        value = getattr(body, field)
        if value is not None:
            setattr(merchant, field, value)
    await session.commit()
    return _profile(merchant, container)


@router.post("/wallet")
async def change_wallet(
    body: VerifyRequest, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> MerchantProfile:
    """The receiving wallet changes only after a TON Connect proof from that wallet,
    otherwise anyone could point their store at someone else's wallet and its payments."""
    if merchant.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "the demo store keeps its wallet")
    wallet = await verify_wallet_proof(body, container)
    taken = await session.scalar(
        select(Merchant.id).where(Merchant.wallet_address == wallet, Merchant.id != merchant.id)
    )
    if taken:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this wallet already belongs to another store"
        )
    merchant.wallet_address = wallet
    await session.commit()
    return _profile(merchant, container)


@router.get("/stats")
async def stats(
    merchant: MerchantDep,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    mode: Mode | None = None,
) -> StatsResponse:
    summary = await StatsService(session).summary(merchant.id, mode, days)
    return StatsResponse(
        days=[
            DayPoint(
                day=d.day,
                fiat=d.fiat,
                ton=d.by_asset[Asset.TON],
                usdt=d.by_asset[Asset.USDT],
                stars=d.by_asset[Asset.STARS],
                paid=d.paid,
            )
            for d in summary.days
        ],
        gross_fiat=summary.gross_fiat,
        paid_count=summary.paid_count,
        created_count=summary.created_count,
        expired_count=summary.expired_count,
        conversion=summary.conversion,
        average_order=summary.average_order,
        volume=summary.volume_by_asset,
        unmatched_transfers=summary.unmatched_transfers,
        webhook_success_rate=summary.webhook_success_rate,
    )


@router.get("/invoices")
async def list_invoices(
    merchant: MerchantDep,
    container: ContainerDep,
    session: SessionDep,
    status_: FilterStatus = None,
    asset: Asset | None = None,
    mode: Mode | None = None,
    q: FilterQ = None,
    date_from: FilterFrom = None,
    date_to: FilterTo = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvoicePage:
    flt = _filter(status_, asset, mode, q, date_from, date_to)
    items, total = await container.invoices(session).page(
        merchant.id, flt, limit=limit, offset=offset
    )
    return InvoicePage(
        items=[container.view(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/invoices/export.csv")
async def export_invoices(
    merchant: MerchantDep,
    container: ContainerDep,
    session: SessionDep,
    status_: FilterStatus = None,
    asset: Asset | None = None,
    mode: Mode | None = None,
    q: FilterQ = None,
    date_from: FilterFrom = None,
    date_to: FilterTo = None,
) -> Response:
    rows = await container.invoices(session).export(
        merchant.id, _filter(status_, asset, mode, q, date_from, date_to)
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "created_at",
            "status",
            "mode",
            "order_id",
            "description",
            "fiat_amount",
            "fiat_currency",
            "asset",
            "amount_due",
            "received",
            "overpaid",
            "late",
            "paid_at",
            "payer",
            "reference",
        ]
    )
    testnet = container.settings.is_testnet
    for inv in rows:
        due = inv.quote(inv.asset) if inv.asset else None
        writer.writerow(
            [
                inv.id,
                inv.created_at.isoformat(),
                inv.status.value,
                inv.mode.value,
                inv.order_id or "",
                _csv_safe(inv.description),
                inv.fiat_amount,
                inv.fiat_currency,
                inv.asset.value if inv.asset else "",
                format_units(due, inv.asset) if inv.asset and due is not None else "",
                format_units(int(inv.received), inv.asset) if inv.asset else "0",
                format_units(int(inv.overpaid), inv.asset) if inv.asset else "0",
                "yes" if inv.late else "no",
                inv.paid_at.isoformat() if inv.paid_at else "",
                to_friendly(inv.payer_address, testnet=testnet) if inv.payer_address else "",
                inv.reference,
            ]
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="invoices-{stamp}.csv"'},
    )


def _csv_safe(value: str) -> str:
    # Spreadsheet apps execute cells that start with these characters as formulas.
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: CreateDashboardInvoice,
    merchant: MerchantDep,
    container: ContainerDep,
    session: SessionDep,
) -> InvoiceView:
    try:
        invoice = await container.invoices(session).create(merchant, body.mode, body.to_command())
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return container.view(invoice)


async def _own_invoice(
    invoice_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> Invoice:
    invoice = await container.invoices(session).get_for_merchant(merchant.id, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return invoice


@router.get("/invoices/{invoice_id}")
async def invoice_detail(
    invoice_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> InvoiceDetail:
    invoice = await _own_invoice(invoice_id, merchant, container, session)
    transfers = await container.invoices(session).transfers(invoice.id)
    events = await session.scalars(
        select(Event).where(Event.invoice_id == invoice.id).order_by(Event.created_at)
    )
    deliveries = await _webhooks(session, container, merchant).deliveries(
        merchant.id, invoice_id=invoice.id
    )
    testnet = container.settings.is_testnet
    return InvoiceDetail(
        invoice=container.view(invoice),
        transfers=[transfer_view(t, testnet=testnet) for t in transfers],
        events=[EventView(id=e.id, type=e.type, created_at=e.created_at) for e in events],
        deliveries=[_delivery_view(d) for d in deliveries],
    )


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> InvoiceView:
    invoice = await _own_invoice(invoice_id, merchant, container, session)
    try:
        invoice = await container.invoices(session).cancel(invoice)
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return container.view(invoice)


class RescanResponse(BaseModel):
    scanned: int


@router.post("/invoices/{invoice_id}/rescan")
async def rescan_invoice(
    invoice_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> RescanResponse:
    invoice = await _own_invoice(invoice_id, merchant, container, session)
    scanned = await container.watcher().rescan(
        invoice.recipient_address, invoice.created_at - timedelta(minutes=1)
    )
    return RescanResponse(scanned=scanned)


@router.get("/transfers/unmatched")
async def unmatched_transfers(
    merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> list[UnmatchedTransfer]:
    rows = await session.scalars(
        select(Transfer)
        .where(Transfer.invoice_id.is_(None), Transfer.recipient == merchant.wallet_address)
        .order_by(Transfer.occurred_at.desc())
        .limit(100)
    )
    testnet = container.settings.is_testnet
    return [
        UnmatchedTransfer(id=t.id, transfer=transfer_view(t, testnet=testnet), note=t.note)
        for t in rows
    ]


@router.post("/transfers/{transfer_id}/assign")
async def assign_transfer(
    transfer_id: int,
    body: AssignRequest,
    merchant: MerchantDep,
    container: ContainerDep,
    session: SessionDep,
) -> AssignResponse:
    result = await container.processor(session).assign(transfer_id, body.invoice_id, merchant.id)
    if result.outcome is not Outcome.MATCHED:
        raise HTTPException(status.HTTP_409_CONFLICT, result.note or "cannot assign this payment")
    return AssignResponse(outcome=result.outcome, status=result.status, note=result.note)


def _key_view(key: ApiKey) -> ApiKeyView:
    return ApiKeyView(
        id=key.id,
        label=key.label,
        mode=key.mode,
        prefix=key.prefix,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked=key.revoked_at is not None,
    )


@router.get("/api-keys")
async def list_keys(merchant: MerchantDep, session: SessionDep) -> list[ApiKeyView]:
    return [_key_view(k) for k in await ApiKeyService(session).for_merchant(merchant.id)]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_key(
    body: NewApiKeyRequest, merchant: MerchantDep, session: SessionDep
) -> NewApiKeyResponse:
    issued = await ApiKeyService(session).issue(merchant.id, body.mode, body.label)
    return NewApiKeyResponse(key=_key_view(issued.key), secret=issued.secret)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: str, merchant: MerchantDep, session: SessionDep) -> None:
    if not await ApiKeyService(session).revoke(merchant.id, key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")


def _endpoint_view(endpoint: WebhookEndpoint) -> EndpointView:
    return EndpointView(
        id=endpoint.id,
        url=endpoint.url,
        enabled=endpoint.enabled,
        secret=endpoint.secret,
        created_at=endpoint.created_at,
    )


@router.get("/webhooks")
async def list_endpoints(
    merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> list[EndpointView]:
    return [
        _endpoint_view(e)
        for e in await _webhooks(session, container, merchant).endpoints(merchant.id)
    ]


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    body: NewEndpointRequest, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> EndpointView:
    try:
        endpoint = await _webhooks(session, container, merchant).create(merchant.id, body.url)
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _endpoint_view(endpoint)


@router.patch("/webhooks/{endpoint_id}")
async def toggle_endpoint(
    endpoint_id: str,
    body: EndpointToggle,
    merchant: MerchantDep,
    container: ContainerDep,
    session: SessionDep,
) -> EndpointView:
    try:
        endpoint = await _webhooks(session, container, merchant).set_enabled(
            merchant.id, endpoint_id, body.enabled
        )
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _endpoint_view(endpoint)


@router.post("/webhooks/{endpoint_id}/rotate-secret")
async def rotate_secret(
    endpoint_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> EndpointView:
    try:
        endpoint = await _webhooks(session, container, merchant).rotate_secret(
            merchant.id, endpoint_id
        )
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _endpoint_view(endpoint)


@router.delete("/webhooks/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> None:
    try:
        await _webhooks(session, container, merchant).delete(merchant.id, endpoint_id)
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/webhooks/{endpoint_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def test_endpoint(
    endpoint_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> DeliveryView:
    try:
        delivery = await _webhooks(session, container, merchant).send_test(merchant.id, endpoint_id)
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.refresh(delivery, ["event", "endpoint"])
    return _delivery_view(delivery)


@router.get("/deliveries")
async def list_deliveries(
    merchant: MerchantDep,
    container: ContainerDep,
    session: SessionDep,
    endpoint_id: str | None = None,
    state: DeliveryState | None = None,
) -> list[DeliveryView]:
    deliveries = await _webhooks(session, container, merchant).deliveries(
        merchant.id, endpoint_id=endpoint_id, state=state
    )
    return [_delivery_view(d) for d in deliveries]


@router.get("/deliveries/{delivery_id}")
async def delivery_detail(
    delivery_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> DeliveryDetail:
    try:
        delivery, attempts = await _webhooks(session, container, merchant).delivery(
            merchant.id, delivery_id
        )
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return DeliveryDetail(
        delivery=_delivery_view(delivery),
        payload=delivery.event.payload,
        attempts=[
            AttemptView(
                number=a.number,
                status_code=a.status_code,
                duration_ms=a.duration_ms,
                error=a.error,
                response_excerpt=a.response_excerpt,
                created_at=a.created_at,
            )
            for a in attempts
        ],
    )


@router.post("/deliveries/{delivery_id}/resend")
async def resend_delivery(
    delivery_id: str, merchant: MerchantDep, container: ContainerDep, session: SessionDep
) -> DeliveryView:
    try:
        delivery = await _webhooks(session, container, merchant).resend(merchant.id, delivery_id)
    except WebhookAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _delivery_view(delivery)
