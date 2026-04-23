from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.models.user import User

# Hierarchie rolí pro BOZP SaaS:
# ozo      – OZO poradce, plný přístup, spravuje tenant a uživatele
# manager  – vedoucí/bezpečnostní technik, čte vše, omezené úpravy
# employee – zaměstnanec, přístup jen ke svým záznamům


def require_role(*roles: str):
    """
    FastAPI dependency factory. Použití:

        @router.get("/something")
        async def endpoint(user: User = Depends(require_role("ozo", "manager"))):
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
