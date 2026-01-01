"""
Abstract base class for all trading strategies.

All strategies must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any, AsyncIterator
from uuid import UUID
from enum import Enum

from void.data.models import Market, Signal, SignalStatus, StrategyType, OrderSide
import structlog

logger = structlog.get_logger()


class StrategySignal(str, Enum):
    """Signal types for strategies."""
    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    BUY_BOTH = "buy_both"  # For binary arbitrage
    HOLD = "hold"
    CLOSE = "close"


@dataclass
class StrategyConfig:
    """Base configuration for all strategies."""

    # Enable/disable
    enabled: bool = True

    # Capital allocation
    max_position_size_usd: Decimal = Decimal("500")
    max_positions: int = 3

    # Risk parameters
    min_profit_margin: Decimal = Decimal("0.01")  # 1%
    max_slippage: Decimal = Decimal("0.02")  # 2%

    # Filters
    min_liquidity_usd: Decimal = Decimal("1000")
    min_volume_24h_usd: Decimal = Decimal("5000")
    excluded_categories: List[str] = field(default_factory=list)
    excluded_tags: List[str] = field(default_factory=list)

    # Timing
    scan_interval_seconds: int = 30
    signal_expiry_seconds: int = 300  # 5 minutes
    cooldown_after_trade_seconds: int = 60


@dataclass
class StrategyContext:
    """Context passed to strategy during execution."""

    agent_id: UUID
    account_id: UUID
    config: StrategyConfig

    # Current state
    active_positions: List[Any]  # Position objects
    pending_orders: List[Any]  # Order objects
    recent_signals: List[Signal]

    # Market data
    market_cache: Dict[str, Market]

    # Timestamps
    last_scan_at: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Strategies are responsible for:
    1. Scanning markets for opportunities
    2. Generating trading signals
    3. Validating signals before execution
    4. Generating order requests from signals
    """

    strategy_type: StrategyType

    def __init__(self, config: StrategyConfig):
        self.config = config
        self._is_running = False
        self.logger = logger.bind(strategy=self.strategy_type.value)

    @property
    def name(self) -> str:
        """Human-readable strategy name."""
        return self.__class__.__name__

    @abstractmethod
    async def scan_markets(
        self,
        markets: List[Market],
        context: StrategyContext,
    ) -> AsyncIterator[Signal]:
        """
        Scan markets and yield potential signals.

        This is the main entry point for signal detection.
        Implementations should yield signals as they are detected.

        Args:
            markets: List of markets to scan
            context: Current strategy execution context

        Yields:
            Signal objects for detected opportunities
        """
        pass

    @abstractmethod
    async def verify_signal(
        self,
        signal: Signal,
        context: StrategyContext,
    ) -> Signal:
        """
        Verify a signal before execution.

        This should perform any additional validation:
        - AI verification for oracle latency
        - Price rechecking for arbitrage
        - Liquidity confirmation

        Args:
            signal: Signal to verify
            context: Current strategy execution context

        Returns:
            Updated signal with confidence score and status
        """
        pass

    @abstractmethod
    async def generate_orders(
        self,
        signal: Signal,
        context: StrategyContext,
    ) -> List[Any]:
        """
        Generate order requests from a verified signal.

        Args:
            signal: Verified signal to execute
            context: Current strategy execution context

        Returns:
            List of OrderRequest objects to submit
        """
        pass

    async def on_signal_detected(self, signal: Signal) -> None:
        """Hook called when a signal is first detected."""
        self.logger.info(
            "signal_detected",
            signal_id=str(signal.id),
            market_id=signal.market_id,
            signal_type=signal.signal_type,
            profit_margin=float(signal.profit_margin),
        )

    async def on_signal_verified(self, signal: Signal) -> None:
        """Hook called after signal verification."""
        self.logger.info(
            "signal_verified",
            signal_id=str(signal.id),
            confidence=float(signal.confidence),
            status=signal.status.value,
        )

    async def on_signal_executed(self, signal: Signal, orders: List[Any]) -> None:
        """Hook called after orders are submitted."""
        self.logger.info(
            "signal_executed",
            signal_id=str(signal.id),
            order_count=len(orders),
        )

    async def on_signal_expired(self, signal: Signal) -> None:
        """Hook called when a signal expires without execution."""
        self.logger.warning(
            "signal_expired",
            signal_id=str(signal.id),
            market_id=signal.market_id,
        )

    def should_scan_market(self, market: Market) -> bool:
        """
        Pre-filter markets before detailed scanning.

        Override for strategy-specific filtering.

        Args:
            market: Market to check

        Returns:
            True if market should be scanned
        """
        # Check liquidity
        if market.liquidity < self.config.min_liquidity_usd:
            return False

        # Check volume
        if market.volume_24h < self.config.min_volume_24h_usd:
            return False

        # Check category exclusions
        if market.category and market.category in self.config.excluded_categories:
            return False

        # Check tag exclusions
        if any(tag in self.config.excluded_tags for tag in market.tags):
            return False

        return True

    def calculate_position_size(
        self,
        signal: Signal,
        context: StrategyContext,
    ) -> Decimal:
        """
        Calculate position size for a signal.

        Override for custom sizing logic.

        Args:
            signal: Trading signal
            context: Strategy context

        Returns:
            Position size in USD
        """
        # Don't exceed max position size
        max_size = self.config.max_position_size_usd

        # Scale by confidence
        if signal.confidence:
            confidence_multiplier = min(signal.confidence, Decimal("1.0"))
            adjusted_size = max_size * confidence_multiplier
        else:
            adjusted_size = max_size * Decimal("0.5")  # Conservative default

        # Account for existing exposure
        current_exposure = sum(
            pos.current_value for pos in context.active_positions
        )
        remaining_capacity = (
            self.config.max_position_size_usd * self.config.max_positions
            - current_exposure
        )

        return min(adjusted_size, remaining_capacity)

    def is_within_risk_limits(self, context: StrategyContext) -> bool:
        """
        Check if we can take new positions.

        Args:
            context: Strategy context

        Returns:
            True if within risk limits
        """
        # Check position count
        if len(context.active_positions) >= self.config.max_positions:
            return False

        # Check cooldown
        if context.last_trade_at:
            elapsed = (datetime.now(timezone.utc) - context.last_trade_at).total_seconds()
            if elapsed < self.config.cooldown_after_trade_seconds:
                return False

        return True

    async def start(self) -> None:
        """Start the strategy."""
        self._is_running = True
        self.logger.info("strategy_started", name=self.name)

    async def stop(self) -> None:
        """Stop the strategy."""
        self._is_running = False
        self.logger.info("strategy_stopped", name=self.name)

    @property
    def is_running(self) -> bool:
        """Check if strategy is running."""
        return self._is_running


__all__ = [
    "BaseStrategy",
    "StrategyConfig",
    "StrategyContext",
    "StrategySignal",
]
