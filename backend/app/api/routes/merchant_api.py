"""Server-to-server API for merchants, authenticated with secret keys."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import ApiKeyDep, ContainerDep, SessionDep, rate_limit
from app.api.schemas import CreateInvoiceRequest, InvoicePage
from app.domain.enums import Asset, InvoiceStatus
from app.services.invoices import InvoiceError, InvoiceFilter
from app.services.views import InvoiceView

router = APIRouter(prefix="/v1", tags=["merchant API"], dependencies=[Depends(rate_limit)])


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: CreateInvoiceRequest, auth: ApiKeyDep, container: ContainerDep, session: SessionDep
) -> InvoiceView:
    merchant, key = auth
    try:
        invoice = await container.invoices(session).create(merchant, key.mode, body.to_command())
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return container.view(invoice)


@router.get("/invoices")
async def list_invoices(
    auth: ApiKeyDep,
    container: ContainerDep,
    session: SessionDep,
    status_: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    asset: Asset | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvoicePage:
    merchant, key = auth
    items, total = await container.invoices(session).page(
        merchant.id,
        InvoiceFilter(status=status_, asset=asset, mode=key.mode),
        limit=limit,
        offset=offset,
    )
    return InvoicePage(
        items=[container.view(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str, auth: ApiKeyDep, container: ContainerDep, session: SessionDep
) -> InvoiceView:
    merchant, _ = auth
    invoice = await container.invoices(session).get_for_merchant(merchant.id, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return container.view(invoice)


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: str, auth: ApiKeyDep, container: ContainerDep, session: SessionDep
) -> InvoiceView:
    merchant, _ = auth
    service = container.invoices(session)
    invoice = await service.get_for_merchant(merchant.id, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    try:
        invoice = await service.cancel(invoice)
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return container.view(invoice)
