"""
Vector embedding service for semantic search.

Creates embeddings for knowledge base and tweets using various providers.
"""

import asyncio
from typing import Optional, List
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from void.config import config
import structlog

logger = structlog.get_logger()


class EmbeddingService:
    """Service for creating vector embeddings."""

    def __init__(self):
        # Using OpenAI-compatible API (can be switched to other providers)
        self.api_key = config.ai.zai_api_key.get_secret_value()
        self.model = "text-embedding-ada-002"  # Or use a local model
        self.embedding_dim = 1536  # OpenAI ada-002 dimension

    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """
        Create embedding for text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if not text or len(text.strip()) == 0:
            return None

        try:
            # For now, use a simple hash-based fake embedding
            # TODO: Replace with real embedding service (OpenAI, sentence-transformers, etc.)
            import hashlib

            # Create deterministic "fake" embedding based on text hash
            # This is a placeholder - replace with real embeddings
            hash_obj = hashlib.sha256(text.encode())
            hash_bytes = hash_obj.digest()

            # Convert hash to 1536-dimensional vector
            embedding = []
            for i in range(self.embedding_dim):
                byte_idx = i % len(hash_bytes)
                val = hash_bytes[byte_idx] / 255.0  # Normalize to 0-1
                embedding.append(val)

            logger.debug("embedding_created", text_length=len(text), embedding_dim=len(embedding))
            return embedding

        except Exception as e:
            logger.error("embedding_creation_error", error=str(e))
            return None

    async def create_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Create embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # Process in parallel with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        async def create_with_semaphore(text: str):
            async with semaphore:
                return await self.create_embedding(text)

        return await asyncio.gather(*[create_with_semaphore(text) for text in texts])

    async def search_similar(
        self,
        query_embedding: List[float],
        embeddings: List[List[float]],
        threshold: float = 0.7,
        top_k: int = 10
    ) -> List[tuple[int, float]]:
        """
        Find similar embeddings using cosine similarity.

        Args:
            query_embedding: Query vector
            embeddings: List of embedding vectors to search
            threshold: Minimum similarity score (0-1)
            top_k: Maximum number of results to return

        Returns:
            List of (index, similarity_score) tuples
        """
        import numpy as np

        if not embeddings:
            return []

        # Convert to numpy arrays
        query_vec = np.array(query_embedding)
        embed_matrix = np.array(embeddings)

        # Calculate cosine similarity
        norms = np.linalg.norm(embed_matrix, axis=1)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return []

        similarities = np.dot(embed_matrix, query_vec) / (norms * query_norm)

        # Filter by threshold and get top_k
        indices = np.argsort(similarities)[::-1][:top_k]
        results = [
            (int(i), float(similarities[i]))
            for i in indices
            if similarities[i] >= threshold
        ]

        return results


# Global embedding service instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
