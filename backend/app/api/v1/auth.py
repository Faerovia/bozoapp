import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import login_user, register_user

router = APIRouter()


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    _, access_token, refresh_token = await register_user(db, data)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    data: LoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    result = await login_user(db, data.email, data.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávný email nebo heslo",
        )
    _, access_token, refresh_token = result
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Neplatný nebo expirovaný refresh token",
    )
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise exc
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (JWTError, KeyError, ValueError):
        raise exc

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise exc

    return TokenResponse(
        access_token=create_access_token(user.id, tenant_id, user.role),
        refresh_token=create_refresh_token(user.id, tenant_id),
    )


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
