import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_attesta.db")

from app.db.models import Base  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB = os.environ["DATABASE_URL"]
_connect_args: dict[str, object] = {}
if "sqlite" in TEST_DB:
    _connect_args["check_same_thread"] = False
engine = create_async_engine(TEST_DB, connect_args=_connect_args)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        if "sqlite" not in TEST_DB:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables():
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield


@pytest.fixture
async def db_session() -> AsyncSession:
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
