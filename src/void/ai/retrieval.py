"""
Vector similarity search using pgvector.

Retrieves relevant knowledge and tweets using semantic search.
"""

from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from sqlalchemy.sql import select

from void.data.models import MarketKnowledge, TwitterData
from void.ai.embeddings import get_embedding_service
import structlog

logger = structlog.get_logger()


class VectorRetrieval:
    """Service for vector similarity search using pgvector."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = get_embedding_service()

    async def search_knowledge(
        self,
        query: str,
        market_id: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Tuple[MarketKnowledge, float]]:
        """
        Search knowledge base semantically.

        Args:
            query: Search query
            market_id: Optional market ID to filter by
            limit: Maximum number of results
            threshold: Minimum similarity score (0-1)

        Returns:
            List of (knowledge_entry, similarity_score) tuples
        """
        try:
            # Create embedding for query
            query_embedding = await self.embedding_service.create_embedding(query)
            if not query_embedding:
                logger.warning("failed_to_create_query_embedding")
                return []

            # Build SQL query with pgvector cosine similarity
            # Using raw SQL for pgvector-specific operations
            embedding_array = f"[{','.join(map(str, query_embedding))}]"

            base_query = f"""
                SELECT
                    id,
                    market_id,
                    content_type,
                    title,
                    summary,
                    collected_at,
                    1 - (embedding <=> '{embedding_array}'::vector) as similarity
                FROM market_knowledge
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> '{embedding_array}'::vector) >= {threshold}
            """

            if market_id:
                base_query += f" AND market_id = '{market_id}'"

            base_query += f"""
                ORDER BY similarity DESC
                LIMIT {limit}
            """

            result = await self.db.execute(text(base_query))
            rows = result.fetchall()

            # Convert to knowledge objects
            knowledge_entries = []
            for row in rows:
                # Fetch full knowledge object
                knowledge = await self.db.get(MarketKnowledge, row[0])
                if knowledge:
                    knowledge_entries.append((knowledge, float(row[7])))  # similarity is column 8

            logger.info(
                "knowledge_search_complete",
                query_length=len(query),
                results_count=len(knowledge_entries)
            )

            return knowledge_entries

        except Exception as e:
            logger.error("knowledge_search_error", error=str(e), exc_info=True)
            return []

    async def search_tweets(
        self,
        query: str,
        market_id: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.6
    ) -> List[Tuple[TwitterData, float]]:
        """
        Search tweets semantically.

        Args:
            query: Search query
            market_id: Optional market ID to filter by
            limit: Maximum number of results
            threshold: Minimum similarity score (0-1)

        Returns:
            List of (tweet, similarity_score) tuples
        """
        try:
            # Create embedding for query
            query_embedding = await self.embedding_service.create_embedding(query)
            if not query_embedding:
                logger.warning("failed_to_create_query_embedding")
                return []

            # Build SQL query with pgvector cosine similarity
            embedding_array = f"[{','.join(map(str, query_embedding))}]"

            base_query = f"""
                SELECT
                    id,
                    tweet_id,
                    content,
                    author,
                    sentiment_score,
                    collected_at,
                    1 - (embedding <=> '{embedding_array}'::vector) as similarity
                FROM twitter_data
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> '{embedding_array}'::vector) >= {threshold}
            """

            if market_id:
                base_query += f" AND market_id = '{market_id}'"

            base_query += f"""
                ORDER BY similarity DESC
                LIMIT {limit}
            """

            result = await self.db.execute(text(base_query))
            rows = result.fetchall()

            # Convert to tweet objects
            tweets = []
            for row in rows:
                # Fetch full tweet object
                tweet = await self.db.get(TwitterData, row[0])
                if tweet:
                    tweets.append((tweet, float(row[6])))  # similarity is column 7

            logger.info(
                "tweet_search_complete",
                query_length=len(query),
                results_count=len(tweets)
            )

            return tweets

        except Exception as e:
            logger.error("tweet_search_error", error=str(e), exc_info=True)
            return []

    async def search_all(
        self,
        query: str,
        market_id: Optional[str] = None,
        limit_per_type: int = 5
    ) -> dict:
        """
        Search both knowledge and tweets.

        Args:
            query: Search query
            market_id: Optional market ID to filter by
            limit_per_type: Max results per type

        Returns:
            Dict with 'knowledge' and 'tweets' keys
        """
        knowledge = await self.search_knowledge(
            query,
            market_id=market_id,
            limit=limit_per_type
        )

        tweets = await self.search_tweets(
            query,
            market_id=market_id,
            limit=limit_per_type
        )

        return {
            'knowledge': knowledge,
            'tweets': tweets
        }
