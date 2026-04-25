"""
API pro adresářovou strukturu dokumentace (BOZP / PO).
"""

import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.document_folders import (
    DocumentFolderCreateRequest,
    DocumentFolderResponse,
    DocumentFolderUpdateRequest,
)
from app.schemas.documents import DocumentResponse
from app.services.document_folders import (
    create_folder,
    delete_folder,
    get_folder_by_id,
    has_children,
    list_folders,
    update_folder,
)
from app.services.document_text_extract import (
    ALLOWED_EXTENSIONS,
    MAX_IMPORT_BYTES,
    extract_text,
)
from app.services.documents import (
    create_imported_document,
)

router = APIRouter()


# ── Folder CRUD ─────────────────────────────────────────────────────────────


@router.get("/document-folders", response_model=list[DocumentFolderResponse])
async def list_folders_endpoint(
    domain: str | None = Query(None, pattern="^(bozp|po)$"),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Vrátí všechny složky daného tenantu, seřazené podle code."""
    return await list_folders(db, current_user.tenant_id, domain=domain)


@router.post(
    "/document-folders",
    response_model=DocumentFolderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_folder_endpoint(
    data: DocumentFolderCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        return await create_folder(
            db, current_user.tenant_id, current_user.id,
            name=data.name, domain=data.domain, parent_id=data.parent_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e


@router.patch(
    "/document-folders/{folder_id}",
    response_model=DocumentFolderResponse,
)
async def update_folder_endpoint(
    folder_id: uuid.UUID,
    data: DocumentFolderUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    folder = await get_folder_by_id(db, folder_id, current_user.tenant_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Složka nenalezena")
    return await update_folder(db, folder, name=data.name, sort_order=data.sort_order)


@router.delete(
    "/document-folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_folder_endpoint(
    folder_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    folder = await get_folder_by_id(db, folder_id, current_user.tenant_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Složka nenalezena")
    if await has_children(db, folder_id, current_user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Složka obsahuje podsložky — nejdřív je smažte / přesuňte.",
        )
    await delete_folder(db, folder)


# ── Import existujícího dokumentu ────────────────────────────────────────────


@router.post(
    "/document-folders/import",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_document_endpoint(
    file: UploadFile = File(...),
    title: str = Form(...),
    folder_id: uuid.UUID | None = Form(None),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Naimportuje existující textový dokument (PDF / DOCX / MD / TXT) jako
    GeneratedDocument typu 'imported'. Text se extrahuje (PDF/DOCX),
    u TXT/MD se uloží jak je.
    """
    if folder_id is not None:
        folder = await get_folder_by_id(db, folder_id, current_user.tenant_id)
        if folder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cílová složka nenalezena",
            )

    content = await file.read()
    try:
        text = extract_text(content, file.filename or "document.txt")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e

    return await create_imported_document(
        db, current_user.tenant_id, current_user.id,
        title=title, content_md=text, folder_id=folder_id,
        source_filename=file.filename or "document",
    )


# ── Konstanta pro frontend ────────────────────────────────────────────────────


@router.get("/document-folders/import/info")
async def import_info_endpoint(
    current_user: User = Depends(require_role("ozo", "hr_manager")),
) -> dict[str, Any]:
    """Limity a povolené formáty pro UI dialog."""
    _ = current_user
    return {
        "max_bytes":          MAX_IMPORT_BYTES,
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    }
