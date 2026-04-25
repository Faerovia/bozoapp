import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Relativní cesta v UPLOAD_DIR k logu firmy (PNG/JPG, max 1 MB).
    # Používá se v certifikátech školení. Migrace 022.
    logo_path: Mapped[str | None] = mapped_column(String(500))
    # Pokud True, zaměstnanci/HR klienta se mohou logovat do tenantu.
    # Pokud False, tenant je OZO-only (ostatní role nemají vlastní login).
    # Migrace 026.
    external_login_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Billing — eviduje a edituje pouze platform admin. Migrace 035.
    billing_type: Mapped[str | None] = mapped_column(String(20))
    billing_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    billing_currency: Mapped[str] = mapped_column(
        String(3), default="CZK", nullable=False,
    )
    billing_note: Mapped[str | None] = mapped_column(Text)
