"""
M:N tabulka uživatel × tenant (OZO multi-client podpora).

Hlavní use-case: OZO poradce má přístup k více tenantům (klientům).
Po loginu si vybere kontext, JWT obsahuje vybraný tenant_id.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class UserTenantMembership(Base, TimestampMixin):
    __tablename__ = "user_tenant_memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Role specifická pro tento tenant (OZO může mít v jiných tenantech
    # jinou roli). Při loginu se z této membership přečte role do JWT.
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
