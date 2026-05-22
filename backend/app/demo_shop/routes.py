import secrets
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import ContainerDep, SessionDep, rate_limit
from app.core import signing
from app.demo_shop.catalog import CATALOG, Product, find_product
from app.demo_shop.models import ShopOrder
from app.domain.enums import Asset, Channel, EventType, Mode
from app.domain.payment_policy import allowed_assets
from app.infrastructure.db.models import Merchant, WebhookEndpoint, new_id
from app.services.invoices import InvoiceError, NewInvoice

log = structlog.get_logger()
router = APIRouter(prefix="/api/shop", tags=["demo shop"], dependencies=[Depends(rate_limit)])


class ProductView(BaseModel):
    id: str
    title: str
    subtitle: str
    kind: str
    badge: str
    price: Decimal
    stars: int | None
    methods: list[Asset]
    policy_note: str


class NewOrder(BaseModel):
    product_id: str
    channel: Channel = Channel.WEB


class OrderView(BaseModel):
    id: str
    status: str
    product: ProductView
    invoice_id: str
    pay_url: str
    access_code: str | None
    fulfilled_at: datetime | None


def _product_view(product: Product, channel: Channel) -> ProductView:
    decision = allowed_assets(product.kind, channel)
    return ProductView(
        id=product.id,
        title=product.title,
        subtitle=product.subtitle,
        kind=product.kind.value,
        badge=product.badge,
        price=product.price,
        stars=product.stars,
        methods=list(decision.allowed),
        policy_note=decision.note,
    )


async def _demo_merchant(session: SessionDep) -> Merchant:
    merchant = await session.scalar(select(Merchant).where(Merchant.is_demo))
    if merchant is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "demo store is not seeded")
    return merchant


def _order_view(order: ShopOrder, container: ContainerDep) -> OrderView:
    product = find_product(order.product_id)
    assert product is not None
    return OrderView(
        id=order.id,
        status=order.status,
        product=_product_view(product, Channel(order.channel)),
        invoice_id=order.invoice_id,
        pay_url=f"{container.settings.public_url}/pay/{order.invoice_id}",
        access_code=order.access_code,
        fulfilled_at=order.fulfilled_at,
    )


@router.get("/products")
async def products(channel: Channel = Channel.WEB) -> list[ProductView]:
    return [_product_view(p, channel) for p in CATALOG]


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_order(body: NewOrder, container: ContainerDep, session: SessionDep) -> OrderView:
    product = find_product(body.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown product")
    merchant = await _demo_merchant(session)
    order = ShopOrder(
        id=new_id("ord"), product_id=product.id, channel=body.channel.value, invoice_id=""
    )
    try:
        invoice = await container.invoices(session).create(
            merchant,
            Mode.TEST,
            NewInvoice(
                fiat_amount=product.price,
                description=product.title,
                product_kind=product.kind,
                channel=body.channel,
                order_id=order.id,
                stars_amount=product.stars,
                return_url=f"{container.settings.public_url}/shop/orders/{order.id}",
                metadata={"shop_order": order.id, "product": product.id},
            ),
        )
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    order.invoice_id = invoice.id
    session.add(order)
    await session.commit()
    return _order_view(order, container)


@router.get("/orders/{order_id}")
async def get_order(order_id: str, container: ContainerDep, session: SessionDep) -> OrderView:
    order = await session.get(ShopOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    return _order_view(order, container)


class Ack(BaseModel):
    ok: bool


@router.post("/webhook")
async def receive_webhook(request: Request, container: ContainerDep, session: SessionDep) -> Ack:
    """What a merchant's backend does with our webhook: verify the signature, then fulfil."""
    body = await request.body()
    secrets_on_file = await session.scalars(
        select(WebhookEndpoint.secret)
        .join(Merchant, Merchant.id == WebhookEndpoint.merchant_id)
        .where(Merchant.is_demo, WebhookEndpoint.url == container.settings.shop_webhook_url)
    )
    headers = dict(request.headers)
    if not any(signing.verify(s, body, headers) for s in secrets_on_file):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")

    event = await request.json()
    if event.get("type") != EventType.INVOICE_PAID.value:
        return Ack(ok=True)
    invoice = event["data"].get("invoice") or {}
    order_id = (invoice.get("metadata") or {}).get("shop_order")
    order = await session.get(ShopOrder, order_id) if order_id else None
    if order is None or order.status == "fulfilled":
        # Webhooks can arrive more than once, fulfilment must be idempotent.
        return Ack(ok=True)
    order.status = "fulfilled"
    order.access_code = secrets.token_hex(4).upper()
    order.fulfilled_at = datetime.now(UTC)
    await session.commit()
    log.info("shop.fulfilled", order=order.id, invoice=invoice.get("id"))
    return Ack(ok=True)
