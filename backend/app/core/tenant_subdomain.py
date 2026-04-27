"""Subdomain → tenant resolver middleware.

Production model:
- {tenant-slug}.digitalozo.cz → tenant
- admin.digitalozo.cz → platform admin (žádný tenant)
- digitalozo.cz / www.digitalozo.cz → marketing root (FE rozhodne kam)

Local dev (FRONTEND_BASE_DOMAIN=.localhost):
- {tenant-slug}.localhost:3000 → tenant
- admin.localhost:3000 → platform admin

Middleware extrahuje subdomain z Host hlavičky, najde tenant.id a uloží
do `request.state.tenant_from_subdomain`. Login endpoint pak ví, do
kterého tenantu hledat usera podle email/personal_number.

LRU cache: tenant slug → (tenant_id, name) na 60 sekund.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import AsyncSessionLocal
from app.models.tenant import Tenant

log = logging.getLogger("tenant_subdomain")

# Cache TTL — 60s je rozumný kompromis mezi čerstvostí (slug se může
# změnit) a šetřením DB. Pro vyšší zátěž zvýšit nebo přepsat na Redis.
_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[uuid.UUID, str, float]] = {}


# Subdomény, které NEPATŘÍ konkrétnímu tenantu. Middleware u nich
# nehledá tenant v DB — request.state.tenant_from_subdomain zůstane None.
RESERVED_SUBDOMAINS = frozenset({
    "admin",      # platform admin
    "www",        # marketing
    "api",        # rezervováno
    "app",        # rezervováno (root pre-tenant landing page)
    "static",
    "cdn",
    "mail",
    "ftp",
})


def extract_subdomain(host: str | None, base_domain: str) -> str | None:
    """Vrátí slug z Host hlavičky, nebo None když host není pod base_domain.

    Příklady (base_domain='.digitalozo.cz'):
        'strojirny-abc.digitalozo.cz'        → 'strojirny-abc'
        'admin.digitalozo.cz'                → 'admin'
        'digitalozo.cz'                      → None (root)
        'localhost:3000'                     → None
        'strojirny-abc.localhost:3000'       → 'strojirny-abc'  (when base='.localhost')

    Port se odstraní. Base_domain musí začínat tečkou.
    """
    if not host:
        return None
    # Odstraň port
    h = host.split(":")[0].lower()

    base = base_domain.lower()
    if not base.startswith("."):
        base = "." + base

    if not h.endswith(base.lstrip(".")):
        return None

    # Strip base_domain z konce
    prefix = h[: -len(base.lstrip("."))].rstrip(".")
    if not prefix:
        return None

    # Multi-level subdomain (např. 'foo.bar.digitalozo.cz') — vezmi první
    # část. V tomhle modelu nepoužíváme nested.
    return prefix.split(".")[0] or None


async def _resolve_slug(slug: str) -> tuple[uuid.UUID, str] | None:
    """Najde tenant podle slugu. Cachuje na 60s."""
    now = time.time()
    cached = _cache.get(slug)
    if cached and cached[2] > now:
        return cached[0], cached[1]

    async with AsyncSessionLocal() as db:
        await _set_superadmin(db)
        result = await db.execute(
            select(Tenant.id, Tenant.name).where(Tenant.slug == slug),
        )
        row = result.first()
    if row is None:
        return None
    tenant_id, name = row
    _cache[slug] = (tenant_id, name, now + _CACHE_TTL_SECONDS)
    return tenant_id, name


async def _set_superadmin(db: AsyncSession) -> None:
    from sqlalchemy import text
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)"),
    )


def invalidate_cache(slug: str | None = None) -> None:
    """Pokud se slug tenantu změnil (rename), zavolat z services."""
    if slug is None:
        _cache.clear()
    else:
        _cache.pop(slug, None)


class TenantSubdomainMiddleware(BaseHTTPMiddleware):
    """Resolvuje tenant z Host hlavičky a uloží do request.state.

    Atributy:
    - `request.state.tenant_from_subdomain`: UUID nebo None
    - `request.state.tenant_slug`: str nebo None (pokud sub. existuje)
    - `request.state.tenant_name`: str nebo None (pro branded login UI)
    - `request.state.is_admin_subdomain`: bool (admin.digitalozo.cz)
    """

    def __init__(self, app: Callable, base_domain: str) -> None:  # type: ignore[type-arg]
        super().__init__(app)
        self.base_domain = base_domain

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Priorita: 1) explicitní X-Tenant-Slug header (klient ho posílá
        # když Next.js proxy přepíše Host), 2) extrakce z Host hlavičky.
        explicit_slug = request.headers.get("x-tenant-slug")
        if explicit_slug:
            slug = explicit_slug.strip().lower() or None
        else:
            host = request.headers.get("host")
            slug = extract_subdomain(host, self.base_domain)

        request.state.tenant_from_subdomain = None
        request.state.tenant_slug = None
        request.state.tenant_name = None
        request.state.is_admin_subdomain = False

        if slug:
            if slug in RESERVED_SUBDOMAINS:
                request.state.tenant_slug = slug
                request.state.is_admin_subdomain = (slug == "admin")
            else:
                resolved = await _resolve_slug(slug)
                if resolved is not None:
                    tenant_id, name = resolved
                    request.state.tenant_from_subdomain = tenant_id
                    request.state.tenant_slug = slug
                    request.state.tenant_name = name
                else:
                    log.info("Unknown tenant slug from subdomain: %s", slug)

        return await call_next(request)
