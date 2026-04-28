"""Schémata pro generated_documents."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentType = Literal[
    "bozp_directive",
    "training_outline",
    "revision_schedule",
    "risk_categorization",
    "operating_log_summary",
    "risk_assessment",   # batch generation per scope
    "imported",
]

RiskAssessmentScopeFilter = Literal["position", "workplace", "plant"]


class GenerateDocumentRequest(BaseModel):
    document_type: DocumentType
    # Volitelné parametry (např. pro training_outline: position_id)
    params: dict[str, Any] = Field(default_factory=dict)
    folder_id: uuid.UUID | None = None


class GenerateRiskAssessmentBatchRequest(BaseModel):
    """Batch generování dokumentů 'Hodnocení rizik' — jeden per scope."""

    folder_id: uuid.UUID | None = None
    # Pokud nastaven, omezí generování jen na daný scope_type;
    # jinak generuje pro všechny tři (position + workplace + plant).
    scope_filter: RiskAssessmentScopeFilter | None = None


class GenerateRiskAssessmentBatchResponse(BaseModel):
    created_count: int
    documents: list["DocumentListItem"]


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    content_md: str | None = None
    folder_id: uuid.UUID | None = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    folder_id: uuid.UUID | None = None
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
    folder_id: uuid.UUID | None = None
    document_type: str
    title: str
    ai_input_tokens: int | None
    ai_output_tokens: int | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


GenerateRiskAssessmentBatchResponse.model_rebuild()
