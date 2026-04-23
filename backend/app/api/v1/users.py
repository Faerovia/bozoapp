import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.users import UserCreateRequest, UserResponse, UserUpdateRequest
from app.services.users import create_user, get_user_by_id, get_users, update_user

router = APIRouter()


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """Vrátí všechny uživatele tenantu. Přístup: ozo, manager."""
    return await get_users(db, current_user.tenant_id)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    data: UserCreateRequest,
    current_user: User = Depends(require_role("ozo")),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Vytvoří nového uživatele v tenantu. Přístup: pouze ozo."""
    return await create_user(db, data, current_user.tenant_id)


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    """Vrátí profil přihlášeného uživatele. Přístup: všechny role."""
    return current_user


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Vrátí detail uživatele.
    OZO/manager vidí kohokoliv v tenantu, employee pouze sebe.
    """
    if current_user.role == "employee" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zaměstnanec může vidět pouze svůj vlastní profil",
        )

    user = await get_user_by_id(db, user_id, current_user.tenant_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uživatel nenalezen")

    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Aktualizuje uživatele.
    - OZO: může měnit kohokoliv v tenantu (vč. role a is_active)
    - Employee/manager: může měnit pouze sebe (jen full_name a password)
    """
    is_ozo = current_user.role == "ozo"

    if not is_ozo and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nemáte oprávnění upravovat jiné uživatele",
        )

    user = await get_user_by_id(db, user_id, current_user.tenant_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uživatel nenalezen")

    return await update_user(db, user, data, is_ozo=is_ozo)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Deaktivuje uživatele (is_active=False). Neprovádí fyzické smazání.
    OZO nemůže deaktivovat sám sebe.
    """
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nemůžete deaktivovat vlastní účet",
        )

    user = await get_user_by_id(db, user_id, current_user.tenant_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uživatel nenalezen")

    user.is_active = False
    await db.flush()
