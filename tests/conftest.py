"""
Test configuration and fixtures.
"""

import pytest
import asyncio
from typing import AsyncGenerator
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from void.data.models import Base
from void.config import config


# Test database URL
TEST_DB_URL = "postgresql+asyncpg://test:test@localhost:5433/void_test"


# ============== FIXTURES ==============

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests."""
    async_session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "id": "test-market-1",
        "conditionId": "0x" + "1" * 64,
        "question": "Will BTC hit $100k?",
        "slug": "btc-100k",
        "yes_token_id": "yes-123",
        "no_token_id": "no-456",
        "yes_price": 0.85,
        "no_price": 0.15,
        "volume_24h": 50000.0,
        "liquidity": 10000.0,
        "end_date": "2026-01-01T00:00:00Z",
        "category": "crypto",
        "tags": ["bitcoin", "crypto"],
    }


@pytest.fixture
def sample_signal_data(sample_market_data):
    """Sample signal data."""
    from void.data.models import Signal, SignalStatus, StrategyType
    from datetime import datetime, timezone
    from uuid import uuid4

    return Signal(
        id=uuid4(),
        agent_id=uuid4(),
        market_id=sample_market_data["id"],
        strategy_type=StrategyType.ORACLE_LATENCY,
        signal_type="oracle_latency",
        predicted_outcome="YES",
        entry_price=0.85,
        expected_payout=1.0,
        profit_margin=0.176,
        confidence=0.95,
        status=SignalStatus.DETECTED,
        detected_at=datetime.now(timezone.utc),
    )
