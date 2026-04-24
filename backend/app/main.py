import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    accident_reports,
    auth,
    dashboard,
    employees,
    health,
    job_positions,
    medical_exams,
    oopp,
    revisions,
    risks,
    tenant,
    trainings,
    users,
    workplaces,
)
from app.core.config import get_settings

settings = get_settings()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )

app = FastAPI(
    title="BOZOapp API",
    version="0.1.0",
    # Disable docs in production
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

_dev_origins = ["http://localhost:3000", "http://localhost:3001"]
_cors_origins = (
    settings.cors_origins_list if settings.is_production else _dev_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(tenant.router, prefix="/api/v1", tags=["tenant"])
app.include_router(employees.router, prefix="/api/v1", tags=["employees"])
app.include_router(risks.router, prefix="/api/v1", tags=["risks"])
app.include_router(trainings.router, prefix="/api/v1", tags=["trainings"])
app.include_router(revisions.router, prefix="/api/v1", tags=["revisions", "calendar"])
app.include_router(accident_reports.router, prefix="/api/v1", tags=["accident-reports"])
app.include_router(dashboard.router, prefix="/api/v1", tags=["dashboard"])
app.include_router(oopp.router, prefix="/api/v1", tags=["oopp"])
app.include_router(workplaces.router, prefix="/api/v1", tags=["workplaces"])
app.include_router(job_positions.router, prefix="/api/v1", tags=["job-positions"])
app.include_router(medical_exams.router, prefix="/api/v1", tags=["medical-exams"])
