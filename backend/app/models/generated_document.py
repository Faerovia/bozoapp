"""
Model pro AI/data-generované BOZP/PO dokumenty.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

DOCUMENT_TYPES = [
    "bozp_directive",       # Směrnice BOZP (AI)
    "training_outline",     # Osnova školení BOZP per pozice (AI)
    "revision_schedule",    # Harmonogram revizí (data-only)
    "risk_categorization",  # Tabulka kategorie rizik (data-only)
    "imported",             # Nahraný existující dokument (PDF/DOCX/MD/TXT)
]


class GeneratedDocument(Base, TimestampMixin):
    __tablename__ = "generated_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('bozp_directive', 'training_outline', "
            "'revision_schedule', 'risk_categorization', 'imported')",
            name="ck_doc_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_folders.id", ondelete="SET NULL"),
    )

    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    ai_input_tokens: Mapped[int | None] = mapped_column(Integer)
    ai_output_tokens: Mapped[int | None] = mapped_column(Integer)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
