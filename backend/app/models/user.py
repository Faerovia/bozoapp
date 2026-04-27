import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Email je teď NULLABLE — zaměstnanci bez emailu se přihlašují
    # přes Employee.personal_number (per-tenant unique). Viz migrace 063
    # a subdomain login flow.
    email: Mapped[str | None] = mapped_column(String(255))
    # Volitelné username pro platform-admin login bez emailu.
    # Per uživatel UNIQUE napříč tenantů (partial unique index na username IS NOT NULL).
    username: Mapped[str | None] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="employee", nullable=False)
    # role: 'admin' | 'ozo' | 'hr_manager' | 'equipment_responsible' | 'employee'
    # admin = platform-level (SaaS operator); kombinace s is_platform_admin=True
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Platform admin flag — cross-tenant access pro SaaS operátora.
    # Pouze users s tímto flagem mohou používat /api/v1/admin/* endpointy.
    # RLS policy `platform_admin_bypass` na tenantovaných tabulkách checkuje
    # `app.is_platform_admin='true'` z DB settings, které app nastaví
    # v dependencies.get_current_user pokud user má tenhle flag.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 2FA (TOTP) — viz migrace 016
    # totp_secret je Fernet-encrypted base32 string (při čtení jde přes decrypt).
    totp_secret: Mapped[str | None] = mapped_column(String(256))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
