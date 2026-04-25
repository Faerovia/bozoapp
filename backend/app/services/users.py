import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.schemas.users import UserCreateRequest, UserUpdateRequest


async def get_users(db: AsyncSession, tenant_id: uuid.UUID) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.created_at)
    )
    return list(result.scalars().all())


async def get_user_by_id(
    db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession, data: UserCreateRequest, tenant_id: uuid.UUID
) -> User:
    user = User(
        tenant_id=tenant_id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    await db.flush()

    # Membership na tenant — bez ní get_current_user vrací 401 po refaktoru.
    from app.models.membership import UserTenantMembership
    db.add(UserTenantMembership(
        user_id=user.id,
        tenant_id=tenant_id,
        role=data.role,
        is_default=True,
    ))
    await db.flush()
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    data: UserUpdateRequest,
    is_ozo: bool,
) -> User:
    """
    Aplikuje aktualizaci uživatele s kontrolou oprávnění.
    is_ozo=True → může měnit role a is_active.
    """
    if data.full_name is not None:
        user.full_name = data.full_name

    if data.password is not None:
        user.hashed_password = hash_password(data.password)

    if is_ozo:
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active

    await db.flush()
    return user
