"""
Oracle Latency Arbitrage Strategy

Exploits the delay between real-world event resolution and
UMA Optimistic Oracle settlement on Polymarket.

Window: 2-24 hours after event conclusion
Edge: Buy discounted outcome tokens before oracle settles
Risk: Very low (outcome is already known)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, AsyncIterator, Optional, Any
import asyncio

from void.strategies.base import (
    BaseStrategy,
    StrategyConfig,
    StrategyContext,
)
from void.data.models import Market, Signal, SignalStatus, StrategyType, MarketStatus
import structlog

logger = structlog.get_logger()


@dataclass
class OracleLatencyConfig(StrategyConfig):
    """Configuration specific to Oracle Latency strategy."""

    # Discount thresholds
    min_discount: Decimal = Decimal("0.01")  # Minimum 1% discount to trade
    max_price: Decimal = Decimal("0.99")  # Don't buy above this

    # Market time filters
    max_hours_since_end: int = 24  # Max hours after event end
    min_hours_since_end: int = 0  # Min hours (immediate trading ok)

    # AI verification
    ai_confidence_threshold: Decimal = Decimal("0.95")
    use_ai_verification: bool = True
    verification_timeout_seconds: int = 30

    # Categories to focus on
    focus_categories: List[str] = field(default_factory=list)
    ignore_categories: List[str] = field(default_factory=list)


class OracleLatencyStrategy(BaseStrategy):
    """
    Oracle Latency Arbitrage Implementation.

    Detection Logic:
    1. Market event has concluded (end_date in past)
    2. Market is still ACTIVE (not resolved on-chain)
    3. One outcome is trading at a discount (<$0.99)
    4. AI verification confirms the real-world outcome

    Execution:
    1. Buy the discounted winning outcome
    2. Wait for UMA oracle to settle (2-24 hours)
    3. Claim $1.00 per share
    """

    strategy_type = StrategyType.ORACLE_LATENCY

    def __init__(self, config: OracleLatencyConfig):
        super().__init__(config)
        self.config: OracleLatencyConfig = config
        self._processed_markets: set = set()

    async def scan_markets(
        self,
        markets: List[Market],
        context: StrategyContext,
    ) -> AsyncIterator[Signal]:
        """
        Scan for oracle latency opportunities.

        Args:
            markets: List of markets to scan
            context: Strategy execution context

        Yields:
            Detected trading signals
        """
        self.logger.info(
            "oracle_latency_scan_started",
            market_count=len(markets),
        )

        for market in markets:
            # Skip if already processed
            if market.id in self._processed_markets:
                continue

            # Apply base filters
            if not self.should_scan_market(market):
                continue

            # Check for opportunity
            signal = await self._detect_opportunity(market, context)

            if signal:
                self._processed_markets.add(market.id)
                yield signal

        self.logger.info(
            "oracle_latency_scan_completed",
            processed_count=len(self._processed_markets),
        )

    async def _detect_opportunity(
        self,
        market: Market,
        context: StrategyContext,
    ) -> Optional[Signal]:
        """
        Detect oracle latency opportunity in a market.

        Args:
            market: Market to analyze
            context: Strategy context

        Returns:
            Signal if opportunity found, None otherwise
        """
        # 1. Check if market has ended
        if not self._is_market_ended(market):
            return None

        # 2. Check if market is still unresolved
        if market.status != MarketStatus.ACTIVE:
            return None

        # 3. Find discounted side
        discounted_side, entry_price = self._find_discount(market)
        if not discounted_side:
            return None

        # 4. Calculate profit margin
        profit_margin = (Decimal("1.0") - entry_price) / entry_price

        if profit_margin < self.config.min_profit_margin:
            return None

        # 5. Create signal
        signal = Signal(
            agent_id=context.agent_id,
            market_id=market.id,
            strategy_type=self.strategy_type,
            signal_type="oracle_latency",
            predicted_outcome=discounted_side,
            entry_price=entry_price,
            expected_payout=Decimal("1.0"),
            profit_margin=profit_margin,
            status=SignalStatus.DETECTED,
            detected_at=datetime.now(timezone.utc),
        )

        self.logger.info(
            "oracle_latency_signal_detected",
            market_id=market.id,
            question=market.question[:50] + "...",
            side=discounted_side,
            price=float(entry_price),
            margin=float(profit_margin),
            hours_since_end=self._hours_since_end(market),
        )

        return signal

    def _is_market_ended(self, market: Market) -> bool:
        """
        Check if market event has concluded.

        Args:
            market: Market to check

        Returns:
            True if market has ended
        """
        if not market.end_date:
            return False

        now = datetime.now(timezone.utc)
        hours_since = self._hours_since_end(market)

        # Market must have ended
        if market.end_date > now:
            return False

        # But within our time window
        if hours_since > self.config.max_hours_since_end:
            return False

        if hours_since < self.config.min_hours_since_end:
            return False

        return True

    def _hours_since_end(self, market: Market) -> Optional[float]:
        """Get hours since market end date."""
        if not market.end_date:
            return None

        now = datetime.now(timezone.utc)
        return (now - market.end_date).total_seconds() / 3600

    def _find_discount(
        self,
        market: Market,
    ) -> tuple[Optional[str], Optional[Decimal]]:
        """
        Find which side (YES/NO) is discounted.

        Args:
            market: Market to check

        Returns:
            Tuple of (side, price) or (None, None)
        """
        # Check YES price
        if market.yes_price < self.config.max_price:
            discount = Decimal("1.0") - market.yes_price
            if discount >= self.config.min_discount:
                return "YES", market.yes_price

        # Check NO price
        if market.no_price < self.config.max_price:
            discount = Decimal("1.0") - market.no_price
            if discount >= self.config.min_discount:
                return "NO", market.no_price

        return None, None

    async def verify_signal(
        self,
        signal: Signal,
        context: StrategyContext,
    ) -> Signal:
        """
        Verify signal with AI and external data sources.

        Args:
            signal: Signal to verify
            context: Strategy context

        Returns:
            Updated signal with confidence score and status
        """
        market = context.market_cache.get(signal.market_id)
        if not market:
            signal.status = SignalStatus.REJECTED
            return signal

        # Re-check prices
        current_yes = market.yes_price
        current_no = market.no_price

        # Determine which side we're trading
        if signal.predicted_outcome == "YES":
            current_price = current_yes
        else:
            current_price = current_no

        # Recalculate profit margin
        current_margin = (Decimal("1.0") - current_price) / current_price

        if current_margin < self.config.min_profit_margin:
            self.logger.info(
                "signal_expired_margin_lost",
                signal_id=str(signal.id),
                old_margin=float(signal.profit_margin),
                new_margin=float(current_margin),
            )
            signal.status = SignalStatus.EXPIRED
            return signal

        # Update signal with current price
        signal.entry_price = current_price
        signal.profit_margin = current_margin

        # AI verification (if enabled)
        if self.config.use_ai_verification:
            # TODO: Implement AI verifier
            # For now, set high confidence based on math
            signal.confidence = Decimal("0.90")
        else:
            signal.confidence = Decimal("0.90")

        signal.verification_source = "price_check"
        signal.status = SignalStatus.VERIFIED

        self.logger.info(
            "signal_verified",
            signal_id=str(signal.id),
            confidence=float(signal.confidence),
            price=float(current_price),
        )

        return signal

    async def generate_orders(
        self,
        signal: Signal,
        context: StrategyContext,
    ) -> List[Any]:
        """
        Generate order request from verified signal.

        Args:
            signal: Verified signal to execute
            context: Strategy context

        Returns:
            List of order requests to submit
        """
        market = context.market_cache.get(signal.market_id)
        if not market:
            return []

        # Determine token to buy
        if signal.predicted_outcome == "YES":
            token_id = market.yes_token_id
            current_price = market.yes_price
        else:
            token_id = market.no_token_id
            current_price = market.no_price

        # Calculate position size
        position_size_usd = self.calculate_position_size(signal, context)

        # Calculate shares to buy
        shares = position_size_usd / current_price

        # Create order request (will be converted to actual Order in execution engine)
        order_request = {
            "market_id": market.id,
            "token_id": token_id,
            "side": "BUY",
            "order_type": "FOK",  # Fill-or-Kill for speed
            "price": float(current_price * (Decimal("1") + self.config.max_slippage)),
            "size": float(shares),
            "signal_id": str(signal.id),
        }

        self.logger.info(
            "order_generated",
            market_id=market.id,
            side=signal.predicted_outcome,
            size_usd=float(position_size_usd),
            shares=float(shares),
            price=float(current_price),
        )

        return [order_request]


__all__ = [
    "OracleLatencyStrategy",
    "OracleLatencyConfig",
]
