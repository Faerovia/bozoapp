"""
Observability foundation.

- **Request ID**: Každý request dostane UUID. Propaguje se do X-Request-ID
  response hlavičky, do logu a do Sentry scope.
- **Structured logging**: structlog se standardním JSON renderingem v prod,
  pretty console v dev. Každý log entry má request_id + user_id + tenant_id
  pokud jsou k dispozici (ContextVar z audit middlewaru).
- **Sentry context**: při kažém requestu nastavíme `sentry_sdk.set_user`
  a `set_tag("tenant_id", ...)` aby errory měly plný kontext.

Middleware je v app.main.RequestContextMiddleware; tenhle modul jen poskytuje
build-blocks.
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import sentry_sdk
import structlog

# Request ID pro current request — samostatný ContextVar, protože nechceme
# míchat s audit RequestContext (request ID je čistě observability, audit je
# bezpečnostní model).
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str | None:
    return _request_id.get()


def new_request_id(header_value: str | None = None) -> str:
    """Reuse hlavičku pokud už request ID má (za LB/proxy), jinak generuj."""
    if header_value and 8 <= len(header_value) <= 128:
        return header_value
    return str(uuid.uuid4())


def _inject_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor — přidá request_id + audit context do každého logu."""
    from app.core.audit import get_request_context  # lazy import, avoid cycles

    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid

    ctx = get_request_context()
    if ctx:
        if ctx.user_id:
            event_dict["user_id"] = str(ctx.user_id)
        if ctx.tenant_id:
            event_dict["tenant_id"] = str(ctx.tenant_id)

    return event_dict


def configure_logging(*, json_output: bool) -> None:
    """
    Nastaví structlog + standard Python logging tak, aby:
    - Stdlib `logging.getLogger(...)` logy procházely přes structlog processors
    - V produkci jsou JSON řádky (strojově čitelné)
    - V dev je pretty console s barvami

    Volat jednou v main.py při startupu.
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_context,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Minimální stdlib logging (hlavně SQLAlchemy, uvicorn) — směrovat přes structlog
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Odstraň default handlery aby nelogovaly zvlášť
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
            ],
            processor=(
                structlog.processors.JSONRenderer() if json_output
                else structlog.dev.ConsoleRenderer(colors=False)
            ),
        )
    )
    root.addHandler(handler)


def set_sentry_context(
    *,
    request_id: str | None,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID | None,
) -> None:
    """Připne user/tenant na Sentry scope pro aktuální request."""
    scope = sentry_sdk.Scope.get_current_scope()
    if user_id:
        scope.set_user({"id": str(user_id)})
    if tenant_id:
        scope.set_tag("tenant_id", str(tenant_id))
    if request_id:
        scope.set_tag("request_id", request_id)
