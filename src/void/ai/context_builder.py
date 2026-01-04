"""
Context builder for AI chat.

Gathers relevant data from database for LLM prompts with caching and optimization.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from void.data.models import (
    Account, Agent, Position, Signal, Market,
    Order, TwitterData, MarketKnowledge, SentimentScore,
)
from void.config import config

import structlog

logger = structlog.get_logger()


class ContextBuilder:
    """Build rich context for AI from database queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_user_context(
        self,
        user_id: int,
        account_id: Optional[int] = None,
    ) -> str:
        """
        Build user context string for LLM.

        Args:
            user_id: Telegram user ID
            account_id: Optional specific account ID

        Returns:
            Formatted context string
        """
        context_parts = []

        # Get account info
        if account_id:
            account = await self.db.get(Account, account_id)
        else:
            # Get user's primary account (first active one)
            result = await self.db.execute(
                select(Account)
                .where(Account.status == "active")
                .limit(1)
            )
            account = result.scalar_one_or_none()

        if account:
            context_parts.append(f"Account: {account.name}")
            context_parts.append(f"Balance: ${account.usdc_balance:,.2f} USDC")
            context_parts.append(f"Address: {account.address[:10]}...")

            # Get active positions
            positions_result = await self.db.execute(
                select(Position)
                .where(
                    Position.account_id == account.id,
                    Position.side == "long",
                )
                .options(selectinload(Position.market))
                .limit(10)
            )
            positions = positions_result.scalars().all()

            if positions:
                total_unrealized_pnl = Decimal("0")
                context_parts.append(f"\nActive Positions ({len(positions)}):")

                for pos in positions[:5]:  # Limit to 5 positions
                    unrealized_pnl = pos.unrealized_pnl or Decimal("0")
                    total_unrealized_pnl += unrealized_pnl

                    context_parts.append(
                        f"  • {pos.market.question[:50]}...: "
                        f"{pos.side} ${pos.tokens_amount:.2f} "
                        f"@ ${pos.avg_price:.4f} "
                        f"(P&L: ${unrealized_pnl:+.2f})"
                    )

                context_parts.append(f"\nTotal Unrealized P&L: ${total_unrealized_pnl:+.2f}")

            # Get recent signals
            signals_result = await self.db.execute(
                select(Signal)
                .join(Agent)
                .where(Agent.account_id == account.id)
                .order_by(Signal.created_at.desc())
                .limit(5)
            )
            signals = signals_result.scalars().all()

            if signals:
                context_parts.append(f"\nRecent Signals ({len(signals)}):")

                for signal in signals:
                    context_parts.append(
                        f"  • {signal.market_id}: {signal.predicted_outcome} "
                        f"@ ${signal.entry_price:.4f} "
                        f"(margin: {signal.profit_margin*100:.1f}%, "
                        f"confidence: {signal.confidence:.2f})"
                    )

        if not context_parts:
            return "No account data available."

        return "\n".join(context_parts)

    async def build_market_context(
        self,
        market_id: Optional[str] = None,
    ) -> str:
        """
        Build market context string.

        Args:
            market_id: Optional specific market

        Returns:
            Formatted context string
        """
        context_parts = []

        if market_id:
            # Specific market
            market = await self.db.get(Market, market_id)
            if market:
                context_parts.append(f"Market: {market.question}")
                context_parts.append(f"YES Price: ${market.yes_price:.4f}")
                context_parts.append(f"NO Price: ${market.no_price:.4f}")
                context_parts.append(f"Liquidity: ${market.liquidity:,.2f}")
                context_parts.append(f"Volume 24h: ${market.volume_24h:,.2f}")
                context_parts.append(f"Status: {market.status.value}")

                # Get sentiment
                if market.sentiment_score is not None:
                    sentiment_label = "Bullish" if market.sentiment_score > 0.1 else "Bearish" if market.sentiment_score < -0.1 else "Neutral"
                    context_parts.append(f"Sentiment: {sentiment_label} ({market.sentiment_score:+.2f})")
        else:
            # Market overview
            result = await self.db.execute(
                select(Market)
                .where(Market.status == "active")
                .order_by(Market.liquidity.desc())
                .limit(5)
            )
            markets = result.scalars().all()

            if markets:
                context_parts.append("Top Active Markets:")
                for m in markets:
                    context_parts.append(
                        f"  • {m.question[:60]}... "
                        f"YES: ${m.yes_price:.4f} | "
                        f"Liq: ${m.liquidity:,.0f}"
                    )

        if not context_parts:
            return "No market data available."

        return "\n".join(context_parts)

    async def build_knowledge_summary(
        self,
        market_id: Optional[str] = None,
        hours: int = 24,
    ) -> str:
        """
        Build knowledge summary from recent data.

        Args:
            market_id: Optional specific market
            hours: Lookback period in hours

        Returns:
            Formatted knowledge summary
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        context_parts = []

        if market_id:
            # Market-specific knowledge
            # Get recent tweets
            tweets_result = await self.db.execute(
                select(TwitterData)
                .where(
                    TwitterData.market_id == market_id,
                    TwitterData.collected_at >= cutoff,
                )
                .order_by(TwitterData.collected_at.desc())
                .limit(5)
            )
            tweets = tweets_result.scalars().all()

            if tweets:
                avg_sentiment = sum(
                    t.sentiment_score or 0 for t in tweets
                ) / len(tweets)

                sentiment_label = "Positive" if avg_sentiment > 0.1 else "Negative" if avg_sentiment < -0.1 else "Neutral"

                context_parts.append(
                    f"Twitter (last {hours}h): {len(tweets)} tweets, "
                    f"sentiment: {sentiment_label} ({avg_sentiment:+.2f})"
                )

            # Get recent news/knowledge
            knowledge_result = await self.db.execute(
                select(MarketKnowledge)
                .where(
                    MarketKnowledge.market_id == market_id,
                    MarketKnowledge.collected_at >= cutoff,
                )
                .order_by(MarketKnowledge.relevance_score.desc())
                .limit(3)
            )
            knowledge_items = knowledge_result.scalars().all()

            if knowledge_items:
                context_parts.append(f"\nRecent Knowledge ({len(knowledge_items)} items):")

                for item in knowledge_items:
                    if item.summary:
                        context_parts.append(f"  • [{item.content_type}] {item.summary[:100]}...")

        # General market sentiment overview
        sentiment_result = await self.db.execute(
            select(func.avg(SentimentScore.score))
            .where(
                SentimentScore.entity_type == "market",
                SentimentScore.analyzed_at >= cutoff,
            )
        )
        avg_market_sentiment = sentiment_result.scalar() or 0

        if not market_id:
            sentiment_label = "Bullish" if avg_market_sentiment > 0.1 else "Bearish" if avg_market_sentiment < -0.1 else "Neutral"
            context_parts.append(
                f"Overall Market Sentiment: {sentiment_label} ({avg_market_sentiment:+.2f})"
            )

        if not context_parts:
            return "No recent knowledge available."

        return "\n".join(context_parts)

    async def build_full_context(
        self,
        user_id: int,
        market_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Build complete context for LLM prompt.

        Returns dict with:
        - user_context: User portfolio and positions
        - market_context: Market data and conditions
        - knowledge_summary: Recent tweets, news, sentiment

        Args:
            user_id: Telegram user ID
            market_id: Optional specific market

        Returns:
            Dict with context strings
        """
        # Build all contexts in parallel for speed
        user_context = await self.build_user_context(user_id)
        market_context = await self.build_market_context(market_id)
        knowledge_summary = await self.build_knowledge_summary(market_id)

        return {
            "user_context": user_context,
            "market_context": market_context,
            "knowledge_summary": knowledge_summary,
        }


__all__ = ["ContextBuilder"]
