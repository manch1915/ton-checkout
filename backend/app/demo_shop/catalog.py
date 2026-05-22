"""Catalog of the demo merchant, a small live-music club. It plays the role of the merchant's
own backend: it creates invoices and fulfils orders when our webhook arrives."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import ProductKind


@dataclass(frozen=True, slots=True)
class Product:
    id: str
    title: str
    subtitle: str
    kind: ProductKind
    price: Decimal
    stars: int | None
    badge: str


CATALOG: tuple[Product, ...] = (
    Product(
        "ticket-jazz-nov14",
        "Friday Jazz Night",
        "Fri 14 Nov, doors 20:00. Anna Melkonyan Trio",
        ProductKind.OFFLINE_SERVICE,
        Decimal("18.00"),
        None,
        "Ticket",
    ),
    Product(
        "ticket-neon-nov21",
        "Neon Harbor live",
        "Fri 21 Nov, doors 21:00. Synthwave set, standing",
        ProductKind.OFFLINE_SERVICE,
        Decimal("24.00"),
        None,
        "Ticket",
    ),
    Product(
        "pass-november",
        "November club pass",
        "Any 4 shows this month, skip the door queue",
        ProductKind.OFFLINE_SERVICE,
        Decimal("60.00"),
        None,
        "Pass",
    ),
    Product(
        "rec-jazz-oct",
        "Live recording: Jazz Night, October",
        "11 tracks, FLAC and MP3, mixed from the desk",
        ProductKind.DIGITAL,
        Decimal("6.00"),
        300,
        "Download",
    ),
    Product(
        "pack-neon-samples",
        "Neon Harbor sample pack",
        "64 one-shots and 12 loops, royalty free",
        ProductKind.DIGITAL,
        Decimal("12.00"),
        600,
        "Download",
    ),
    Product(
        "poster-season",
        "Season poster",
        "Printable PDF, A2 and A3",
        ProductKind.DIGITAL,
        Decimal("3.00"),
        150,
        "Download",
    ),
)


def find_product(product_id: str) -> Product | None:
    return next((p for p in CATALOG if p.id == product_id), None)
