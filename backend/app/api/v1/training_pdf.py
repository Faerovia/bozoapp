"""
PDF endpointy:
- GET /trainings/{id}/attendance-list.pdf — prezenční listina (managers)
- GET /employees/{id}/trainings.pdf       — souhrn školení zaměstnance
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.employee import Employee
from app.models.tenant import Tenant
from app.models.training import Training, TrainingAssignment
from app.models.user import User
from app.services.employee_trainings_pdf import render_employee_trainings_pdf
from app.services.training_attendance_pdf import render_attendance_list_pdf

router = APIRouter()


@router.get(
    "/trainings/{training_id}/attendance-list.pdf",
    dependencies=[Depends(require_role("ozo", "hr_manager"))],
)
async def attendance_list_pdf(
    training_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    training = (await db.execute(
        select(Training).where(Training.id == training_id)
    )).scalar_one_or_none()
    if training is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )).scalar_one()

    # Trainer = autor šablony (Training.created_by)
    trainer = (await db.execute(
        select(User).where(User.id == training.created_by)
    )).scalar_one_or_none()

    # Načti podepsané assignmenty + zaměstnance
    rows = (await db.execute(
        select(TrainingAssignment, Employee)
        .join(Employee, TrainingAssignment.employee_id == Employee.id)
        .where(TrainingAssignment.training_id == training_id)
        .where(TrainingAssignment.signature_image.is_not(None))
        .where(TrainingAssignment.signed_at.is_not(None))
        .order_by(Employee.last_name, Employee.first_name)
    )).all()

    signed: list[tuple[TrainingAssignment, Employee]] = [
        (a, e) for a, e in rows
    ]

    pdf_bytes = render_attendance_list_pdf(
        training=training,
        tenant=tenant,
        trainer=trainer,
        signed_assignments=signed,
        issued_at=datetime.now(UTC),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="prezencni-listina-{training_id}.pdf"'
            ),
        },
    )


@router.get(
    "/employees/{employee_id}/trainings.pdf",
    dependencies=[Depends(require_role("ozo", "hr_manager"))],
)
async def employee_trainings_pdf(
    employee_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    employee = (await db.execute(
        select(Employee).where(Employee.id == employee_id)
    )).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Zaměstnanec nenalezen")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )).scalar_one()

    # Načti podepsané assignmenty + Training + trainer (User)
    rows_db = (await db.execute(
        select(TrainingAssignment, Training)
        .join(Training, TrainingAssignment.training_id == Training.id)
        .where(TrainingAssignment.employee_id == employee_id)
        .where(TrainingAssignment.signature_image.is_not(None))
        .where(TrainingAssignment.signed_at.is_not(None))
        .order_by(TrainingAssignment.signed_at.desc())
    )).all()

    rows: list[tuple[TrainingAssignment, Training, User | None]] = []
    trainer_cache: dict[uuid.UUID, User | None] = {}
    for assignment, training in rows_db:
        if training.created_by not in trainer_cache:
            trainer_cache[training.created_by] = (await db.execute(
                select(User).where(User.id == training.created_by)
            )).scalar_one_or_none()
        rows.append((assignment, training, trainer_cache[training.created_by]))

    pdf_bytes = render_employee_trainings_pdf(
        employee=employee,
        tenant=tenant,
        rows=rows,
        issued_by=user,
        issued_at=datetime.now(UTC),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="skoleni-{employee.last_name}-{employee_id}.pdf"'
            ),
        },
    )
