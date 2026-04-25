"""
Adresářová struktura pro provozní/procesní dokumentaci.

Hierarchie přes self-FK `parent_id`. Code je full path:
  - root:    "000"
  - úroveň 1: "000.001"
  - úroveň 2: "000.001.005"

Číslování je automatické při vytvoření, přejmenování parent neovlivní
ulozený code potomků (uchovává se jako string, ne derivovaně).
"""

import uuid
from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

DocumentDomain = Literal["bozp", "po"]


class DocumentFolder(Base, TimestampMixin):
    __tablename__ = "document_folders"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('bozp', 'po')",
            name="ck_df_domain",
        ),
        UniqueConstraint(
            "tenant_id", "code", "domain",
            name="uq_df_tenant_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_folders.id", ondelete="RESTRICT"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(10), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
