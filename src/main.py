"""
Main entry point for VOID Trading Agent.

Usage:
    python -m void.agent                    # Start agent
    python -m void.agent --strategy oracle_latency  # Specific strategy
    python -m void.agent --dry-run          # Simulation mode
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import structlog
from void.config import config
from void.messaging import EventBus
from void.data.database import init_db, close_db
from void.accounts.service import AccountService
from void.agent.orchestrator import AgentOrchestrator
from void.data.models import Agent, AgentStatus, StrategyType
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from datetime import datetime, timezone

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


async def create_demo_agent(db: AsyncSession) -> Agent:
    """Create a demo agent for testing."""
    # Check if agent already exists
    from sqlalchemy import select
    result = await db.execute(
        select(Agent).where(Agent.name == "oracle-latency-agent-1")
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info("demo_agent_exists", agent_id=str(existing.id))
        return existing

    # Create new agent
    agent = Agent(
        name="oracle-latency-agent-1",
        status=AgentStatus.IDLE,
        account_id=uuid4(),  # Will need to create account first
        strategy_type=StrategyType.ORACLE_LATENCY,
        strategy_config={
            "max_position_size_usd": "500",
            "max_positions": 3,
            "min_profit_margin": "0.01",
            "min_discount": "0.01",
            "max_hours_since_end": 24,
            "use_ai_verification": True,
        },
        max_position_size=500,
        max_daily_loss=100,
        max_concurrent_positions=3,
    )

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info("demo_agent_created", agent_id=str(agent.id))
    return agent


async def main():
    """Main entry point."""
    logger.info(
        "void_starting",
        version="1.0.0",
        environment=config.environment,
    )

    # Initialize database
    logger.info("initializing_database")
    await init_db()

    # Create event bus
    logger.info("initializing_event_bus")
    event_bus = EventBus()
    await event_bus.connect()

    # Subscribe to events
    async def log_event(event_data):
        logger.info("event_received", **event_data)

    # Subscribe to all signal events
    from void.messaging.events import EventType
    await event_bus.subscribe(EventType.SIGNAL_DETECTED, log_event)
    await event_bus.subscribe(EventType.SIGNAL_VERIFIED, log_event)
    await event_bus.subscribe(EventType.ORDER_SUBMITTED, log_event)

    # Create services
    from void.data.database import async_session_maker

    async with async_session_maker() as db:
        account_service = AccountService(db)
        orchestrator = AgentOrchestrator(db, account_service, event_bus)

        # Create demo account
        logger.info("creating_demo_account")
        account = await account_service.create_account(
            name="demo-account",
            private_key=None,  # Will generate new key
        )

        # Sync balances
        logger.info("syncing_balances")
        account = await account_service.sync_balances(account.id)

        logger.info(
            "account_created",
            account_id=str(account.id),
            address=account.address,
            usdc_balance=float(account.usdc_balance),
            matic_balance=float(account.matic_balance),
        )

        # Create and start agent
        agent = await create_demo_agent(db)

        # Update agent with real account
        agent.account_id = account.id
        await db.commit()

        logger.info(
            "starting_agent",
            agent_id=str(agent.id),
            strategy=agent.strategy_type.value,
        )

        try:
            await orchestrator.start_agent(agent.id)

            # Keep running
            logger.info("agent_running", press_ctrl_c="Press Ctrl+C to stop")

            # Run forever
            while True:
                await asyncio.sleep(60)

                # Check agent status
                await db.refresh(agent)
                logger.info(
                    "agent_status",
                    status=agent.status.value,
                    heartbeat=str(agent.last_heartbeat),
                )

        except KeyboardInterrupt:
            logger.info("shutting_down")

            # Stop agent
            await orchestrator.stop_agent(agent.id)

            # Close connections
            await event_bus.disconnect()
            await close_db()

            logger.info("void_stopped")
            sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("interrupted")
        sys.exit(0)
