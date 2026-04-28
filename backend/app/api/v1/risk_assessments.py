"""Risk Assessment endpointy.

CRUD pro hodnocení rizik dle ČSN ISO 45001 + opatření + audit revizí.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.risk_assessments import (
    RiskAssessmentCreateRequest,
    RiskAssessmentResponse,
    RiskAssessmentRevisionResponse,
    RiskAssessmentUpdateRequest,
    RiskMeasureCreateRequest,
    RiskMeasureResponse,
    RiskMeasureUpdateRequest,
)
from app.services.risk_assessments import (
    create_measure,
    create_risk_assessment,
    delete_measure,
    delete_risk_assessment,
    get_measure,
    get_measures,
    get_revisions,
    get_risk_assessment,
    get_risk_assessments,
    update_measure,
    update_risk_assessment,
)

router = APIRouter()


# ── List + Create ───────────────────────────────────────────────────────────


@router.get("/risk-assessments", response_model=list[RiskAssessmentResponse])
async def list_risk_assessments(
    scope_type: str | None = Query(None, pattern="^(workplace|position|plant|activity)$"),
    workplace_id: uuid.UUID | None = Query(None),
    job_position_id: uuid.UUID | None = Query(None),
    plant_id: uuid.UUID | None = Query(None),
    ra_status: str | None = Query(
        None,
        pattern="^(draft|open|in_progress|mitigated|accepted|archived)$",
    ),
    level: str | None = Query(None, pattern="^(low|medium|high|critical)$"),
    hazard_category: str | None = Query(None),
    current_user: User = Depends(require_role("ozo", "hr_manager", "lead_worker")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await get_risk_assessments(
        db, current_user.tenant_id,
        scope_type=scope_type,
        workplace_id=workplace_id,
        job_position_id=job_position_id,
        plant_id=plant_id,
        status=ra_status,
        level=level,
        hazard_category=hazard_category,
    )


@router.post(
    "/risk-assessments",
    response_model=RiskAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_risk_assessment_endpoint(
    data: RiskAssessmentCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        ra = await create_risk_assessment(
            db, data, current_user.tenant_id, current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e
    from app.services.risk_assessments import _enrich_assessment
    return await _enrich_assessment(db, ra)


# ── Detail / Update / Delete ────────────────────────────────────────────────


@router.get("/risk-assessments/{ra_id}", response_model=RiskAssessmentResponse)
async def get_risk_assessment_endpoint(
    ra_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "lead_worker")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    ra = await get_risk_assessment(db, ra_id, current_user.tenant_id)
    if ra is None:
        raise HTTPException(status_code=404, detail="Hodnocení rizika nenalezeno")
    from app.services.risk_assessments import _enrich_assessment
    return await _enrich_assessment(db, ra)


@router.patch("/risk-assessments/{ra_id}", response_model=RiskAssessmentResponse)
async def update_risk_assessment_endpoint(
    ra_id: uuid.UUID,
    data: RiskAssessmentUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    ra = await get_risk_assessment(db, ra_id, current_user.tenant_id)
    if ra is None:
        raise HTTPException(status_code=404, detail="Hodnocení rizika nenalezeno")
    try:
        updated = await update_risk_assessment(
            db, ra, data, revised_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e
    from app.services.risk_assessments import _enrich_assessment
    return await _enrich_assessment(db, updated)


@router.delete(
    "/risk-assessments/{ra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_risk_assessment(
    ra_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete — nastaví status='archived'."""
    ra = await get_risk_assessment(db, ra_id, current_user.tenant_id)
    if ra is None:
        raise HTTPException(status_code=404, detail="Hodnocení rizika nenalezeno")
    await delete_risk_assessment(db, ra)


# ── Measures ────────────────────────────────────────────────────────────────


@router.get(
    "/risk-assessments/{ra_id}/measures",
    response_model=list[RiskMeasureResponse],
)
async def list_measures(
    ra_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "lead_worker")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    ra = await get_risk_assessment(db, ra_id, current_user.tenant_id)
    if ra is None:
        raise HTTPException(status_code=404, detail="Hodnocení rizika nenalezeno")
    return await get_measures(db, ra_id, current_user.tenant_id)


@router.post(
    "/risk-assessments/{ra_id}/measures",
    response_model=RiskMeasureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_measure_endpoint(
    ra_id: uuid.UUID,
    data: RiskMeasureCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if data.risk_assessment_id != ra_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="risk_assessment_id v body se neshoduje s URL",
        )
    try:
        measure = await create_measure(
            db, data, current_user.tenant_id, current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e
    from app.services.risk_assessments import _enrich_measure
    return await _enrich_measure(db, measure)


@router.patch(
    "/risk-measures/{measure_id}",
    response_model=RiskMeasureResponse,
)
async def update_measure_endpoint(
    measure_id: uuid.UUID,
    data: RiskMeasureUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    measure = await get_measure(db, measure_id, current_user.tenant_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Opatření nenalezeno")
    updated = await update_measure(db, measure, data, user_id=current_user.id)
    from app.services.risk_assessments import _enrich_measure
    return await _enrich_measure(db, updated)


@router.delete(
    "/risk-measures/{measure_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_measure_endpoint(
    measure_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    measure = await get_measure(db, measure_id, current_user.tenant_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Opatření nenalezeno")
    await delete_measure(db, measure)


# ── Revisions (audit trail) ─────────────────────────────────────────────────


@router.get(
    "/risk-assessments/{ra_id}/revisions",
    response_model=list[RiskAssessmentRevisionResponse],
)
async def list_revisions(
    ra_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    ra = await get_risk_assessment(db, ra_id, current_user.tenant_id)
    if ra is None:
        raise HTTPException(status_code=404, detail="Hodnocení rizika nenalezeno")
    return await get_revisions(db, ra_id, current_user.tenant_id)
