"""
Audit log — automatický zápis všech CREATE/UPDATE/DELETE do tabulky audit_log.

Architektura:

1. **Request context** se nastaví middlewarem při příchodu requestu (IP,
   user_agent, user_id, tenant_id) do `ContextVar`. To umožňuje SQLAlchemy
   event listeneru si ho přečíst aniž by do něj kdokoli explicitně sypal
   request objekt.

2. **SQLAlchemy `before_flush` listener** se spouští před commit/flush
   session. Projde pending inserts/updates/deletes, zachytí diff
   (old_values / new_values) a vytvoří řádek v `audit_log`.

3. **Auditovatelné modely** se řídí přes mixin `Auditable` — model který
   má `__audit__ = True` (nebo dědí `Auditable`) se loguje. Tenant, User
   tabulka je explicitně zahrnuta. Audit_log sama sebe NEloguje (nekonečná
   rekurze).

Co se do audit_log NENEZAPISUJE:
- Čistě read queries (SELECT). V BOZP by to dávalo smysl pro zdravotní
  data, ale zahltilo by tabulku → řešit později přes samostatný
  "sensitive access" log.
- Columns jako `updated_at`, `created_at` (bez byznys významu).
- Columns v `AUDIT_SKIP_COLUMNS` (hashed_password atd.).

GDPR: audit_log obsahuje old_values/new_values jako JSONB. Zvláštní
kategorie dat (personal_id) se nikdy neukládají v cleartextu — hash/mask
se řeší v modelu.
"""
from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# ── Request context ──────────────────────────────────────────────────────────

@dataclass
class RequestContext:
    """Minimální metadata aktuálního requestu — nastavuje middleware."""
    user_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    ip_address: str | None = None
    user_agent: str | None = None


_request_ctx: ContextVar[RequestContext | None] = ContextVar(
    "audit_request_ctx", default=None
)


def set_request_context(ctx: RequestContext) -> None:
    _request_ctx.set(ctx)


def get_request_context() -> RequestContext | None:
    return _request_ctx.get()


def clear_request_context() -> None:
    _request_ctx.set(None)


# ── Co auditovat ─────────────────────────────────────────────────────────────

# Modely, které NIKDY neauditujeme — sama audit tabulka + čisté čtecí entity.
AUDIT_EXCLUDED_TABLES = frozenset({
    "audit_log",
    "alembic_version",
})

# Názvy sloupců, které se do diffu nepřenášejí — buď irelevantní pro audit,
# nebo obsahují tajnosti (heslo).
AUDIT_SKIP_COLUMNS = frozenset({
    "hashed_password",
    "updated_at",
    "created_at",
})


def _serialize_value(value: Any) -> Any:
    """Převede SQLAlchemy hodnotu na JSON-friendly typ."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    # Bytes, custom types etc. — serialize as repr fallback
    return str(value)


def _collect_values(instance: Any, *, old: bool = False) -> dict[str, Any]:
    """Vrátí dict {column_name: serialized_value} nebo původních hodnot (old=True)."""
    state = inspect(instance)
    out: dict[str, Any] = {}
    for attr in state.attrs:
        if attr.key in AUDIT_SKIP_COLUMNS:
            continue
        if old:
            history = attr.history
            if history.has_changes() and history.deleted:
                out[attr.key] = _serialize_value(history.deleted[0])
        else:
            out[attr.key] = _serialize_value(attr.value)
    return out


def _diff_updated(instance: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pro update: (old_values, new_values) jen sloupce, které se změnily."""
    state = inspect(instance)
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for attr in state.attrs:
        if attr.key in AUDIT_SKIP_COLUMNS:
            continue
        history = attr.history
        if history.has_changes():
            if history.deleted:
                old[attr.key] = _serialize_value(history.deleted[0])
            new[attr.key] = _serialize_value(attr.value)
    return old, new


def _resolve_tenant_id(instance: Any, ctx: RequestContext | None) -> uuid.UUID | None:
    """
    Audit log potřebuje tenant_id. Priorita:
    1. instance.tenant_id (většina tabulek)
    2. request context tenant_id (edge case: tabulky bez tenant_id - třeba Tenant)
    """
    value = getattr(instance, "tenant_id", None)
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            pass
    return ctx.tenant_id if ctx else None


# ── SQLAlchemy event listener ────────────────────────────────────────────────

def _audit_instance(
    session: Session,
    instance: Any,
    action: str,
) -> None:
    """Vytvoří jeden audit řádek pro INSERT/UPDATE/DELETE instance."""
    from app.models.audit_log import AuditLog  # lazy import

    table_name = instance.__tablename__
    if table_name in AUDIT_EXCLUDED_TABLES:
        return

    ctx = get_request_context()
    tenant_id = _resolve_tenant_id(instance, ctx)
    if tenant_id is None:
        # Bez tenant_id nemá audit smysl — většinou jde o setup operace
        # (registrace, alembic). Logujeme debug a pokračujeme.
        log.debug("Skipping audit for %s: no tenant_id resolvable", table_name)
        return

    # Diff
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    if action == "CREATE":
        new_values = _collect_values(instance)
    elif action == "UPDATE":
        old_values, new_values = _diff_updated(instance)
        if not new_values:
            # Žádná reálná změna — neaudituj
            return
    elif action == "DELETE":
        old_values = _collect_values(instance)

    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=ctx.user_id if ctx else None,
        action=action,
        resource_type=table_name,
        resource_id=str(getattr(instance, "id", "")),
        old_values=old_values,
        new_values=new_values,
        ip_address=ctx.ip_address if ctx else None,
        user_agent=ctx.user_agent if ctx else None,
    )
    session.add(entry)


def _before_flush_listener(
    session: Session,
    flush_context: Any,  # noqa: ARG001
    instances: Any,  # noqa: ARG001
) -> None:
    """
    Hlavní hook — pro každou nově přidanou/změněnou/smazanou entitu
    vytvoří audit řádek. Spouští se před flush, takže AuditLog
    instance se do flushe zahrne automaticky.
    """
    try:
        for obj in list(session.new):
            _audit_instance(session, obj, "CREATE")
        for obj in list(session.dirty):
            if not session.is_modified(obj):
                continue
            _audit_instance(session, obj, "UPDATE")
        for obj in list(session.deleted):
            _audit_instance(session, obj, "DELETE")
    except Exception as e:  # noqa: BLE001
        # Audit selhání nesmí blokovat byznys operaci. Logujeme + pokračujeme.
        log.exception("Audit log failure (suppressed): %s", e)


def install_audit_listeners() -> None:
    """Zavěsí listener na úrovni Session class. Zavolat jednou při startu app."""
    if not event.contains(Session, "before_flush", _before_flush_listener):
        event.listen(Session, "before_flush", _before_flush_listener)


# Pomocná serializace pro debug — reexport
def audit_json(data: Any) -> str:
    return json.dumps(data, default=_serialize_value, ensure_ascii=False)


# Timestamp helper (abychom neimportovali datetime všude)
def now_utc() -> datetime:
    return datetime.now(UTC)
