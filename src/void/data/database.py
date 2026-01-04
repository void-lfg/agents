"""
Database connection and session management.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base

from void.config import config
from void.data.models import Base


# Create async engine
# Parse connect args from URL for asyncpg
from urllib.parse import urlparse, parse_qs
db_url = str(config.database.url)
parsed = urlparse(db_url)

# Extract SSL mode from query params and clean URL
connect_args = {}
clean_url = db_url
if parsed.query:
    params = parse_qs(parsed.query)
    if 'sslmode' in params:
        connect_args['ssl'] = params['sslmode'][0]
    # Remove query string from URL
    clean_url = parsed._replace(query='').geturl()

engine: AsyncEngine = create_async_engine(
    clean_url,
    echo=config.database.echo,
    pool_size=config.database.pool_size,
    max_overflow=config.database.max_overflow,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args=connect_args if connect_args else None,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.

    Usage:
        @router.get("/markets")
        async def list_markets(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Market))
            return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Initialize database - create all tables.

    NOTE: In production, use Alembic migrations instead!
    This is only for development/testing.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()


__all__ = [
    "engine",
    "async_session_maker",
    "get_db",
    "init_db",
    "close_db",
]
