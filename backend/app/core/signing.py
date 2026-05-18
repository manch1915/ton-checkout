"""Webhook signatures in the Standard Webhooks format (https://www.standardwebhooks.com).

Merchants can verify our requests with any of the existing Standard Webhooks libraries.
"""

import base64
import hashlib
import hmac
import secrets
import time

ID_HEADER = "webhook-id"
TIMESTAMP_HEADER = "webhook-timestamp"
SIGNATURE_HEADER = "webhook-signature"
SECRET_PREFIX = "whsec_"  # noqa: S105
DEFAULT_TOLERANCE_SECONDS = 300


def new_secret() -> str:
    return SECRET_PREFIX + base64.b64encode(secrets.token_bytes(24)).decode()


def _key(secret: str) -> bytes:
    return base64.b64decode(secret.removeprefix(SECRET_PREFIX))


def sign(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    to_sign = f"{msg_id}.{timestamp}.".encode() + body
    digest = hmac.new(_key(secret), to_sign, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def signed_headers(
    secret: str, msg_id: str, body: bytes, timestamp: int | None = None
) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else timestamp
    return {
        ID_HEADER: msg_id,
        TIMESTAMP_HEADER: str(ts),
        SIGNATURE_HEADER: sign(secret, msg_id, ts, body),
    }


def verify(
    secret: str,
    body: bytes,
    headers: dict[str, str],
    *,
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
    now: int | None = None,
) -> bool:
    lowered = {k.lower(): v for k, v in headers.items()}
    try:
        msg_id = lowered[ID_HEADER]
        ts = int(lowered[TIMESTAMP_HEADER])
        signatures = lowered[SIGNATURE_HEADER].split()
    except (KeyError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - ts) > tolerance:
        return False
    expected = sign(secret, msg_id, ts, body)
    # Several space-separated signatures are allowed, which is how secret rotation works.
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)
