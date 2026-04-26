"""
OOPP modul (NV 390/2021 Sb. Příloha č. 2).

Endpoint mapa:
  Catalog (statický popis tabulky NV 390/2021):
    GET /oopp/catalog
  Risk grid per pozice:
    GET /job-positions/{id}/oopp-grid
    PUT /job-positions/{id}/oopp-grid
  Pozice s vyplněným gridem (UI list):
    GET /oopp/positions
  OOPP items (co pozice musí dostat):
    GET    /oopp/items?job_position_id=...
    POST   /oopp/items
    PATCH  /oopp/items/{id}
    DELETE /oopp/items/{id}  (archivuje)
  Issues (záznam výdeje):
    GET    /oopp/issues?employee_id=...
    POST   /oopp/issues
    PATCH  /oopp/issues/{id}
    DELETE /oopp/issues/{id}  (archivuje)
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.oopp import BODY_PARTS, RISK_COLUMNS
from app.models.user import User
from app.schemas.oopp import (
    BodyPartInfo,
    IssueCreateRequest,
    IssueResponse,
    IssueUpdateRequest,
    OoppCatalogResponse,
    OoppItemCreateRequest,
    OoppItemResponse,
    OoppItemUpdateRequest,
    RiskColumnInfo,
    RiskGridResponse,
    RiskGridUpdateRequest,
)
from app.services.employees import get_employee_by_user_id
from app.services.oopp import (
    create_issue,
    create_oopp_item,
    get_issue_by_id,
    get_issues,
    get_oopp_item_by_id,
    get_oopp_items,
    get_positions_with_grid,
    get_risk_grid,
    issue_to_response_dict,
    update_issue,
    update_oopp_item,
    upsert_risk_grid,
)

router = APIRouter()


# ── Catalog (statický popis tabulky NV 390/2021) ────────────────────────────


@router.get("/oopp/catalog", response_model=OoppCatalogResponse)
async def get_oopp_catalog(
    _current_user: User = Depends(get_current_user),
) -> OoppCatalogResponse:
    """Vrátí seznam body parts (řádky) a risk columns (sloupce) tabulky."""
    return OoppCatalogResponse(
        body_parts=[
            BodyPartInfo(key=k, label=lbl, group=grp)
            for (k, lbl, grp) in BODY_PARTS
        ],
        risk_columns=[
            RiskColumnInfo(col=c, label=lbl, subgroup=sub, group=grp)
            for (c, lbl, sub, grp) in RISK_COLUMNS
        ],
    )


# ── Risk grid per pozice ────────────────────────────────────────────────────


@router.get(
    "/job-positions/{position_id}/oopp-grid",
    response_model=RiskGridResponse,
)
async def get_grid_endpoint(
    position_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    grid = await get_risk_grid(db, position_id, current_user.tenant_id)
    if grid is None:
        # Vrátíme prázdný grid jako "ještě nezahájeno" — UI to vykreslí jako pristnou matrix.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grid není nastaven"
        )
    return grid


@router.put(
    "/job-positions/{position_id}/oopp-grid",
    response_model=RiskGridResponse,
)
async def set_grid_endpoint(
    position_id: uuid.UUID,
    data: RiskGridUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        return await upsert_risk_grid(
            db, position_id, data, current_user.tenant_id, current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        ) from e


# ── Pozice s vyplněným gridem ────────────────────────────────────────────────


@router.get("/oopp/positions")
async def list_positions_with_grid(
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Pozice, kde je v gridu zaškrtnuto alespoň jedno riziko."""
    positions = await get_positions_with_grid(db, current_user.tenant_id)
    return [
        {
            "id": jp.id,
            "name": jp.name,
            "workplace_id": jp.workplace_id,
        }
        for jp in positions
    ]


# ── OOPP items per pozice ────────────────────────────────────────────────────


