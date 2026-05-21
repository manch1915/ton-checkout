import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, SessionDep, rate_limit
from app.infrastructure.db.models import Merchant
from app.services.auth import SESSION_COOKIE, AuthError, MerchantService, issue_session
from app.services.ton_proof import ProofError, TonProof

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(rate_limit)])


class PayloadResponse(BaseModel):
    payload: str


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


class SessionResponse(BaseModel):
    merchant_id: str
    name: str
    demo: bool


def _start_session(
    response: Response, container: ContainerDep, merchant: Merchant
) -> SessionResponse:
    settings = container.settings
    token = issue_session(
        merchant.id,
        secret=settings.secret_key.get_secret_value(),
        ttl_hours=settings.session_ttl_hours,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.env == "prod",
        samesite="lax",
    )
    return SessionResponse(merchant_id=merchant.id, name=merchant.name, demo=merchant.is_demo)


@router.post("/ton-proof/payload")
async def proof_payload(container: ContainerDep) -> PayloadResponse:
    payload = secrets.token_hex(32)
    await container.nonces.put(payload, container.settings.ton_proof_ttl_seconds)
    return PayloadResponse(payload=payload)


@router.post("/ton-proof/verify")
async def verify_proof(
    body: VerifyRequest, response: Response, container: ContainerDep, session: SessionDep
) -> SessionResponse:
    if not await container.nonces.consume(body.proof.payload):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "login request expired, try again")
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
        owner = await container.proof_verifier().verify(proof, expected_payload=body.proof.payload)
    except ProofError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    merchant = await MerchantService(session).login_wallet(owner)
    return _start_session(response, container, merchant)


@router.post("/demo")
async def demo_login(
    response: Response, container: ContainerDep, session: SessionDep
) -> SessionResponse:
    if not container.settings.demo_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demo is disabled")
    try:
        merchant = await MerchantService(session).demo()
    except AuthError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return _start_session(response, container, merchant)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
