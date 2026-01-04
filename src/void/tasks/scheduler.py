"""
Background task scheduler for VOID.

Runs periodic tasks like:
- Twitter data collection
- Sentiment analysis
- Knowledge archival
- Market research
"""

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from void.data.database import async_session_maker
from void.data.models import Market
from void.data.feeds.twitter_collector import TwitterCollector
from void.data.feeds.sentiment_analyzer import SentimentAnalyzer
from void.data.knowledge.service import KnowledgeService
from void.data.knowledge.storage import HybridStorage
from void.config import config
import structlog

logger = structlog.get_logger()


class TaskScheduler:
    """Background task scheduler for automated data collection."""

    def __init__(self):
        self.running = False
        self.tasks: list[asyncio.Task] = []

    async def start(self):
        """Start all background tasks."""
        if self.running:
            logger.warning("scheduler_already_running")
            return

        self.running = True
        logger.info("starting_scheduler")

        # Start background tasks
        self.tasks = [
            asyncio.create_task(self._twitter_collection_loop()),
            asyncio.create_task(self._sentiment_analysis_loop()),
            asyncio.create_task(self._knowledge_archival_loop()),
            asyncio.create_task(self._market_research_loop()),
        ]

        logger.info("scheduler_started", tasks_count=len(self.tasks))

    async def stop(self):
        """Stop all background tasks."""
        if not self.running:
            return

        logger.info("stopping_scheduler")
        self.running = False

        # Cancel all tasks
        for task in self.tasks:
            task.cancel()

        # Wait for tasks to finish
        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("scheduler_stopped")

    async def _twitter_collection_loop(self):
        """Periodically collect Twitter data for active markets."""
        interval_minutes = config.twitter.collection_interval_minutes
        logger.info("starting_twitter_collection_loop", interval_minutes=interval_minutes)

        while self.running:
            try:
                async with async_session_maker() as db:
                    # Get active markets (last 7 days)
                    cutoff = datetime.utcnow().timestamp() - (7 * 24 * 60 * 60)
                    result = await db.execute(
                        select(Market)
                        .where(Market.end_date_ts > cutoff)
                        .order_by(Market.volume.desc())
                        .limit(20)  # Top 20 markets by volume
                    )
                    markets = result.scalars().all()

                    if not markets:
                        logger.info("no_active_markets_for_twitter")
                        await asyncio.sleep(interval_minutes * 60)
                        continue

                    logger.info("collecting_twitter_data", markets_count=len(markets))

                    collector = TwitterCollector(db)
                    total_collected = 0

                    for market in markets:
                        try:
                            # Extract keywords from market question
                            keywords = self._extract_keywords(market.question)

                            collected = await collector.collect_for_market(
                                market.market_id,
                                keywords
                            )
                            total_collected += collected

                            # Small delay between markets
                            await asyncio.sleep(2)

                        except Exception as e:
                            logger.error(
                                "twitter_collection_error",
                                market_id=market.market_id,
                                error=str(e)
                            )

                    logger.info(
                        "twitter_collection_complete",
                        total_collected=total_collected,
                        markets_processed=len(markets)
                    )

            except Exception as e:
                logger.error("twitter_collection_loop_error", error=str(e), exc_info=True)

            # Sleep until next collection
            await asyncio.sleep(interval_minutes * 60)

    async def _sentiment_analysis_loop(self):
        """Periodically analyze sentiment for unanalyzed tweets."""
        interval_minutes = config.twitter.collection_interval_minutes
        logger.info("starting_sentiment_analysis_loop", interval_minutes=interval_minutes)

        while self.running:
            try:
                async with async_session_maker() as db:
                    analyzer = SentimentAnalyzer(db)

                    # Analyze up to 100 unanalyzed tweets
                    analyzed = await analyzer.batch_analyze_tweets(limit=100)

                    logger.info("sentiment_analysis_complete", analyzed_count=analyzed)

            except Exception as e:
                logger.error("sentiment_analysis_loop_error", error=str(e), exc_info=True)

            # Sleep until next analysis
            await asyncio.sleep(interval_minutes * 60)

    async def _knowledge_archival_loop(self):
        """Periodically archive old knowledge to R2."""
        interval_hours = 6  # Run every 6 hours
        logger.info("starting_knowledge_archival_loop", interval_hours=interval_hours)

        while self.running:
            try:
                async with async_session_maker() as db:
                    storage = HybridStorage(db)

                    # Archive knowledge older than retention period
                    archived = await storage.cleanup_knowledge()

                    # Enforce size limits
                    await storage._enforce_size_limits()

                    logger.info("knowledge_archival_complete", archived_count=archived)

            except Exception as e:
                logger.error("knowledge_archival_loop_error", error=str(e), exc_info=True)

            # Sleep until next archival
            await asyncio.sleep(interval_hours * 60 * 60)

    async def _market_research_loop(self):
        """Periodically research top markets."""
        interval_hours = 12  # Run every 12 hours
        logger.info("starting_market_research_loop", interval_hours=interval_hours)

        while self.running:
            try:
                async with async_session_maker() as db:
                    # Get top 5 markets by volume that haven't been researched in 24h
                    cutoff = datetime.utcnow().timestamp() - (24 * 60 * 60)
                    result = await db.execute(
                        select(Market)
                        .where(
                            (Market.end_date_ts > cutoff) &
                            ((Market.last_researched_at == None) |
                             (Market.last_researched_at < datetime.utcnow()))
                        )
                        .order_by(Market.volume.desc())
                        .limit(5)
                    )
                    markets = result.scalars().all()

                    if not markets:
                        logger.info("no_markets_requiring_research")
                        await asyncio.sleep(interval_hours * 60 * 60)
                        continue

                    logger.info("researching_markets", markets_count=len(markets))

                    knowledge_service = KnowledgeService(db)

                    for market in markets:
                        try:
                            await knowledge_service.research_market(
                                market.market_id,
                                force=True
                            )
                            logger.info("market_research_complete", market_id=market.market_id)

                            # Delay between markets to avoid rate limits
                            await asyncio.sleep(30)

                        except Exception as e:
                            logger.error(
                                "market_research_error",
                                market_id=market.market_id,
                                error=str(e)
                            )

            except Exception as e:
                logger.error("market_research_loop_error", error=str(e), exc_info=True)

            # Sleep until next research
            await asyncio.sleep(interval_hours * 60 * 60)

    def _extract_keywords(self, question: str) -> list[str]:
        """Extract keywords from market question for Twitter search."""
        # Simple keyword extraction - can be improved with NLP
        import re

        # Remove common words
        stop_words = {
            'will', 'the', 'a', 'an', 'is', 'are', 'by', 'before', 'after',
            'in', 'on', 'at', 'to', 'for', 'of', 'with', 'and', 'or', 'but'
        }

        # Extract words
        words = re.findall(r'\b\w+\b', question.lower())
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]

        # Return top 5 keywords
        return list(set(keywords))[:5]


# Global scheduler instance
_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