@router.get("/oopp/items", response_model=list[OoppItemResponse])
async def list_oopp_items(
    job_position_id: uuid.UUID | None = Query(None),
    body_part: str | None = Query(None, max_length=2),
    item_status: str | None = Query(None, pattern="^(active|archived)$"),
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await get_oopp_items(
        db, current_user.tenant_id,
        job_position_id=job_position_id,
        body_part=body_part,
        status=item_status,
    )


@router.post(
    "/oopp/items",
    response_model=OoppItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_oopp_item_endpoint(
    data: OoppItemCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await create_oopp_item(db, data, current_user.tenant_id, current_user.id)


@router.patch("/oopp/items/{item_id}", response_model=OoppItemResponse)
async def update_oopp_item_endpoint(
    item_id: uuid.UUID,
    data: OoppItemUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    item = await get_oopp_item_by_id(db, item_id, current_user.tenant_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Položka nenalezena")
    return await update_oopp_item(db, item, data)


@router.delete("/oopp/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_oopp_item(
    item_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    item = await get_oopp_item_by_id(db, item_id, current_user.tenant_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Položka nenalezena")
    item.status = "archived"
    await db.flush()


# ── Issues (záznam výdeje OOPP zaměstnanci) ─────────────────────────────────


@router.get("/oopp/issues.pdf")
async def export_issues_pdf(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """PDF přehled vydaných OOPP zaměstnancům s osobním číslem."""
    from fastapi.responses import Response

    from app.models.tenant import Tenant
    from app.services.export_pdf import generate_oopp_issues_pdf

    issues = await get_issues(
        db, current_user.tenant_id, status="active",
    )
    issue_dicts = [await issue_to_response_dict(db, i) for i in issues]

    # Doplň personal_number per employee
    from sqlalchemy import select

    from app.models.employee import Employee
    emp_ids = {iss.get("employee_id") for iss in issue_dicts if iss.get("employee_id")}
    if emp_ids:
        rows = (await db.execute(
            select(Employee).where(Employee.id.in_(emp_ids))
        )).scalars().all()
        emp_map = {str(e.id): e for e in rows}
        for iss in issue_dicts:
            emp = emp_map.get(str(iss.get("employee_id")))
            if emp is not None:
                iss["personal_number"] = emp.personal_number

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )).scalar_one()
    pdf_bytes = generate_oopp_issues_pdf(issue_dicts, tenant.name)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="oopp-vydeje.pdf"',
        },
    )


@router.get("/oopp/issues", response_model=list[IssueResponse])
async def list_issues(
    employee_id: uuid.UUID | None = Query(None),
    item_id: uuid.UUID | None = Query(None),
    issue_status: str | None = Query(None, pattern="^(active|returned|discarded)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Výdejní záznamy. Zaměstnanec vidí pouze vlastní (filtr aplikujeme automaticky).
    """
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None:
            return []
        employee_id = emp.id

    issues = await get_issues(
        db, current_user.tenant_id,
        employee_id=employee_id,
        item_id=item_id,
        status=issue_status,
    )
    return [await issue_to_response_dict(db, i) for i in issues]


@router.post(
    "/oopp/issues",
    response_model=IssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_issue_endpoint(
    data: IssueCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        issue = await create_issue(db, data, current_user.tenant_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        ) from e
    return await issue_to_response_dict(db, issue)


@router.post(
    "/oopp/issues/bulk",
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_issues_endpoint(
    data: dict[str, Any],
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Hromadný výdej OOPP — pro každého employee_id zkopíruje stejný
    výdej (item_id, issued_at, valid_until, size, serial_number, notes).

    Request: {
        "employee_ids": ["...", "..."],
        "item_id": "...",
        "issued_at": "2026-04-15",
        "valid_until": null,
        "size": null,
        "notes": null
    }
    Response: {created_count, errors}
    """
    employee_ids = data.get("employee_ids") or []
    if not isinstance(employee_ids, list) or not employee_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="employee_ids je povinný neprázdný seznam",
        )

    created = 0
    errors: list[dict[str, Any]] = []
    for emp_id in employee_ids:
        try:
            payload = {
                **{k: v for k, v in data.items() if k != "employee_ids"},
                "employee_id": emp_id,
            }
            issue_req = IssueCreateRequest(**payload)
            await create_issue(db, issue_req, current_user.tenant_id, current_user.id)
            created += 1
        except (ValueError, Exception) as e:  # noqa: BLE001
            errors.append({"employee_id": str(emp_id), "error": str(e)})

    return {"created_count": created, "errors": errors}


@router.patch("/oopp/issues/{issue_id}", response_model=IssueResponse)
async def update_issue_endpoint(
    issue_id: uuid.UUID,
    data: IssueUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    issue = await get_issue_by_id(db, issue_id, current_user.tenant_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Výdej nenalezen")
    updated = await update_issue(db, issue, data)
    return await issue_to_response_dict(db, updated)


@router.delete("/oopp/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_issue(
    issue_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    issue = await get_issue_by_id(db, issue_id, current_user.tenant_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Výdej nenalezen")
    issue.status = "discarded"
    await db.flush()
