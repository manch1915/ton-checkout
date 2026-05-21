"""TON Connect `ton_proof` check.

Follows docs.ton.org/applications/ton-connect/how-to/ton-proof.
"""

import base64
import hashlib
import struct
import time
from dataclasses import dataclass

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from pytoniq_core import Address, Cell, StateInit

from app.services.ports import ChainProvider

PROOF_PREFIX = b"ton-proof-item-v2/"
CONNECT_PREFIX = b"ton-connect"
TESTNET_CHAIN = "-3"
MAINNET_CHAIN = "-239"

# Bit offset of the public key inside wallet data: v3/v4 keep seqno + subwallet_id before it,
# v5 adds a one-bit signature flag in front.
_KEY_OFFSETS = (64, 65)


class ProofError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TonProof:
    address: str
    network: str
    timestamp: int
    domain: str
    domain_length: int
    payload: str
    signature: str
    state_init: str | None


def proof_digest(
    workchain: int, address_hash: bytes, domain: str, timestamp: int, payload: str
) -> bytes:
    domain_bytes = domain.encode()
    message = (
        PROOF_PREFIX
        + struct.pack(">i", workchain)
        + address_hash
        + struct.pack("<I", len(domain_bytes))
        + domain_bytes
        + struct.pack("<Q", timestamp)
        + payload.encode()
    )
    return hashlib.sha256(b"\xff\xff" + CONNECT_PREFIX + hashlib.sha256(message).digest()).digest()


def _candidate_keys(state_init_b64: str, address: Address) -> list[bytes]:
    cell = Cell.one_from_boc(base64.b64decode(state_init_b64))
    if cell.hash != address.hash_part:
        raise ProofError("state_init does not belong to this address")
    data = StateInit.deserialize(cell.begin_parse()).data
    if data is None:
        return []
    keys = []
    for offset in _KEY_OFFSETS:
        sl = data.begin_parse()
        if sl.remaining_bits < offset + 256:
            continue
        sl.skip_bits(offset)
        keys.append(sl.load_bytes(32))
    return keys


class TonProofVerifier:
    def __init__(
        self, provider: ChainProvider, *, allowed_domains: tuple[str, ...], network: str, ttl: int
    ):
        self._provider = provider
        self._domains = allowed_domains
        self._network = network
        self._ttl = ttl

    async def verify(
        self, proof: TonProof, *, expected_payload: str, now: int | None = None
    ) -> str:
        """Return the raw address on success. Payload single-use is the caller's job."""
        if proof.network != self._network:
            raise ProofError("wallet is connected to another network")
        if proof.domain not in self._domains or proof.domain_length != len(proof.domain.encode()):
            raise ProofError("proof was issued for another domain")
        current = int(time.time()) if now is None else now
        if abs(current - proof.timestamp) > self._ttl:
            raise ProofError("proof is too old")
        if proof.payload != expected_payload:
            raise ProofError("unexpected payload")

        address = Address(proof.address)
        digest = proof_digest(
            address.wc, address.hash_part, proof.domain, proof.timestamp, proof.payload
        )
        signature = base64.b64decode(proof.signature)

        # A deployed wallet is asked for its current key, because some wallets
        # (Telegram Money / WalletTg) can rotate keys while keeping the address.
        live_key = await self._provider.wallet_public_key(address.to_str(is_user_friendly=False))
        if live_key is not None:
            candidates = [live_key]
        elif proof.state_init:
            candidates = _candidate_keys(proof.state_init, address)
        else:
            raise ProofError("cannot resolve the wallet public key")

        for key in candidates:
            try:
                VerifyKey(key).verify(digest, signature)
            except BadSignatureError:
                continue
            return str(address.to_str(is_user_friendly=False)).lower()
        raise ProofError("signature does not match")
