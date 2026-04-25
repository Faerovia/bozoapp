import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentDomain = Literal["bozp", "po"]


class DocumentFolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    domain: DocumentDomain
    parent_id: uuid.UUID | None = None


class DocumentFolderUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    sort_order: int | None = Field(None, ge=0)


class DocumentFolderResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    parent_id: uuid.UUID | None
    code: str
    name: str
    domain: str
    sort_order: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentImportRequest(BaseModel):
    """Import existujícího dokumentu jako Markdown text."""
    title: str = Field(..., min_length=1, max_length=255)
    content_md: str = Field(..., min_length=1)
    folder_id: uuid.UUID | None = None
