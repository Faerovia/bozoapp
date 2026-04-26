from typing import Any

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.models.user import User

# Hierarchie rolí pro BOZP SaaS:
#
# admin                  – platform-level (SaaS operator); spravuje tenanty.
#                          Vyžaduje is_platform_admin=True pro cross-tenant akce.
# ozo                    – OZO poradce; full access v tenantu
# hr_manager             – HR manager; full access v tenantu
# lead_worker            – Vedoucí pracovník; vidí přiřazení své skupiny
# equipment_responsible  – Zaměstnanec + správa revizí/vyhrazených zařízení
# employee               – Přístup jen ke svým záznamům
#
# Konvence rovnosti: `ozo` a `hr_manager` mají stejná práva napříč moduly;
# `TENANT_MANAGERS` je zkratka pro tyto dvě role dohromady.

TENANT_MANAGERS: tuple[str, ...] = ("ozo", "hr_manager")


def require_role(*roles: str) -> Any:
    """
    FastAPI dependency factory pro tenant-level role checking.

        @router.get("/something")
        async def endpoint(user: User = Depends(require_role(*TENANT_MANAGERS))):
            ...
    """

    async def check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nedostatečná oprávnění pro tuto operaci",
            )
        return current_user

    return check_role


def require_platform_admin() -> Any:
    """
    FastAPI dependency factory pro platform-level admin endpointy.

    Kontroluje:
    1. user.is_platform_admin == True (flag nastavený manuálně / CLI příkazem)
    2. user.role == "admin" (konzistence)

    RLS kontext `app.is_platform_admin='true'` se setuje v
    dependencies.get_current_user → všechny následné DB dotazy jdou cross-tenant.
    """

    async def check_admin(current_user: User = Depends(get_current_user)) -> User:
        if not (current_user.is_platform_admin and current_user.role == "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform admin přístup vyžadován",
            )
        return current_user

    return check_admin
