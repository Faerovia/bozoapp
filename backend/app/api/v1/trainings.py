"""
Trainings API — šablony + přiřazení + testy + certifikát.

Endpoint layout:

  /trainings                 GET/POST                   — šablony (OZO/HR)
  /trainings/test-template   GET                        — CSV vzor testu
  /trainings/assignments     POST                       — hromadné přiřazení
  /trainings/assignments/group POST                     — přiřazení podle filtru
  /trainings/assignments/{id} GET/DELETE                — detail / revoke
  /trainings/assignments/{id}/start POST                — spustit test
  /trainings/assignments/{id}/submit POST               — odeslat odpovědi
  /trainings/assignments/{id}/mark-read POST            — training bez testu
  /trainings/assignments/{id}/certificate.pdf GET       — certifikát
  /trainings/my              GET                        — pro employee

  /trainings/{id}            GET/PATCH/DELETE           — detail šablony
  /trainings/{id}/content    POST (PDF)/GET             — upload/download PDF
  /trainings/{id}/test       POST (CSV+%)/DELETE        — test nahrát/smazat
  /trainings/{id}/assignments GET                       — seznam přiřazení
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.core.storage import read_file
from app.models.employee import Employee
from app.models.tenant import Tenant
from app.models.training import TrainingAssignment
from app.models.user import User
from app.schemas.trainings import (
    AssignmentCreateRequest,
    AssignmentCreateResponse,
    AssignmentResponse,
    ContentUploadResponse,
    GroupAssignRequest,
    StartTestResponse,
    SubmitTestRequest,
    SubmitTestResponse,
    TestUploadResponse,
    TrainingCreateRequest,
    TrainingResponse,
    TrainingUpdateRequest,
)
from app.services import trainings as svc
from app.services.employees import get_employee_by_user_id
from app.services.training_certificate import generate_certificate_pdf

router = APIRouter()


def _training_to_response(t: Any) -> TrainingResponse:
    resp = TrainingResponse.model_validate(t)
    resp.has_test = t.has_test
    resp.question_count = t.question_count
    return resp


async def _load_assignment_for_employee(
    db: AsyncSession, assignment_id: uuid.UUID, current_user: User
) -> tuple[TrainingAssignment, Any, Employee]:
    """
    Načte (assignment, training, employee). Ověří přístup:
    - employee / equipment_responsible: jen vlastní
    - OZO / HR / admin: libovolný v rámci tenantu
    """
    a = await svc.get_assignment(db, assignment_id, current_user.tenant_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Přiřazení nenalezeno")

    if current_user.role in ("employee", "equipment_responsible"):
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None or emp.id != a.employee_id:
            raise HTTPException(status_code=403, detail="Přístup odepřen")
        employee = emp
    else:
        employee_row = (await db.execute(
            select(Employee).where(Employee.id == a.employee_id)
        )).scalar_one_or_none()
        if employee_row is None:
            raise HTTPException(status_code=500, detail="Zaměstnanec nenalezen")
        employee = employee_row

    training = await svc.get_training(db, a.training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=500, detail="Šablona nenalezena")

    return a, training, employee


# ── Training templates ───────────────────────────────────────────────────────

@router.get("/trainings", response_model=list[TrainingResponse])
async def list_trainings_endpoint(
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    result = await svc.list_trainings(db, current_user.tenant_id)
    return [_training_to_response(t) for t in result]


@router.post(
    "/trainings",
    response_model=TrainingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_endpoint(
    data: TrainingCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> TrainingResponse:
    training = await svc.create_training(db, data, current_user.tenant_id, current_user.id)
    return _training_to_response(training)


# ── Test CSV template (static route před {training_id}) ──────────────────────

@router.get("/trainings/test-template")
async def download_test_csv_template(
    current_user: User = Depends(require_role("ozo", "hr_manager")),  # noqa: ARG001
) -> Response:
    """Vzorový CSV pro test: hlavička + 5 příkladových otázek."""
    content = svc.generate_test_csv_template()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="test_vzor.csv"',
        },
    )


# ── Assignment flat routes (PŘED /trainings/{id}/*) ──────────────────────────

@router.post(
    "/trainings/assignments",
    response_model=AssignmentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignments_endpoint(
    data: AssignmentCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> AssignmentCreateResponse:
    training = await svc.get_training(db, data.training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")

    created, skipped, errors = await svc.create_assignments(
        db,
        training=training,
        employee_ids=data.employee_ids,
        tenant_id=current_user.tenant_id,
        assigned_by=current_user.id,
    )
    return AssignmentCreateResponse(
        created_count=created, skipped_existing_count=skipped, errors=errors
    )


@router.post(
    "/trainings/assignments/group",
    response_model=AssignmentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def group_assign_endpoint(
    data: GroupAssignRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> AssignmentCreateResponse:
    """Přiřadit školení všem zaměstnancům podle filtru."""
    training = await svc.get_training(db, data.training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")

    query = select(Employee).where(Employee.tenant_id == current_user.tenant_id)
    if data.only_active:
        query = query.where(Employee.status == "active")
    if data.plant_id is not None:
        query = query.where(Employee.plant_id == data.plant_id)
    if data.workplace_id is not None:
        query = query.where(Employee.workplace_id == data.workplace_id)
    if data.job_position_id is not None:
        query = query.where(Employee.job_position_id == data.job_position_id)

    employees = (await db.execute(query)).scalars().all()
    emp_ids = [e.id for e in employees]

    created, skipped, errors = await svc.create_assignments(
        db,
        training=training,
        employee_ids=emp_ids,
        tenant_id=current_user.tenant_id,
        assigned_by=current_user.id,
    )
    return AssignmentCreateResponse(
        created_count=created, skipped_existing_count=skipped, errors=errors
    )


@router.get("/trainings/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment_endpoint(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    a = await svc.get_assignment(db, assignment_id, current_user.tenant_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Přiřazení nenalezeno")
    if current_user.role in ("employee", "equipment_responsible"):
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None or emp.id != a.employee_id:
            raise HTTPException(status_code=403, detail="Přístup odepřen")
    return await svc.enrich_assignment(db, a)


@router.delete(
    "/trainings/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_assignment_endpoint(
    assignment_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    a = await svc.get_assignment(db, assignment_id, current_user.tenant_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Přiřazení nenalezeno")
    await svc.revoke_assignment(db, a)


@router.post(
    "/trainings/assignments/{assignment_id}/start",
    response_model=StartTestResponse,
)
async def start_test_endpoint(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartTestResponse:
    a, training, _emp = await _load_assignment_for_employee(db, assignment_id, current_user)
    if not training.has_test:
        raise HTTPException(
            status_code=422,
            detail="K tomuto školení není přiložen test; použijte mark-read",
        )
    questions = svc.prepare_test_for_attempt(training.test_questions or [])
    return StartTestResponse(
        assignment_id=a.id,
        training_title=training.title,
        pass_percentage=training.pass_percentage or 0,
        questions=questions,
    )


@router.post(
    "/trainings/assignments/{assignment_id}/submit",
    response_model=SubmitTestResponse,
)
async def submit_test_endpoint(
    assignment_id: uuid.UUID,
    data: SubmitTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitTestResponse:
    a, training, _emp = await _load_assignment_for_employee(db, assignment_id, current_user)
    attempt = await svc.submit_attempt(
        db,
        assignment=a,
        training=training,
        answers=[x.model_dump() for x in data.answers],
    )
    return SubmitTestResponse(
        attempt_id=attempt.id,
        score_percentage=attempt.score_percentage,
        passed=attempt.passed,
        pass_percentage=training.pass_percentage or 0,
        assignment=await svc.enrich_assignment(db, a),
    )


@router.post(
    "/trainings/assignments/{assignment_id}/mark-read",
    response_model=AssignmentResponse,
)
async def mark_read_endpoint(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    a, training, _emp = await _load_assignment_for_employee(db, assignment_id, current_user)
    await svc.mark_assignment_read(db, assignment=a, training=training)
    return await svc.enrich_assignment(db, a)


@router.get("/trainings/assignments/{assignment_id}/certificate.pdf")
async def download_certificate(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    a, training, emp = await _load_assignment_for_employee(db, assignment_id, current_user)
    if a.last_completed_at is None:
        raise HTTPException(status_code=422, detail="Školení dosud nebylo splněno")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=500, detail="Tenant nenalezen")

    issuer = (await db.execute(
        select(User).where(User.id == a.assigned_by)
    )).scalar_one_or_none()

    pdf_bytes = generate_certificate_pdf(
        tenant=tenant,
        training=training,
        assignment=a,
        employee=emp,
        issuer_name=issuer.full_name if issuer else None,
    )
    safe_title = training.title[:40].replace(" ", "_")
    filename = f"certifikat_{safe_title}_{emp.last_name}_{a.last_completed_at.date()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── My assignments (employee "Školící centrum") ──────────────────────────────

@router.get("/trainings/my", response_model=list[AssignmentResponse])
async def my_assignments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssignmentResponse]:
    emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
    if emp is None:
        return []
    assignments = await svc.list_assignments_for_employee(
        db, emp.id, current_user.tenant_id
    )
    return [await svc.enrich_assignment(db, a) for a in assignments]


# ── Training specific routes (s {training_id}) — MUSÍ být na konci ───────────

@router.get("/trainings/{training_id}", response_model=TrainingResponse)
async def get_training_endpoint(
    training_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> TrainingResponse:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")
    return _training_to_response(t)


@router.patch("/trainings/{training_id}", response_model=TrainingResponse)
async def update_training_endpoint(
    training_id: uuid.UUID,
    data: TrainingUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> TrainingResponse:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")
    t = await svc.update_training(db, t, data)
    return _training_to_response(t)


@router.delete("/trainings/{training_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_training_endpoint(
    training_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")
    await svc.delete_training(db, t)


@router.post(
    "/trainings/{training_id}/content",
    response_model=ContentUploadResponse,
)
async def upload_pdf_content(
    training_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> ContentUploadResponse:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")

    content = await file.read()
    try:
        rel_path = await svc.attach_pdf_content(db, t, content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return ContentUploadResponse(content_pdf_path=rel_path, size_bytes=len(content))


@router.get("/trainings/{training_id}/content")
async def download_pdf_content(
    training_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None or not t.content_pdf_path:
        raise HTTPException(status_code=404, detail="PDF obsah není k dispozici")

    # Employee-side access check
    if current_user.role in ("employee", "equipment_responsible"):
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None:
            raise HTTPException(status_code=403, detail="Přístup odepřen")
        has_assignment = (await db.execute(
            select(TrainingAssignment.id).where(
                TrainingAssignment.training_id == training_id,
                TrainingAssignment.employee_id == emp.id,
            )
        )).scalar_one_or_none()
        if has_assignment is None:
            raise HTTPException(status_code=403, detail="Školení vám nebylo přiřazeno")

    try:
        content = read_file(t.content_pdf_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="PDF soubor nenalezen") from None

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="skoleni.pdf"'},
    )


@router.post("/trainings/{training_id}/test", response_model=TestUploadResponse)
async def upload_test_csv(
    training_id: uuid.UUID,
    pass_percentage: int = Form(..., ge=0, le=100),
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> TestUploadResponse:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")

    content = await file.read()
    try:
        questions = svc.parse_test_csv(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    await svc.set_test(db, t, questions, pass_percentage)
    return TestUploadResponse(
        question_count=len(questions),
        pass_percentage=pass_percentage,
    )


@router.delete("/trainings/{training_id}/test", status_code=status.HTTP_204_NO_CONTENT)
async def remove_test_endpoint(
    training_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")
    await svc.remove_test(db, t)


@router.get(
    "/trainings/{training_id}/assignments",
    response_model=list[AssignmentResponse],
)
async def list_training_assignments_endpoint(
    training_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[AssignmentResponse]:
    t = await svc.get_training(db, training_id, current_user.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Školení nenalezeno")
    assignments = await svc.list_assignments_for_training(
        db, training_id, current_user.tenant_id
    )
    return [await svc.enrich_assignment(db, a) for a in assignments]
