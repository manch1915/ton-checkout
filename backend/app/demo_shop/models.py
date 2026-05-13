from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Base, new_id, utcnow


class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ord"))
    product_id: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(32))
    invoice_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="awaiting_payment")
    access_code: Mapped[str | None] = mapped_column(String(32))
    fulfilled_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
