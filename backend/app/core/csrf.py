"""
CSRF ochrana pro cookie-based auth.

Model: **Double-Submit Cookie**.
- Při loginu/registraci/refresh server setuje non-httpOnly cookie `csrf_token`
  (random UUID). Klient ho umí přečíst z JS a přiložit jako hlavičku.
- Pro state-changing requesty (POST/PUT/PATCH/DELETE) middleware porovnává:
  cookie `csrf_token` == header `X-CSRF-Token`. Pokud nesedí → 403.
- Pokud request je GET/HEAD/OPTIONS nebo auth přes Bearer token, CSRF se
  přeskakuje (Bearer implicitně vyžaduje JS, SOP pro cross-site XHR).

Pro pohodlí: login/register endpoint je z CSRF výjimkou (uživatel nemá ještě
žádný token). Stejně tak /auth/refresh (samotný refresh se řeší přes httpOnly
cookie + rotation detekcí; CSRF jako další vrstva je over-engineering).

Skip patterns pokrývají auth endpointy. Další se přidávají v CSRF_EXEMPT_PATHS.
"""
from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Endpointy, na kterých CSRF nekontrolujeme:
# - /auth/login, /auth/register: uživatel ještě nemá CSRF cookie
# - /auth/refresh: chráněný path-bound httpOnly cookie + rotation
# - /auth/logout: state-changing, ale klient může cookie smazat jen svoji session
#   takže bez CSRF je OK (logout attack = no-op DOS)
CSRF_EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
})


def generate_csrf_token() -> str:
    """Cryptographically safe random string."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str, *, is_production: bool) -> None:
    """Setuje CSRF cookie — NON-httpOnly (klient musí přečíst z JS)."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # Musí být čitelné z JS — jinak double-submit nefunguje
        secure=is_production,
        samesite="lax",
        path="/",
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Kontroluje CSRF token pro state-changing cookie-authenticated requesty."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if self._should_check(request):
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)

            if not cookie_token or not header_token:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token chybí"},
                )
            if not secrets.compare_digest(cookie_token, header_token):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token nesouhlasí"},
                )

        return await call_next(request)

    @staticmethod
    def _should_check(request: Request) -> bool:
        if request.method in SAFE_METHODS:
            return False
        if request.url.path in CSRF_EXEMPT_PATHS:
            return False
        # Bearer token → request pravděpodobně z JS s explicitním Authorization,
        # což SOP chrání před cross-site. CSRF kontrola neplatí.
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return False
        # Zbytek: cookie-authenticated state-changing request → kontroluj.
        return True
