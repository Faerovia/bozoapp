import uuid
from collections.abc import Awaitable, Callable

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1 import (
    accident_reports,
    admin,
    auth,
    dashboard,
    document_folders,
    documents,
    employees,
    global_trainings,
    health,
    invoices,
    invoices_admin,
    job_positions,
    medical_exams,
    onboarding,
    oopp,
    operating_logs,
    ozo_overview,
    periodic_checks,
    reminders_admin,
    revisions,
    risks,
    tenant,
    totp,
    training_pdf,
    training_signing,
    trainings,
    users,
    workplaces,
)
from app.core.audit import (
    RequestContext,
    clear_request_context,
    install_audit_listeners,
    set_request_context,
)
from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.observability import (
    configure_logging,
    new_request_id,
    set_request_id,
    set_sentry_context,
)
from app.core.rate_limit import limiter
from app.core.security import JWTError, decode_token
from app.core.storage import ensure_upload_dir_exists

settings = get_settings()

# Structured logging — JSON v produkci (strojově čitelné), pretty v dev/test.
configure_logging(json_output=settings.is_production)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        # send_default_pii: POZOR, nechávám False — máme zdravotní data,
        # nechceme je posílat do Sentry. Request ID + user_id/tenant_id si
        # do scope dáváme ručně v middlewaru (observability.set_sentry_context).
        send_default_pii=False,
    )

app = FastAPI(
    title="DigitalOZO API",
    version="0.1.0",
    # Disable docs in production
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

# ── Rate limiting (slowapi) ───────────────────────────────────────────────────
# Limiter je definován v app.core.rate_limit s Redis backend.
# state.limiter umožní použít @limiter.limit(...) dekorátor v routerech.
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Příliš mnoho pokusů. Zkus to za chvíli znovu."},
    )


# ── Audit log infrastructure ─────────────────────────────────────────────────
# install_audit_listeners() zavěsí SQLAlchemy before_flush listener, který
# při každém session.commit() zachytí INSERT/UPDATE/DELETE a zapíše do
# audit_log tabulky. Middleware níže do ContextVar napumpuje request-level
# metadata (IP, user_agent, user_id, tenant_id), aby měl listener co loggovat.
install_audit_listeners()

# Upload dir (PDF školení, loga firem) — vytvoří adresář pokud chybí.
ensure_upload_dir_exists()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Kombinovaný middleware: Request ID + audit context + Sentry scope.

    1. Request ID: reuse X-Request-ID pokud přišel od LB/proxy, jinak vygeneruj.
       Nastaví ContextVar (pro logger) a response header.
    2. Audit context: user_id, tenant_id, IP, user_agent z JWT. Jde do
       ContextVar pro SQLAlchemy before_flush listener.
    3. Sentry: set_user / set_tag pro current scope.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 1. Request ID
        rid = new_request_id(request.headers.get("x-request-id"))
        set_request_id(rid)

        # 2. Audit context (JWT best-effort)
        ctx = RequestContext(
            ip_address=self._client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        token = self._extract_token(request)
        if token:
            try:
                payload = decode_token(token)
                if payload.get("type") == "access":
                    ctx.user_id = uuid.UUID(payload["sub"])
                    ctx.tenant_id = uuid.UUID(payload["tenant_id"])
            except (JWTError, KeyError, ValueError):
                # Invalid/expired token — audit bez user info
                pass

        set_request_context(ctx)

        # 3. Sentry scope (no-op pokud Sentry není init)
        set_sentry_context(
            request_id=rid, user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        try:
            response = await call_next(request)
            response.headers["x-request-id"] = rid
            return response
        finally:
            clear_request_context()

    @staticmethod
    def _client_ip(request: Request) -> str | None:
        # X-Forwarded-For preferenčně (za reverse proxy), fallback na client.host
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            return auth.split(" ", 1)[1].strip()
        return request.cookies.get("access_token")


app.add_middleware(RequestContextMiddleware)

# CSRF middleware. POZOR: middlewares se spouští v opačném pořadí deklarace,
# tedy zde CSRF poběží PŘED AuditContextMiddleware (early rejection = neaudituj
# neplatné requesty). Pokud bys chtěl audit i failed CSRF pokusů, prohoď pořadí.
app.add_middleware(CSRFMiddleware)

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
app.include_router(totp.router, prefix="/api/v1", tags=["auth", "2fa"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
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
app.include_router(ozo_overview.router, prefix="/api/v1", tags=["ozo-overview"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(document_folders.router, prefix="/api/v1", tags=["document-folders"])
app.include_router(global_trainings.router, prefix="/api/v1", tags=["global-trainings"])
app.include_router(invoices_admin.router, prefix="/api/v1", tags=["invoices-admin"])
app.include_router(invoices.router, prefix="/api/v1", tags=["invoices"])
app.include_router(reminders_admin.router, prefix="/api/v1", tags=["reminders-admin"])
app.include_router(training_signing.router, prefix="/api/v1", tags=["training-signing"])
app.include_router(training_pdf.router, prefix="/api/v1", tags=["training-pdf"])
app.include_router(onboarding.router, prefix="/api/v1", tags=["onboarding"])
app.include_router(periodic_checks.router, prefix="/api/v1", tags=["periodic-checks"])
app.include_router(operating_logs.router, prefix="/api/v1", tags=["operating-logs"])
