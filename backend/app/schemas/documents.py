"""Schémata pro generated_documents."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentType = Literal[
    "bozp_directive",
    "training_outline",
    "revision_schedule",
    "risk_categorization",
]


class GenerateDocumentRequest(BaseModel):
    document_type: DocumentType
    # Volitelné parametry (např. pro training_outline: position_id)
    params: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    content_md: str | None = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    document_type: str
    title: str
    content_md: str
    params: dict[str, Any]
    ai_input_tokens: int | None
    ai_output_tokens: int | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    """List view bez content_md (úspora payload)."""
    id: uuid.UUID
    document_type: str
    title: str
    ai_input_tokens: int | None
    ai_output_tokens: int | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
