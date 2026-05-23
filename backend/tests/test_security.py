import base64
from dataclasses import replace

import pytest
from nacl.signing import SigningKey
from pytoniq_core import Address, StateInit, begin_cell

from app.core import signing
from app.services.ton_proof import (
    TESTNET_CHAIN,
    ProofError,
    TonProof,
    TonProofVerifier,
    proof_digest,
)
from app.services.webhooks import WebhookUrlError, validate_webhook_url
from tests.conftest import FakeProvider

DOMAIN = "checkout.test"


def test_webhook_signature_round_trip() -> None:
    secret = signing.new_secret()
    body = b'{"type":"invoice.paid"}'
    headers = signing.signed_headers(secret, "evt_1", body, timestamp=1_800_000_000)
    assert signing.verify(secret, body, headers, now=1_800_000_010)


def test_webhook_signature_rejects_tampering_and_replay() -> None:
    secret = signing.new_secret()
    body = b'{"amount":"1"}'
    headers = signing.signed_headers(secret, "evt_1", body, timestamp=1_800_000_000)
    assert not signing.verify(secret, b'{"amount":"9"}', headers, now=1_800_000_000)
    assert not signing.verify(signing.new_secret(), body, headers, now=1_800_000_000)
    assert not signing.verify(secret, body, headers, now=1_800_000_000 + 3600)


def test_webhook_signature_accepts_any_of_rotated_signatures() -> None:
    old, new = signing.new_secret(), signing.new_secret()
    body = b"{}"
    headers = signing.signed_headers(new, "evt_2", body, timestamp=100)
    headers["webhook-signature"] = (
        signing.sign(old, "evt_2", 100, body) + " " + headers["webhook-signature"]
    )
    assert signing.verify(new, body, headers, now=100)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "http://example.com/hook",
        "https://127.0.0.1/hook",
        "https://localhost/x",
    ],
)
def test_webhook_url_guard(url: str) -> None:
    with pytest.raises(WebhookUrlError):
        validate_webhook_url(url, allow_private=False, allowed_hosts=())


def test_webhook_url_allowlist_for_internal_service() -> None:
    url = "http://api/api/shop/webhook"
    assert validate_webhook_url(url, allow_private=False, allowed_hosts=("api",)) == url


def _wallet(key: SigningKey) -> tuple[str, str]:
    """A v4-like wallet: code is irrelevant here, data holds seqno, subwallet and the key."""
    code = begin_cell().store_uint(0xC0DE, 16).end_cell()
    data = (
        begin_cell()
        .store_uint(0, 32)
        .store_uint(698983191, 32)
        .store_bytes(bytes(key.verify_key))
        .store_bit(0)
        .end_cell()
    )
    cell = StateInit(code=code, data=data).serialize()
    address = Address((0, cell.hash)).to_str(is_user_friendly=False)
    return address, base64.b64encode(cell.to_boc()).decode()


def _proof(key: SigningKey, address: str, state_init: str, *, payload: str, ts: int) -> TonProof:
    addr = Address(address)
    digest = proof_digest(addr.wc, addr.hash_part, DOMAIN, ts, payload)
    return TonProof(
        address=address,
        network=TESTNET_CHAIN,
        timestamp=ts,
        domain=DOMAIN,
        domain_length=len(DOMAIN),
        payload=payload,
        signature=base64.b64encode(key.sign(digest).signature).decode(),
        state_init=state_init,
    )


def _verifier(provider: FakeProvider) -> TonProofVerifier:
    return TonProofVerifier(provider, allowed_domains=(DOMAIN,), network=TESTNET_CHAIN, ttl=900)


async def test_ton_proof_from_state_init_for_undeployed_wallet() -> None:
    key = SigningKey.generate()
    address, state_init = _wallet(key)
    proof = _proof(key, address, state_init, payload="p1", ts=1_800_000_000)
    owner = await _verifier(FakeProvider()).verify(proof, expected_payload="p1", now=1_800_000_100)
    assert owner == address.lower()


async def test_ton_proof_uses_live_key_when_wallet_rotated_it() -> None:
    old_key, new_key = SigningKey.generate(), SigningKey.generate()
    address, state_init = _wallet(old_key)
    provider = FakeProvider()
    provider.public_keys[address] = bytes(new_key.verify_key)
    stale = _proof(old_key, address, state_init, payload="p", ts=1_800_000_000)
    with pytest.raises(ProofError, match="signature"):
        await _verifier(provider).verify(stale, expected_payload="p", now=1_800_000_000)
    fresh = _proof(new_key, address, state_init, payload="p", ts=1_800_000_000)
    assert await _verifier(provider).verify(fresh, expected_payload="p", now=1_800_000_000)


async def test_ton_proof_rejects_foreign_state_init_domain_and_age() -> None:
    key, other = SigningKey.generate(), SigningKey.generate()
    address, _ = _wallet(key)
    _, foreign_init = _wallet(other)
    verifier = _verifier(FakeProvider())

    proof = _proof(key, address, foreign_init, payload="p", ts=1_800_000_000)
    with pytest.raises(ProofError, match="does not belong"):
        await verifier.verify(proof, expected_payload="p", now=1_800_000_000)

    _, own_init = _wallet(key)
    old = _proof(key, address, own_init, payload="p", ts=1_800_000_000)
    with pytest.raises(ProofError, match="too old"):
        await verifier.verify(old, expected_payload="p", now=1_800_010_000)

    wrong_domain = replace(old, domain="evil.test", domain_length=9)
    with pytest.raises(ProofError, match="domain"):
        await verifier.verify(wrong_domain, expected_payload="p", now=1_800_000_000)
