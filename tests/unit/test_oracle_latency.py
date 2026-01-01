"""
Test Oracle Latency strategy.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from void.strategies.oracle_latency.strategy import (
    OracleLatencyStrategy,
    OracleLatencyConfig,
)
from void.strategies.oracle_latency.verifier import OutcomeVerifier, VerificationResult
from void.data.models import Market, MarketStatus
from void.strategies.base import StrategyContext


@pytest.mark.asyncio
class TestOracleLatencyStrategy:
    """Test Oracle Latency strategy."""

    @pytest.fixture
    def config(self):
        """Strategy configuration."""
        return OracleLatencyConfig(
            min_discount=Decimal("0.01"),
            max_hours_since_end=24,
            min_liquidity_usd=Decimal("1000"),
            use_ai_verification=True,
        )

    @pytest.fixture
    def strategy(self, config):
        """Strategy instance."""
        return OracleLatencyStrategy(config)

    @pytest.fixture
    def context(self):
        """Strategy context."""
        from uuid import uuid4

        return StrategyContext(
            agent_id=uuid4(),
            account_id=uuid4(),
            config=OracleLatencyConfig(),
            active_positions=[],
            pending_orders=[],
            recent_signals=[],
            market_cache={},
        )

    @pytest.fixture
    def sample_markets(self):
        """Sample markets."""
        return [
            Market(
                id="market-1",
                conditionId="0x" + "1" * 64,
                question="Will BTC hit $100k by end of 2025?",
                slug="btc-100k",
                yes_token_id="yes-1",
                no_token_id="no-1",
                clobTokenIds='["yes-1", "no-1"]',
                outcomePrices='[0.85, 0.15]',
                yes_price=Decimal("0.85"),
                no_price=Decimal("0.15"),
                volume_24h=Decimal("50000"),
                liquidity=Decimal("10000"),
                end_date=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                status=MarketStatus.ACTIVE,
                category="crypto",
                tags=["bitcoin"],
            ),
            Market(
                id="market-2",
                conditionId="0x" + "2" * 64,
                question="Will ETH hit $10k?",
                slug="eth-10k",
                yes_token_id="yes-2",
                no_token_id="no-2",
                clobTokenIds='["yes-2", "no-2"]',
                outcomePrices='[0.5, 0.5]',
                yes_price=Decimal("0.5"),
                no_price=Decimal("0.5"),
                volume_24h=Decimal("10000"),
                liquidity=Decimal("5000"),
                end_date=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                status=MarketStatus.ACTIVE,
                category="crypto",
                tags=["ethereum"],
            ),
        ]

    def test_should_scan_market_passes(self, strategy, sample_markets):
        """Test market scanning filter - passes."""
        market = sample_markets[0]  # High liquidity
        assert strategy.should_scan_market(market) is True

    def test_should_scan_market_fails_liquidity(self, strategy, sample_markets):
        """Test market scanning filter - fails low liquidity."""
        market = sample_markets[0]
        market.liquidity = Decimal("500")  # Below threshold
        assert strategy.should_scan_market(market) is False

    @pytest.mark.asyncio
    async def test_detect_opportunity_found(self, strategy, context, sample_markets):
        """Test opportunity detection - finds valid signal."""
        market = sample_markets[0]  # YES at 0.85, ended

        # Mock time
        with patch('void.strategies.oracle_latency.strategy.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.timezone.utc = timezone.utc

            signal = await strategy._detect_opportunity(market, context)

        assert signal is not None
        assert signal.predicted_outcome == "YES"
        assert signal.entry_price == Decimal("0.85")
        assert signal.profit_margin > 0

    @pytest.mark.asyncio
    async def test_detect_opportunity_no_discount(self, strategy, context, sample_markets):
        """Test opportunity detection - no discount."""
        market = sample_markets[1]  # Both at 0.5

        signal = await strategy._detect_opportunity(market, context)

        assert signal is None

    @pytest.mark.asyncio
    async def test_verify_signal_price_check(self, strategy, context, sample_markets):
        """Test signal verification - price recheck."""
        from void.data.models import Signal, SignalStatus
        from uuid import uuid4

        signal = Signal(
            id=uuid4(),
            agent_id=context.agent_id,
            market_id=sample_markets[0].id,
            strategy_type="oracle_latency",
            signal_type="oracle_latency",
            predicted_outcome="YES",
            entry_price=Decimal("0.85"),
            profit_margin=Decimal("0.176"),
            status=SignalStatus.DETECTED,
            detected_at=datetime.now(timezone.utc),
        )

        # Add to cache
        context.market_cache[sample_markets[0].id] = sample_markets[0]

        verified = await strategy.verify_signal(signal, context)

        assert verified.status == SignalStatus.VERIFIED
        assert verified.confidence >= Decimal("0.9")


@pytest.mark.asyncio
class TestOutcomeVerifier:
    """Test Z.ai outcome verifier."""

    @pytest.fixture
    def verifier(self):
        """Verifier instance."""
        return OutcomeVerifier()

    @pytest.mark.asyncio
    async def test_verify_outcome_with_zai(self, verifier):
        """Test outcome verification with Z.ai."""
        # Mock HTTP client
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{
                    "message": {
                        "content": "CONFIDENCE: 0.98\nREASONING: Bitcoin reached $100k on Dec 30, 2025."
                    }
                }]
            }

            result = await verifier._verify_with_zai(
                question="Will BTC hit $100k by end of 2025?",
                predicted_outcome="YES",
            )

            assert result.predicted_outcome == "YES"
            assert result.confidence == 0.98
            assert "Bitcoin" in result.reasoning

    def test_parse_zai_response(self, verifier):
        """Test Z.ai response parsing."""
        content = """CONFIDENCE: 0.95
REASONING: The event has concluded and the outcome is YES."""

        confidence, reasoning = verifier._parse_zai_response(content)

        assert confidence == 0.95
        assert "concluded" in reasoning.lower()

    def test_parse_zai_response_no_confidence(self, verifier):
        """Test Z.ai response parsing - missing confidence."""
        content = "The event is still ongoing."

        confidence, reasoning = verifier._parse_zai_response(content)

        assert confidence == 0.75  # Default
        assert reasoning == content
