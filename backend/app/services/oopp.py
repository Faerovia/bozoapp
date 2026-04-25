"""
Služby OOPP modulu (NV 390/2021 Sb.).
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.oopp import (
    EmployeeOoppIssue,
    PositionOoppItem,
    PositionRiskGrid,
    VALID_BODY_PARTS,
    VALID_RISK_COLS,
)
from app.schemas.oopp import (
    _add_months,
    IssueCreateRequest,
    IssueUpdateRequest,
    OoppItemCreateRequest,
    OoppItemUpdateRequest,
    RiskGridUpdateRequest,
)


# ── Risk grid ────────────────────────────────────────────────────────────────


async def get_risk_grid(
    db: AsyncSession, position_id: uuid.UUID, tenant_id: uuid.UUID
) -> PositionRiskGrid | None:
    res = await db.execute(
        select(PositionRiskGrid).where(
            PositionRiskGrid.tenant_id == tenant_id,
            PositionRiskGrid.job_position_id == position_id,
        )
    )
    return res.scalar_one_or_none()


def _validate_grid(grid: dict[str, list[int]]) -> None:
    """Validuje, že klíče jsou validní body parts a hodnoty validní risk cols."""
    for body_part, cols in grid.items():
        if body_part not in VALID_BODY_PARTS:
            raise ValueError(f"Neplatná část těla: {body_part}")
        if not isinstance(cols, list):
            raise ValueError(f"Hodnota pro {body_part} musí být seznam")
        for c in cols:
            if c not in VALID_RISK_COLS:
                raise ValueError(f"Neplatný sloupec rizik: {c}")


async def upsert_risk_grid(
    db: AsyncSession,
    position_id: uuid.UUID,
    data: RiskGridUpdateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> PositionRiskGrid:
    """Replace strategie: nahradí celou matrix."""
    await assert_in_tenant(
        db, JobPosition, position_id, tenant_id, field_name="job_position_id"
    )
    _validate_grid(data.grid)

    cleaned = {bp: cols for bp, cols in data.grid.items() if cols}

    grid = await get_risk_grid(db, position_id, tenant_id)
    if grid is None:
        grid = PositionRiskGrid(
            tenant_id=tenant_id,
            job_position_id=position_id,
            grid=cleaned,
            created_by=created_by,
        )
        db.add(grid)
    else:
        grid.grid = cleaned
    await db.flush()
    return grid


# ── Position OOPP items ──────────────────────────────────────────────────────


async def get_oopp_items(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    job_position_id: uuid.UUID | None = None,
    body_part: str | None = None,
    status: str | None = None,
) -> list[PositionOoppItem]:
    query = (
        select(PositionOoppItem)
        .where(PositionOoppItem.tenant_id == tenant_id)
        .order_by(PositionOoppItem.body_part, PositionOoppItem.name)
    )
    if job_position_id is not None:
        query = query.where(PositionOoppItem.job_position_id == job_position_id)
    if body_part is not None:
        query = query.where(PositionOoppItem.body_part == body_part)
    if status is not None:
        query = query.where(PositionOoppItem.status == status)
    res = await db.execute(query)
    return list(res.scalars().all())


async def get_oopp_item_by_id(
    db: AsyncSession, item_id: uuid.UUID, tenant_id: uuid.UUID
) -> PositionOoppItem | None:
    res = await db.execute(
        select(PositionOoppItem).where(
            PositionOoppItem.id == item_id,
            PositionOoppItem.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_oopp_item(
    db: AsyncSession,
    data: OoppItemCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> PositionOoppItem:
    await assert_in_tenant(
        db, JobPosition, data.job_position_id, tenant_id,
        field_name="job_position_id",
    )
    item = PositionOoppItem(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(item)
    await db.flush()
    return item


async def update_oopp_item(
    db: AsyncSession, item: PositionOoppItem, data: OoppItemUpdateRequest
) -> PositionOoppItem:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.flush()
    return item


# ── Employee OOPP issues ─────────────────────────────────────────────────────


async def get_issues(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    employee_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[EmployeeOoppIssue]:
    query = (
        select(EmployeeOoppIssue)
        .where(EmployeeOoppIssue.tenant_id == tenant_id)
        .order_by(EmployeeOoppIssue.issued_at.desc())
    )
    if employee_id is not None:
        query = query.where(EmployeeOoppIssue.employee_id == employee_id)
    if item_id is not None:
        query = query.where(EmployeeOoppIssue.position_oopp_item_id == item_id)
    if status is not None:
        query = query.where(EmployeeOoppIssue.status == status)
    res = await db.execute(query)
    return list(res.scalars().all())


async def get_issue_by_id(
    db: AsyncSession, issue_id: uuid.UUID, tenant_id: uuid.UUID
) -> EmployeeOoppIssue | None:
    res = await db.execute(
        select(EmployeeOoppIssue).where(
            EmployeeOoppIssue.id == issue_id,
            EmployeeOoppIssue.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_issue(
    db: AsyncSession,
    data: IssueCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> EmployeeOoppIssue:
    await assert_in_tenant(
        db, Employee, data.employee_id, tenant_id, field_name="employee_id"
    )
    item = await get_oopp_item_by_id(db, data.position_oopp_item_id, tenant_id)
    if item is None:
        raise ValueError(
            f"OOPP položka {data.position_oopp_item_id} nenalezena"
        )

    valid_until: date | None = data.valid_until
    if valid_until is None and item.valid_months is not None:
        valid_until = _add_months(data.issued_at, item.valid_months)

    payload = data.model_dump(exclude={"valid_until"})
    issue = EmployeeOoppIssue(
        tenant_id=tenant_id,
        created_by=created_by,
        valid_until=valid_until,
        **payload,
    )
    db.add(issue)
    await db.flush()
    return issue


async def update_issue(
    db: AsyncSession, issue: EmployeeOoppIssue, data: IssueUpdateRequest
) -> EmployeeOoppIssue:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(issue, field, value)
    await db.flush()
    return issue


# ── Response enrichment ──────────────────────────────────────────────────────


async def issue_to_response_dict(
    db: AsyncSession, issue: EmployeeOoppIssue
) -> dict[str, Any]:
    """Připojí employee_name + item_name + body_part pro UI."""
    emp_res = await db.execute(
        select(Employee).where(Employee.id == issue.employee_id)
    )
    emp = emp_res.scalar_one_or_none()
    employee_name = (
        f"{emp.first_name} {emp.last_name}".strip() if emp is not None else None
    )

    item_res = await db.execute(
        select(PositionOoppItem).where(
            PositionOoppItem.id == issue.position_oopp_item_id
        )
    )
    item = item_res.scalar_one_or_none()

    return {
        "id": issue.id,
        "tenant_id": issue.tenant_id,
        "employee_id": issue.employee_id,
        "employee_name": employee_name,
        "position_oopp_item_id": issue.position_oopp_item_id,
        "item_name": item.name if item else None,
        "body_part": item.body_part if item else None,
        "issued_at": issue.issued_at,
        "valid_until": issue.valid_until,
        "validity_status": issue.validity_status,
        "quantity": issue.quantity,
        "size_spec": issue.size_spec,
        "serial_number": issue.serial_number,
        "notes": issue.notes,
        "status": issue.status,
        "created_by": issue.created_by,
    }


# ── Pozice s vyhodnoceným gridem (pro UI list "OOPP per pozice") ────────────


async def get_positions_with_grid(
    db: AsyncSession, tenant_id: uuid.UUID
) -> list[JobPosition]:
    """Vrátí pozice, kde existuje neprázdný PositionRiskGrid."""
    res = await db.execute(
        select(JobPosition)
        .join(PositionRiskGrid, PositionRiskGrid.job_position_id == JobPosition.id)
        .where(
            JobPosition.tenant_id == tenant_id,
            JobPosition.status == "active",
        )
        .order_by(JobPosition.name)
    )
    positions = list(res.scalars().all())
    out: list[JobPosition] = []
    for jp in positions:
        grid = await get_risk_grid(db, jp.id, tenant_id)
        if grid is not None and grid.has_any_risk:
            out.append(jp)
    return out
