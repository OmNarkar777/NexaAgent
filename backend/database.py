"""
nexaagent/backend/database.py
Async SQLAlchemy engine, session factory, and Redis client.
"""
from typing import AsyncGenerator
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import settings

logger = structlog.get_logger(__name__)

engine = create_async_engine(
    settings.database_url,
    pool_size=20, max_overflow=40,
    pool_pre_ping=True, pool_recycle=3600,
    echo=not settings.is_production,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession,
    expire_on_commit=False, autoflush=False, autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialised. Call init_redis() first.")
    return _redis_client


async def init_redis() -> aioredis.Redis:
    global _redis_client
    _redis_client = await aioredis.from_url(
        settings.redis_url, encoding="utf-8",
        decode_responses=True, max_connections=50,
    )
    await _redis_client.ping()
    logger.info("redis.connected", url=settings.redis_url)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


async def create_tables() -> None:
    from . import models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database.tables_created")


async def dispose_engine() -> None:
    await engine.dispose()
