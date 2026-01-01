"""
Agent orchestrator - manages agent lifecycle and trading operations.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from void.data.models import (
    Agent,
    AgentStatus,
    Market,
    Signal,
    SignalStatus,
    Position,
    Order as OrderModel,
    OrderStatus,
)
from void.strategies.base import BaseStrategy, StrategyConfig, StrategyContext
from void.strategies.oracle_latency import OracleLatencyStrategy, OracleLatencyConfig
from void.execution.engine import ExecutionEngine
from void.execution.models import OrderRequest, OrderSide, OrderType
from void.accounts.service import AccountService
from void.messaging.events import AgentStartedEvent, AgentStoppedEvent, AgentErrorEvent
from void.data.feeds.polymarket import GammaClient
import structlog

logger = structlog.get_logger()


class AgentOrchestrator:
    """
    Orchestrates trading agent operations.

    Responsibilities:
    - Agent lifecycle (start, stop, pause, resume)
    - Market scanning loop
    - Signal detection and verification
    - Order execution
    - Position monitoring
    """

    def __init__(
        self,
        db: AsyncSession,
        account_service: AccountService,
        event_bus: Optional[any] = None,
    ):
        self.db = db
        self.account_service = account_service
        self.event_bus = event_bus

        # Strategy instances
        self._strategies: dict[UUID, BaseStrategy] = {}

        # Execution
        self.execution_engine = ExecutionEngine(db, account_service, event_bus)

        # Market data client
        self.gamma_client = GammaClient()

        # Background tasks
        self._scan_tasks: dict[UUID, asyncio.Task] = {}

    async def start_agent(self, agent_id: UUID) -> None:
        """
        Start a trading agent.

        Args:
            agent_id: Agent ID to start
        """
        # Get agent
        agent = await self._get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.status == AgentStatus.RUNNING:
            logger.warning("agent_already_running", agent_id=str(agent_id))
            return

        # Initialize strategy
        strategy = self._create_strategy(agent)
        await strategy.start()
        self._strategies[agent_id] = strategy

        # Update agent status
        agent.status = AgentStatus.RUNNING
        agent.started_at = datetime.now(timezone.utc)
        agent.last_heartbeat = datetime.now(timezone.utc)

        await self.db.commit()

        # Start background scan task
        task = asyncio.create_task(self._scan_loop(agent))
        self._scan_tasks[agent_id] = task

        # Publish event
        if self.event_bus:
            await self.event_bus.publish(
                AgentStartedEvent(
                    agent_id=agent.id,
                    strategy=agent.strategy_type.value,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        logger.info(
            "agent_started",
            agent_id=str(agent_id),
            strategy=agent.strategy_type.value,
        )

    async def stop_agent(self, agent_id: UUID) -> None:
        """
        Stop a trading agent.

        Args:
            agent_id: Agent ID to stop
        """
        # Get agent
        agent = await self._get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Stop strategy
        if agent_id in self._strategies:
            strategy = self._strategies[agent_id]
            await strategy.stop()
            del self._strategies[agent_id]

        # Cancel scan task
        if agent_id in self._scan_tasks:
            task = self._scan_tasks[agent_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._scan_tasks[agent_id]

        # Cancel all pending orders
        await self.execution_engine.cancel_all_orders(agent.account_id)

        # Update agent status
        agent.status = AgentStatus.STOPPED
        agent.stopped_at = datetime.now(timezone.utc)

        await self.db.commit()

        # Publish event
        if self.event_bus:
            await self.event_bus.publish(
                AgentStoppedEvent(
                    agent_id=agent.id,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        logger.info("agent_stopped", agent_id=str(agent_id))

    async def pause_agent(self, agent_id: UUID) -> None:
        """Pause an agent."""
        agent = await self._get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent.status = AgentStatus.PAUSED
        await self.db.commit()

        logger.info("agent_paused", agent_id=str(agent_id))

    async def resume_agent(self, agent_id: UUID) -> None:
        """Resume a paused agent."""
        agent = await self._get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent.status = AgentStatus.RUNNING
        await self.db.commit()

        logger.info("agent_resumed", agent_id=str(agent_id))

    async def _scan_loop(self, agent: Agent) -> None:
        """
        Main scanning loop for an agent.

        Continuously scans markets for opportunities.
        """
        strategy = self._strategies.get(agent.id)
        if not strategy:
            return

        logger.info(
            "scan_loop_started",
            agent_id=str(agent.id),
        )

        try:
            while strategy.is_running:
                try:
                    # Check if agent is still running
                    await self.db.refresh(agent)
                    if agent.status != AgentStatus.RUNNING:
                        break

                    # Build context
                    context = await self._build_context(agent)

                    # Fetch markets
                    markets = await self.gamma_client.get_markets(
                        active=True,
                        limit=100,
                    )

                    # Scan for signals
                    async for signal in strategy.scan_markets(markets, context):
                        # Process signal
                        await self._process_signal(agent, signal, context)

                    # Update heartbeat
                    agent.last_heartbeat = datetime.now(timezone.utc)
                    await self.db.commit()

                    # Wait before next scan
                    config = strategy.config
                    await asyncio.sleep(config.scan_interval_seconds)

                except asyncio.CancelledError:
                    logger.info("scan_loop_cancelled", agent_id=str(agent.id))
                    break

                except Exception as e:
                    logger.error(
                        "scan_loop_error",
                        agent_id=str(agent.id),
                        error=str(e),
                    )

                    # Update agent status
                    agent.status = AgentStatus.ERROR
                    agent.error_message = str(e)
                    await self.db.commit()

                    # Publish error event
                    if self.event_bus:
                        await self.event_bus.publish(
                            AgentErrorEvent(
                                agent_id=agent.id,
                                error=str(e),
                                timestamp=datetime.now(timezone.utc),
                            )
                        )

                    # Wait before retrying
                    await asyncio.sleep(60)

        finally:
            logger.info("scan_loop_ended", agent_id=str(agent.id))

    async def _process_signal(
        self,
        agent: Agent,
        signal: Signal,
        context: StrategyContext,
    ) -> None:
        """
        Process a detected signal.

        Args:
            agent: Agent instance
            signal: Detected signal
            context: Strategy context
        """
        try:
            # Save signal to database
            self.db.add(signal)
            await self.db.flush()

            # Verify signal
            strategy = self._strategies.get(agent.id)
            if not strategy:
                return

            verified_signal = await strategy.verify_signal(signal, context)

            # Update signal
            self.db.add(verified_signal)
            await self.db.commit()

            # Check if verified
            if verified_signal.status != SignalStatus.VERIFIED:
                logger.info(
                    "signal_not_verified",
                    signal_id=str(signal.id),
                    status=verified_signal.status.value,
                )
                return

            # Check if within risk limits
            if not strategy.is_within_risk_limits(context):
                logger.info(
                    "signal_rejected_risk_limits",
                    signal_id=str(signal.id),
                )
                return

            # Generate orders
            order_requests = await strategy.generate_orders(verified_signal, context)

            # Execute orders
            orders = []
            for request in order_requests:
                # Convert dict to OrderRequest
                from void.execution.models import OrderSide, OrderType

                order_request = OrderRequest(
                    market_id=request["market_id"],
                    token_id=request["token_id"],
                    side=OrderSide[request["side"].upper()],
                    order_type=OrderType[request["order_type"]],
                    price=Decimal(str(request["price"])),
                    size=Decimal(str(request["size"])),
                    signal_id=UUID(request["signal_id"]) if request.get("signal_id") else None,
                )

                result = await self.execution_engine.execute_order(
                    order_request,
                    agent.account_id,
                )

                if result.success:
                    orders.append(result)

            # Update signal
            signal.status = SignalStatus.EXECUTED
            signal.executed_at = datetime.now(timezone.utc)
            await self.db.commit()

            logger.info(
                "signal_executed",
                signal_id=str(signal.id),
                order_count=len(orders),
            )

        except Exception as e:
            logger.error(
                "signal_processing_error",
                signal_id=str(signal.id),
                error=str(e),
            )
            raise

    async def _build_context(self, agent: Agent) -> StrategyContext:
        """Build strategy execution context."""
        # Get active positions
        result = await self.db.execute(
            select(Position).where(
                Position.account_id == agent.account_id,
                Position.is_closed == False,
            )
        )
        active_positions = list(result.scalars().all())

        # Get pending orders
        result = await self.db.execute(
            select(OrderModel).where(
                OrderModel.account_id == agent.account_id,
                OrderModel.status.in_([
                    OrderStatus.PENDING,
                    OrderStatus.SUBMITTED,
                    OrderStatus.PARTIAL,
                ]),
            )
        )
        pending_orders = list(result.scalars().all())

        # TODO: Get recent signals from database

        # TODO: Build market cache

        from void.strategies.oracle_latency import OracleLatencyConfig

        return StrategyContext(
            agent_id=agent.id,
            account_id=agent.account_id,
            config=OracleLatencyConfig(**agent.strategy_config),
            active_positions=active_positions,
            pending_orders=pending_orders,
            recent_signals=[],
            market_cache={},
        )

    def _create_strategy(self, agent: Agent) -> BaseStrategy:
        """Create strategy instance for agent."""
        if agent.strategy_type == "oracle_latency":
            config = OracleLatencyConfig(**agent.strategy_config)
            return OracleLatencyStrategy(config)
        else:
            raise ValueError(f"Unknown strategy type: {agent.strategy_type}")

    async def _get_agent(self, agent_id: UUID) -> Optional[Agent]:
        """Get agent from database."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()


__all__ = ["AgentOrchestrator"]
