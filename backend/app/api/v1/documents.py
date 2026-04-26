"""
API pro AI/data-generované dokumenty (Směrnice BOZP, osnovy školení, harmonogramy).
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.documents import (
    DocumentListItem,
    DocumentResponse,
    DocumentUpdateRequest,
    GenerateDocumentRequest,
)
from app.services.document_pdf import render_document_pdf
from app.services.documents import (
    generate_document,
    get_document_by_id,
    list_documents,
    update_document,
)

router = APIRouter()


@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents_endpoint(
    document_type: str | None = Query(None),
    folder_id: uuid.UUID | None = Query(None),
    root_only: bool = Query(False, description="Vrátí jen dokumenty bez složky"),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    folder_id_set = root_only or folder_id is not None
    return await list_documents(
        db, current_user.tenant_id,
        document_type=document_type,
        folder_id=folder_id,
        folder_id_set=folder_id_set,
    )


@router.post(
    "/documents/generate",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_document_endpoint(
    data: GenerateDocumentRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        doc = await generate_document(
            db,
            tenant_id=current_user.tenant_id,
            document_type=data.document_type,
            params=data.params,
            created_by=current_user.id,
            folder_id=data.folder_id,
        )
    except RuntimeError as e:
        # Anthropic API klíč chybí
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    doc = await get_document_by_id(db, doc_id, current_user.tenant_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokument nenalezen")
    return doc


@router.patch("/documents/{doc_id}", response_model=DocumentResponse)
async def update_document_endpoint(
    doc_id: uuid.UUID,
    data: DocumentUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    doc = await get_document_by_id(db, doc_id, current_user.tenant_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokument nenalezen")
    folder_id_set = "folder_id" in data.model_fields_set
    return await update_document(
        db, doc,
        title=data.title,
        content_md=data.content_md,
        folder_id=data.folder_id,
        folder_id_set=folder_id_set,
    )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    doc = await get_document_by_id(db, doc_id, current_user.tenant_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokument nenalezen")
    await db.delete(doc)
    await db.flush()


@router.get("/documents/{doc_id}/pdf")
async def document_pdf(
    doc_id: uuid.UUID,
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Renderuje uložený MD content do PDF (fpdf2)."""
    doc = await get_document_by_id(db, doc_id, current_user.tenant_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokument nenalezen")

    tenant_res = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_res.scalar_one()

    pdf_bytes = render_document_pdf(doc, tenant)

    # HTTP headers must be Latin-1. Pro filename použij ASCII fallback +
    # filename* dle RFC 5987 (UTF-8) pro moderní browsery.
    import unicodedata
    from urllib.parse import quote
    ascii_title = (
        unicodedata.normalize("NFKD", doc.title)
        .encode("ascii", "ignore").decode("ascii")
    )
    ascii_safe = "".join(
        c if c.isalnum() or c in "-_ " else "_" for c in ascii_title
    ) or "document"
    utf8_quoted = quote(doc.title, safe="")

    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_safe}.pdf"; '
                f"filename*=UTF-8''{utf8_quoted}.pdf"
            ),
        },
    )
