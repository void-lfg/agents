"""
Knowledge service orchestrator for VOID.

Coordinates knowledge collection, storage, and retrieval.
"""

from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from void.data.knowledge.storage import HybridStorage
from void.data.feeds.twitter_collector import TwitterCollector
from void.data.feeds.sentiment_analyzer import SentimentAnalyzer
from void.ai.llm_client import ZAIClient
from void.ai.prompt_templates import PromptTemplates
from void.data.models import Market, TwitterData, SentimentScore
from void.config import config

import structlog

logger = structlog.get_logger()


class KnowledgeService:
    """Orchestrate knowledge collection and management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = HybridStorage(db)
        self.twitter_collector = TwitterCollector(db)
        self.sentiment_analyzer = SentimentAnalyzer(db)
        self.llm = ZAIClient()

    async def research_market(
        self,
        market_id: str,
        force: bool = False,
    ) -> Dict[str, any]:
        """
        Perform comprehensive research on a market.

        Args:
            market_id: Polymarket market ID
            force: Force re-research even if recently done

        Returns:
            Research results summary
        """
        # Check if recently researched
        market = await self.db.get(Market, market_id)
        if not market:
            logger.warning("market_not_found", market_id=market_id)
            return {"error": "Market not found"}

        if market.last_researched_at:
            hours_since = (datetime.utcnow() - market.last_researched_at).total_seconds() / 3600
            if hours_since < 6 and not force:
                logger.info(
                    "market_recently_researched",
                    market_id=market_id,
                    hours_since=round(hours_since, 1),
                )
                return {
                    "status": "skipped",
                    "reason": "Recently researched",
                    "last_researched": market.last_researched_at.isoformat(),
                }

        logger.info("market_research_started", market_id=market_id)

        results = {
            "market_id": market_id,
            "started_at": datetime.utcnow().isoformat(),
            "tweets_collected": 0,
            "knowledge_created": 0,
        }

        # Step 1: Collect tweets
        keywords = self._extract_keywords(market)
        tweets_collected = await self.twitter_collector.collect_for_market(
            market_id=market_id,
            keywords=keywords,
        )
        results["tweets_collected"] = tweets_collected

        # Step 2: Analyze sentiment
        sentiment_result = await self.sentiment_analyzer.analyze_market_sentiment(
            market_id=market_id
        )
        results["sentiment"] = sentiment_result

        # Step 3: Generate knowledge summary using LLM
        if tweets_collected > 0:
            await self._generate_market_knowledge(market, keywords)

        # Step 4: Update market
        market.last_researched_at = datetime.utcnow()
        await self.db.commit()

        logger.info(
            "market_research_complete",
            market_id=market_id,
            results=results,
        )

        return results

    def _extract_keywords(self, market: Market) -> List[str]:
        """Extract search keywords from market."""
        keywords = []

        if market.tags:
            keywords.extend(market.tags[:5])

        if market.category:
            keywords.append(market.category)

        # Add words from question
        question_words = [
            w.lower() for w in market.question.split()
            if len(w) > 4
        ]
        keywords.extend(question_words[:5])

        return list(set(keywords))[:10]

    async def _generate_market_knowledge(
        self,
        market: Market,
        keywords: List[str],
    ) -> None:
        """Generate and store AI-generated knowledge summary."""

        try:
            # Get recent tweets for this market
            result = await self.db.execute(
                select(TwitterData)
                .where(TwitterData.market_id == market.id)
                .order_by(TwitterData.collected_at.desc())
                .limit(20)
            )
            tweets = result.scalars().all()

            if not tweets:
                return

            # Format tweets for LLM
            tweets_text = "\n\n".join([
                f"@{t.author}: {t.content}"
                for t in tweets[:10]
            ])

            # Generate summary using LLM
            summary = await self.llm.generate_response(
                template=PromptTemplates.SUMMARIZE_TWEETS,
                market_id=market.id,
                count=len(tweets),
                tweets=tweets_text,
            )

            # Store as knowledge
            await self.storage.store_knowledge(
                market_id=market.id,
                content_type="analysis",
                content=summary,
                title=f"Twitter Summary for {market.question[:50]}",
                summary=summary[:500],  # Brief summary
                metadata={
                    "tweets_analyzed": len(tweets),
                    "keywords": keywords[:5],
                    "generated_at": datetime.utcnow().isoformat(),
                }
            )

            logger.info(
                "market_knowledge_generated",
                market_id=market.id,
                tweets_analyzed=len(tweets),
            )

        except Exception as e:
            logger.error(
                "knowledge_generation_error",
                market_id=market.id,
                error=str(e),
            )

    async def get_market_knowledge(
        self,
        market_id: str,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get all knowledge for a market.

        Args:
            market_id: Market ID
            limit: Max entries

        Returns:
            Knowledge entries
        """
        return await self.storage.get_knowledge(
            market_id=market_id,
            limit=limit,
        )

    async def get_knowledge_summary(
        self,
        market_id: str,
    ) -> str:
        """
        Get human-readable knowledge summary.

        Args:
            market_id: Market ID

        Returns:
            Formatted summary string
        """
        entries = await self.get_market_knowledge(market_id)

        if not entries:
            return "No knowledge available for this market."

        summary_parts = [
            f"Knowledge Base for Market {market_id}:",
            f"Total Entries: {len(entries)}\n",
        ]

        for entry in entries[:5]:  # Top 5
            summary_parts.append(
                f"• [{entry['content_type']}] {entry.get('title', 'No title')[:60]}"
            )
            if entry.get('summary'):
                summary_parts.append(f"  {entry['summary'][:150]}...")

        return "\n".join(summary_parts)

    async def cleanup_knowledge(self) -> Dict[str, int]:
        """
        Cleanup old knowledge across all markets.

        Returns:
            Cleanup statistics
        """
        stats = await self.storage.get_storage_stats()

        archived = await self.storage._archive_old_entries()
        oldest_archived = await self.storage._archive_oldest_entries(
            num_to_archive=50  # Archive oldest 50
        )

        total_archived = archived + oldest_archived

        logger.info(
            "knowledge_cleanup_complete",
            total_archived=total_archived,
        )

        return {
            "total_archived": total_archived,
            "storage_stats": stats,
        }


__all__ = ["KnowledgeService"]
