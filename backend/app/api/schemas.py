from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from app.container import Container
from app.domain.enums import Asset, Channel, ProductKind
from app.services.invoices import NewInvoice
from app.services.ton_proof import ProofError, TonProof
from app.services.views import InvoiceView


class CreateInvoiceRequest(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("100000"), decimal_places=2, examples=["24.00"])
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: str = Field(min_length=1, max_length=240)
    order_id: str | None = Field(default=None, max_length=80)
    product_kind: ProductKind = ProductKind.DIGITAL
    channel: Channel = Channel.WEB
    assets: list[Asset] | None = Field(default=None, max_length=3)
    stars_amount: int | None = Field(default=None, gt=0, le=100_000)
    return_url: HttpUrl | None = None
    ttl_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=20)

    def to_command(self) -> NewInvoice:
        return NewInvoice(
            fiat_amount=self.amount,
            fiat_currency=self.currency,
            description=self.description,
            order_id=self.order_id,
            product_kind=self.product_kind,
            channel=self.channel,
            assets=tuple(self.assets) if self.assets else None,
            stars_amount=self.stars_amount,
            return_url=str(self.return_url) if self.return_url else None,
            ttl_minutes=self.ttl_minutes,
            metadata=self.metadata,
        )


class InvoicePage(BaseModel):
    items: list[InvoiceView]
    total: int
    limit: int
    offset: int


class ProofDomain(BaseModel):
    length_bytes: int = Field(alias="lengthBytes")
    value: str = Field(max_length=128)


class ProofBody(BaseModel):
    timestamp: int
    domain: ProofDomain
    payload: str = Field(max_length=128)
    signature: str = Field(max_length=200)
    state_init: str | None = Field(default=None, max_length=4096)


class VerifyRequest(BaseModel):
    address: str = Field(max_length=80)
    network: str = Field(max_length=8)
    proof: ProofBody


async def verify_wallet_proof(body: VerifyRequest, container: Container) -> str:
    """Check a TON Connect proof and burn its payload. Returns the raw wallet address."""
    if not await container.nonces.consume(body.proof.payload):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the request expired, connect again")
    proof = TonProof(
        address=body.address,
        network=body.network,
        timestamp=body.proof.timestamp,
        domain=body.proof.domain.value,
        domain_length=body.proof.domain.length_bytes,
        payload=body.proof.payload,
        signature=body.proof.signature,
        state_init=body.proof.state_init,
    )
    try:
        return await container.proof_verifier().verify(proof, expected_payload=body.proof.payload)
    except ProofError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
