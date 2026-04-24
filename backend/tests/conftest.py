"""
Test configuration – transaction-rollback pattern pro SQLAlchemy 2.x async.

Klíčové: join_transaction_mode="create_savepoint" zajišťuje, že
session.commit() v endpointu vytvoří SAVEPOINT místo commitu outer
transakce. Outer transakce se na konci každého testu rollbackuje.

Každý test dostane vlastní engine/connection/session → žádné problémy
se session-scoped event loop v pytest-asyncio 0.24+.
"""

import os

# Vynucení test environmentu PŘED importem app — rate limit a další
# infra se rozhoduje podle ENVIRONMENT v module-load time (lru_cache).
# Bez tohoto v lokálním docker-compose testy narážejí na 5 registrací/hod.
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

settings = get_settings()


@pytest.fixture
async def test_engine():
    engine = create_async_engine(settings.database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_connection(test_engine):
    async with test_engine.connect() as conn:
        await conn.begin()
        yield conn
        await conn.rollback()


@pytest.fixture
async def db_session(db_connection):
    session = AsyncSession(
        bind=db_connection,
        expire_on_commit=False,
        # Klíčové: commit() v endpointu vytvoří savepoint, ne commit outer transakce
        join_transaction_mode="create_savepoint",
    )
    yield session
    await session.close()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
