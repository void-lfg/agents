"""
Twitter data collector for VOID.

Collects tweets for markets, analyzes sentiment, and stores to DB.
Aggressively optimized to stay under 300MB DB limit.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from void.data.feeds.twitter_client import TwitterClient
from void.data.models import Market, TwitterData, SentimentScore
from void.config import config

import structlog

logger = structlog.get_logger()


class TwitterCollector:
    """Collect and store Twitter data with size optimization."""

    # SIZE LIMITS (to stay under 300MB for entire DB)
    MAX_TWEETS_PER_MARKET = 100  # Keep only recent 100 tweets per market
    MAX_TWEET_AGE_DAYS = 7  # Auto-delete tweets older than 7 days
    MAX_TOTAL_TWEETS = 10000  # Hard limit on total tweets in DB

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = TwitterClient()
        self.enabled = config.twitter.sentiment_enabled

    async def collect_for_market(
        self,
        market_id: str,
        keywords: List[str],
    ) -> int:
        """
        Collect tweets for a specific market.

        Args:
            market_id: Polymarket market ID
            keywords: Market-relevant keywords

        Returns:
            Number of tweets collected
        """
        if not self.enabled:
            logger.debug("twitter_collection_disabled")
            return 0

        try:
            # Check if we're at the limit
            count_result = await self.db.execute(
                select(func.count(TwitterData.id))
            )
            total_tweets = count_result.scalar() or 0

            if total_tweets >= self.MAX_TOTAL_TWEETS:
                logger.warning(
                    "twitter_db_limit_reached",
                    total=total_tweets,
                    limit=self.MAX_TOTAL_TWEETS,
                )
                await self._cleanup_old_tweets()
                return 0

            # Get market info
            market = await self.db.get(Market, market_id)
            if not market:
                logger.warning("market_not_found", market_id=market_id)
                return 0

            # Search tweets
            tweets = await self.client.search_market_tweets(
                market_question=market.question,
                keywords=keywords,
                max_results=config.twitter.search_max_results,
            )

            collected_count = 0

            for tweet_data in tweets:
                try:
                    # Skip if already exists
                    tweet_id = tweet_data.get("id")
                    existing = await self.db.execute(
                        select(TwitterData).where(TwitterData.tweet_id == tweet_id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # Extract author info
                    author_data = tweet_data.get("author_data", {})
                    author_name = author_data.get("name", "Unknown")[:50]  # Truncate
                    author_id = author_data.get("id", "")

                    # Truncate content to save space (max 280 chars anyway, but ensure)
                    content = tweet_data.get("text", "")[:500]

                    # Parse timestamp
                    created_at_str = tweet_data.get("created_at")
                    created_at = None
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(
                                created_at_str.replace("Z", "+00:00")
                            )
                        except:
                            pass

                    # Create tweet record (MINIMAL FIELDS to save space)
                    tweet = TwitterData(
                        tweet_id=tweet_id,
                        content=content,
                        author=author_name,
                        author_id=author_id,
                        created_at=created_at,
                        market_id=market_id,
                        # Don't store full metrics, just essential
                        public_metrics={
                            "likes": tweet_data.get("public_metrics", {}).get("like_count", 0),
                            "retweets": tweet_data.get("public_metrics", {}).get("retweet_count", 0),
                        } if tweet_data.get("public_metrics") else None,
                        # Minimal metadata
                        metadata={
                            "source": tweet_data.get("source", "")[:50],  # Truncate source
                        }
                    )

                    self.db.add(tweet)
                    collected_count += 1

                except Exception as e:
                    logger.warning(
                        "tweet_store_error",
                        tweet_id=tweet_data.get("id"),
                        error=str(e),
                    )
                    continue

            await self.db.commit()

            logger.info(
                "twitter_collection_complete",
                market_id=market_id,
                collected=collected_count,
                total_tweets=total_tweets + collected_count,
            )

            # Cleanup old tweets for this market
            await self._cleanup_market_tweets(market_id)

            return collected_count

        except Exception as e:
            logger.error(
                "twitter_collection_error",
                market_id=market_id,
                error=str(e),
                exc_info=True,
            )
            return 0

    async def collect_for_all_active_markets(self) -> Dict[str, int]:
        """
        Collect tweets for all active markets.

        Returns:
            Dict mapping market_id to tweets collected
        """
        results = {}

        # Get active markets (limit to 20 to avoid rate limits)
        markets_result = await self.db.execute(
            select(Market)
            .where(Market.status == "active")
            .order_by(Market.liquidity.desc())
            .limit(20)
        )
        markets = markets_result.scalars().all()

        logger.info(
            "twitter_collection_started",
            active_markets=len(markets),
        )

        for market in markets:
            # Extract keywords from market question/tags
            keywords = self._extract_keywords(market)

            try:
                count = await self.collect_for_market(
                    market_id=market.id,
                    keywords=keywords,
                )

                if count > 0:
                    results[market.id] = count

                # Rate limiting: sleep between requests
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(
                    "market_collection_failed",
                    market_id=market.id,
                    error=str(e),
                )
                continue

        logger.info(
            "twitter_collection_finished",
            markets_processed=len(results),
            total_tweets=sum(results.values()),
        )

        return results

    def _extract_keywords(self, market: Market) -> List[str]:
        """
        Extract search keywords from market.

        Args:
            market: Market object

        Returns:
            List of keywords
        """
        keywords = []

        # Add tags
        if market.tags:
            keywords.extend(market.tags[:5])  # Limit to 5 tags

        # Add category
        if market.category:
            keywords.append(market.category)

        # Extract key terms from question
        question_words = market.question.lower().split()
        important_words = [
            w for w in question_words
            if len(w) > 4 and w not in ["will", "what", "when", "market", "price"]
        ]
        keywords.extend(important_words[:3])  # Top 3 important words

        # Remove duplicates and limit
        return list(set(keywords))[:10]

    async def _cleanup_market_tweets(self, market_id: str) -> None:
        """
        Cleanup old/extra tweets for a market to save space.

        Keeps only the most recent MAX_TWEETS_PER_MARKET tweets.
        """
        # Count tweets for this market
        count_result = await self.db.execute(
            select(func.count(TwitterData.id))
            .where(TwitterData.market_id == market_id)
        )
        count = count_result.scalar() or 0

        if count > self.MAX_TWEETS_PER_MARKET:
            # Get oldest tweets beyond limit
            old_tweets_result = await self.db.execute(
                select(TwitterData)
                .where(TwitterData.market_id == market_id)
                .order_by(TwitterData.collected_at.asc())
                .limit(count - self.MAX_TWEETS_PER_MARKET)
            )
            old_tweets = old_tweets_result.scalars().all()

            # Delete them
            for tweet in old_tweets:
                await self.db.delete(tweet)

            await self.db.commit()

            logger.info(
                "cleaned_up_market_tweets",
                market_id=market_id,
                deleted=len(old_tweets),
            )

    async def _cleanup_old_tweets(self) -> None:
        """
        Cleanup tweets older than MAX_TWEET_AGE_DAYS globally.
        Called when approaching DB size limit.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.MAX_TWEET_AGE_DAYS)

        result = await self.db.execute(
            delete(TwitterData)
            .where(TwitterData.created_at < cutoff)
        )

        deleted_count = result.rowcount
        await self.db.commit()

        if deleted_count > 0:
            logger.info(
                "cleaned_up_old_tweets",
                deleted=deleted_count,
                cutoff_days=self.MAX_TWEET_AGE_DAYS,
            )

    async def get_collection_stats(self) -> Dict[str, any]:
        """
        Get collection statistics.

        Returns:
            Dict with stats
        """
        # Total tweets
        total_result = await self.db.execute(
            select(func.count(TwitterData.id))
        )
        total_tweets = total_result.scalar() or 0

        # Tweets by market
        by_market_result = await self.db.execute(
            select(
                TwitterData.market_id,
                func.count(TwitterData.id).label('count')
            )
            .group_by(TwitterData.market_id)
            .order_by(func.count(TwitterData.id).desc())
            .limit(10)
        )
        top_markets = {row.market_id: row.count for row in by_market_result.all()}

        # DB size estimate (rough calculation)
        # Avg tweet ~500 bytes
        estimated_size_bytes = total_tweets * 500
        estimated_size_mb = round(estimated_size_bytes / (1024 * 1024), 2)

        return {
            "total_tweets": total_tweets,
            "top_markets": top_markets,
            "estimated_size_mb": estimated_size_mb,
            "max_tweets": self.MAX_TOTAL_TWEETS,
            "usage_percent": round((total_tweets / self.MAX_TOTAL_TWEETS) * 100, 1),
        }


__all__ = ["TwitterCollector"]
