"""
Sentiment analyzer service using Z.ai GLM-4.7.

Analyzes tweets, news, and text for market sentiment.
"""

from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from decimal import Decimal

from void.ai.llm_client import ZAIClient
from void.ai.prompt_templates import PromptTemplates
from void.data.models import TwitterData, MarketKnowledge, SentimentScore, Market
from void.config import config

import structlog

logger = structlog.get_logger()


class SentimentAnalyzer:
    """Analyze sentiment using LLM."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = ZAIClient()
        self.enabled = config.twitter.sentiment_enabled

    async def analyze_tweet(self, tweet: TwitterData) -> Optional[SentimentScore]:
        """
        Analyze sentiment of a tweet.

        Args:
            tweet: TwitterData object

        Returns:
            SentimentScore object or None
        """
        if not self.enabled:
            return None

        try:
            # Use specialized tweet sentiment prompt
            from void.ai.prompt_templates import PromptTemplates

            prompt = PromptTemplates.TWEET_SENTIMENT.format(
                tweet=tweet.content,
                author=tweet.author or "Unknown",
                followers=tweet.public_metrics.get("followers", 0) if tweet.public_metrics else 0,
                likes=tweet.public_metrics.get("likes", 0) if tweet.public_metrics else 0,
                retweets=tweet.public_metrics.get("retweets", 0) if tweet.public_metrics else 0,
                replies=tweet.public_metrics.get("replies", 0) if tweet.public_metrics else 0,
                timestamp=tweet.created_at.isoformat() if tweet.created_at else "Unknown",
            )

            messages = [
                {"role": "system", "content": "You are a precise sentiment analyst. Always respond with valid JSON."},
                {"role": "user", "content": prompt},
            ]

            response = await self.llm._call_api(messages, response_format="json")

            # Parse JSON response
            import json

            result = json.loads(response)

            # Create sentiment score
            sentiment = SentimentScore(
                entity_id=tweet.tweet_id,
                entity_type="tweet",
                score=Decimal(str(result.get("score", 0))),
                confidence=Decimal(str(result.get("confidence", 0))),
                metadata={
                    "market_relevance": result.get("market_relevance", 0),
                    "key_insight": result.get("key_insight", "")[:200],  # Truncate
                }
            )

            # Update tweet with sentiment
            tweet.sentiment_score = sentiment.score

            await self.db.commit()

            logger.debug(
                "tweet_sentiment_analyzed",
                tweet_id=tweet.tweet_id,
                score=float(sentiment.score),
                confidence=float(sentiment.confidence),
            )

            return sentiment

        except Exception as e:
            logger.error(
                "tweet_sentiment_error",
                tweet_id=tweet.tweet_id,
                error=str(e),
            )
            return None

    async def analyze_market_sentiment(
        self,
        market_id: str,
    ) -> Dict[str, float]:
        """
        Calculate aggregate sentiment for a market.

        Args:
            market_id: Polymarket market ID

        Returns:
            Dict with sentiment metrics
        """
        # Get all sentiment scores for this market's tweets
        result = await self.db.execute(
            select(SentimentScore)
            .join(TwitterData, TwitterData.tweet_id == SentimentScore.entity_id)
            .where(
                TwitterData.market_id == market_id,
                SentimentScore.entity_type == "tweet",
            )
        )
        sentiments = result.scalars().all()

        if not sentiments:
            return {
                "avg_score": 0.0,
                "tweet_count": 0,
                "confidence": 0.0,
            }

        # Calculate weighted average (by confidence)
        total_weight = 0
        weighted_sum = 0

        for s in sentiments:
            weight = float(s.confidence or 0.5)
            weighted_sum += float(s.score) * weight
            total_weight += weight

        avg_score = weighted_sum / total_weight if total_weight > 0 else 0
        avg_confidence = sum(float(s.confidence or 0) for s in sentiments) / len(sentiments)

        # Update market's sentiment score
        await self.db.execute(
            update(Market)
            .where(Market.id == market_id)
            .values(sentiment_score=round(avg_score, 4))
        )
        await self.db.commit()

        return {
            "avg_score": round(avg_score, 4),
            "tweet_count": len(sentiments),
            "confidence": round(avg_confidence, 4),
        }

    async def analyze_text(
        self,
        text: str,
        entity_id: str,
        entity_type: str = "text",
    ) -> Optional[Dict]:
        """
        Analyze sentiment of arbitrary text.

        Args:
            text: Text to analyze
            entity_id: ID for this entity
            entity_type: Type of entity

        Returns:
            Sentiment analysis result
        """
        try:
            result = await self.llm.analyze_sentiment(text, entity_type)

            # Store in DB if high confidence
            if result.get("confidence", 0) > 0.7:
                sentiment = SentimentScore(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    score=Decimal(str(result.get("score", 0))),
                    confidence=Decimal(str(result.get("confidence", 0))),
                    metadata={
                        "key_points": result.get("key_points", [])[:5],  # Limit to 5 points
                    }
                )

                self.db.add(sentiment)
                await self.db.commit()

            return result

        except Exception as e:
            logger.error(
                "text_sentiment_error",
                entity_id=entity_id,
                error=str(e),
            )
            return None

    async def batch_analyze_tweets(
        self,
        limit: int = 100,
    ) -> int:
        """
        Analyze sentiment for tweets that haven't been analyzed.

        Args:
            limit: Max tweets to analyze

        Returns:
            Number of tweets analyzed
        """
        # Get tweets without sentiment
        result = await self.db.execute(
            select(TwitterData)
            .where(TwitterData.sentiment_score.is_(None))
            .order_by(TwitterData.collected_at.desc())
            .limit(limit)
        )
        tweets = result.scalars().all()

        analyzed_count = 0

        for tweet in tweets:
            try:
                await self.analyze_tweet(tweet)
                analyzed_count += 1

                # Rate limiting: small delay between API calls
                import asyncio
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.warning(
                    "batch_analysis_failed",
                    tweet_id=tweet.tweet_id,
                    error=str(e),
                )
                continue

        logger.info(
            "batch_sentiment_complete",
            analyzed=analyzed_count,
            total_queued=len(tweets),
        )

        return analyzed_count


__all__ = ["SentimentAnalyzer"]
