import base64

from pytoniq_core import Address, Cell, begin_cell


def to_raw(address: str) -> str:
    """Canonical form for comparisons and storage: `0:abcd...` in lowercase."""
    return str(Address(address).to_str(is_user_friendly=False)).lower()


def to_friendly(address: str, *, testnet: bool, bounceable: bool = False) -> str:
    # Wallets expect non-bounceable addresses for plain payments to user wallets.
    return str(
        Address(address).to_str(
            is_user_friendly=True, is_bounceable=bounceable, is_url_safe=True, is_test_only=testnet
        )
    )


def is_valid(address: str) -> bool:
    try:
        Address(address)
    except Exception:
        return False
    return True


def b64_hash_to_hex(value: str) -> str:
    return base64.b64decode(value).hex()


def decode_text_comment(boc_b64: str | None) -> str | None:
    """Read an op=0 text comment from a message body BOC."""
    if not boc_b64:
        return None
    try:
        cell = Cell.one_from_boc(base64.b64decode(boc_b64))
        sl = cell.begin_parse()
        if sl.remaining_bits < 32 or sl.load_uint(32) != 0:
            return None
        text: str = sl.load_snake_string()
    except Exception:
        return None
    return text


def comment_payload(text: str) -> str:
    """Base64 BOC of a text comment, the same thing a wallet builds for `text=` links."""
    cell = begin_cell().store_uint(0, 32).store_snake_string(text).end_cell()
    return base64.b64encode(cell.to_boc()).decode()
