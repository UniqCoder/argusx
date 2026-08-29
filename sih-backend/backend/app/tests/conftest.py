"""
app/tests/conftest.py — pytest fixtures shared across all test modules.
"""
from typing import Any, AsyncGenerator, Optional
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.routers.check_wallet import get_redis
from app.db.session import Base, get_db
from app.main import app as fastapi_app
import app.models  # noqa: F401 — load all models into Base.metadata
from app.workers.celery_app import celery_app

# Run Celery tasks eagerly in test suite
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=False,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class FakeRedis:
    """In-memory async Redis double for testing."""
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) else 0

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


@pytest_asyncio.fixture(scope="function")
async def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean in-memory database session per test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, fake_redis: FakeRedis) -> AsyncGenerator[AsyncClient, None]:
    """Async test client for FastAPI app with overridden DB and Redis sessions."""
    async def _override_get_db():
        yield db_session

    def _override_get_redis():
        return fake_redis

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.dependency_overrides[get_redis] = _override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://testserver",
    ) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Obtains valid JWT auth headers for investigator role."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "investigator@i4c.gov.in", "password": "devpass"},
    )
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
def vasp_api_headers() -> dict[str, str]:
    """Valid X-API-Key header for VASP check-wallet requests."""
    return {"X-API-Key": "dev_vasp_key_1"}
