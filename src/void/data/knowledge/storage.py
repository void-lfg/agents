"""
Hybrid storage service: PostgreSQL (hot) + Cloudflare R2 (cold).

Aggressively manages size to stay under 300MB DB limit.
"""

import json
import gzip
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

import boto3
from botocore.exceptions import ClientError

from void.data.models import MarketKnowledge
from void.config import config

import structlog

logger = structlog.get_logger()


class HybridStorage:
    """
    Manage hybrid storage with aggressive size limits.

    Hot Storage (PostgreSQL):
    - Max 500 entries total (~50MB)
    - Keep only last 7 days
    - Max 50KB per entry
    - Auto-archive when full

    Cold Storage (Cloudflare R2):
    - Unlimited capacity
    - Compressed JSON
    - Retrieved on demand
    """

    # SIZE LIMITS (to keep under 300MB total DB)
    MAX_KNOWLEDGE_ENTRIES = 500  # Total entries in hot storage
    MAX_ENTRY_SIZE_BYTES = 50 * 1024  # 50KB per entry
    MAX_AGE_DAYS = 7  # Auto-archive after 7 days
    DB_SIZE_TARGET_MB = 100  # Target size for knowledge table

    def __init__(self, db: AsyncSession):
        self.db = db
        self.r2_config = config.r2

        # Initialize S3 client for R2
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.r2_config.endpoint,
            aws_access_key_id=self.r2_config.access_key_id,
            aws_secret_access_key=self.r2_config.secret_access_key.get_secret_value(),
            region_name='auto',
        )

        self.bucket = self.r2_config.bucket_name
        self.knowledge_path = self.r2_config.knowledge_base_path

    async def store_knowledge(
        self,
        market_id: str,
        content_type: str,
        content: str,
        source_url: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[MarketKnowledge]:
        """
        Store knowledge entry with automatic archival if needed.

        Args:
            market_id: Market ID
            content_type: Type (twitter, news, analysis)
            content: Full content
            source_url: Source URL
            title: Title
            summary: Summary (truncated if needed)
            metadata: Additional metadata

        Returns:
            MarketKnowledge object or None
        """
        try:
            # Check size limits BEFORE storing
            await self._enforce_size_limits()

            # Truncate content if too large
            content_bytes = content.encode('utf-8')
            if len(content_bytes) > self.MAX_ENTRY_SIZE_BYTES:
                # Store only summary and metadata in DB
                summary = summary or content[:500]  # First 500 chars
                content_to_store = None
                should_archive = True
            else:
                content_to_store = content
                should_archive = False

            # Create knowledge entry
            knowledge = MarketKnowledge(
                market_id=market_id,
                content_type=content_type,
                source_url=source_url[:500] if source_url else None,  # Truncate URL
                title=title[:500] if title else None,
                summary=summary[:1000] if summary else None,  # Truncate summary
                content=content_to_store,
                metadata=metadata or {},
            )

            self.db.add(knowledge)
            await self.db.commit()
            await self.db.refresh(knowledge)

            # If content is large, archive immediately to R2
            if should_archive:
                r2_url = await self._archive_to_r2(knowledge.id, content)
                knowledge.r2_url = r2_url
                await self.db.commit()

                logger.debug(
                    "knowledge_archived_immediately",
                    knowledge_id=str(knowledge.id),
                    size_bytes=len(content_bytes),
                )

            return knowledge

        except Exception as e:
            logger.error(
                "store_knowledge_error",
                market_id=market_id,
                error=str(e),
                exc_info=True,
            )
            return None

    async def _archive_to_r2(
        self,
        knowledge_id: str,
        content: str,
    ) -> Optional[str]:
        """
        Archive content to Cloudflare R2.

        Args:
            knowledge_id: Knowledge entry ID
            content: Content to archive

        Returns:
            R2 URL or None
        """
        try:
            # Compress content
            content_bytes = content.encode('utf-8')
            compressed = gzip.compress(content_bytes)

            logger.debug(
                "r2_upload_start",
                knowledge_id=str(knowledge_id),
                original_size=len(content_bytes),
                compressed_size=len(compressed),
                compression_ratio=f"{len(compressed)/len(content_bytes):.2%}",
            )

            # Upload to R2
            key = f"{self.knowledge_path}/{knowledge_id}.json.gz"

            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=compressed,
                ContentType='application/gzip',
                Metadata={
                    'original_size': str(len(content_bytes)),
                    'knowledge_id': str(knowledge_id),
                }
            )

            # Generate URL
            r2_url = f"s3://{self.bucket}/{key}"

            logger.info(
                "r2_upload_success",
                knowledge_id=str(knowledge_id),
                key=key,
                size_kb=len(compressed) / 1024,
            )

            return r2_url

        except ClientError as e:
            logger.error(
                "r2_upload_error",
                knowledge_id=str(knowledge_id),
                error=str(e),
            )
            return None

    async def retrieve_from_r2(
        self,
        r2_url: str,
    ) -> Optional[str]:
        """
        Retrieve content from R2.

        Args:
            r2_url: R2 URL

        Returns:
            Decompressed content or None
        """
        try:
            # Parse key from URL
            # URL format: s3://bucket/path/to/file.json.gz
            key = r2_url.split(f"{self.bucket}/", 1)[1]

            # Download from R2
            response = self.s3_client.get_object(
                Bucket=self.bucket,
                Key=key,
            )

            compressed = response['Body'].read()

            # Decompress
            content = gzip.decompress(compressed).decode('utf-8')

            logger.debug(
                "r2_retrieve_success",
                key=key,
                size_kb=len(compressed) / 1024,
            )

            return content

        except Exception as e:
            logger.error(
                "r2_retrieve_error",
                r2_url=r2_url,
                error=str(e),
            )
            return None

    async def _enforce_size_limits(self) -> None:
        """
        Enforce size limits by archiving old entries.

        This is called before every new entry to ensure we stay under limits.
        """
        # Count total entries
        count_result = await self.db.execute(
            select(func.count(MarketKnowledge.id))
        )
        total_count = count_result.scalar() or 0

        # If at limit, archive oldest entries
        if total_count >= self.MAX_KNOWLEDGE_ENTRIES:
            await self._archive_oldest_entries(
                num_to_archive=total_count - self.MAX_KNOWLEDGE_ENTRIES + 10
            )

        # Also archive entries older than MAX_AGE_DAYS
        await self._archive_old_entries()

    async def _archive_oldest_entries(self, num_to_archive: int) -> int:
        """Archive oldest entries to R2."""
        # Get oldest entries that have content in DB
        result = await self.db.execute(
            select(MarketKnowledge)
            .where(
                MarketKnowledge.content.isnot(None),
                MarketKnowledge.r2_url.is_(None),
            )
            .order_by(MarketKnowledge.collected_at.asc())
            .limit(num_to_archive)
        )
        entries = result.scalars().all()

        archived_count = 0

        for entry in entries:
            if entry.content:
                r2_url = await self._archive_to_r2(
                    str(entry.id),
                    entry.content
                )

                if r2_url:
                    entry.content = None  # Remove from DB
                    entry.r2_url = r2_url
                    entry.archived_at = datetime.utcnow()
                    archived_count += 1

        await self.db.commit()

        if archived_count > 0:
            logger.info(
                "archived_oldest_entries",
                count=archived_count,
            )

        return archived_count

    async def _archive_old_entries(self) -> int:
        """Archive entries older than MAX_AGE_DAYS."""
        cutoff = datetime.utcnow() - timedelta(days=self.MAX_AGE_DAYS)

        result = await self.db.execute(
            select(MarketKnowledge)
            .where(
                MarketKnowledge.collected_at < cutoff,
                MarketKnowledge.content.isnot(None),
            )
        )
        entries = result.scalars().all()

        archived_count = 0

        for entry in entries:
            if entry.content:
                r2_url = await self._archive_to_r2(
                    str(entry.id),
                    entry.content
                )

                if r2_url:
                    entry.content = None
                    entry.r2_url = r2_url
                    entry.archived_at = datetime.utcnow()
                    archived_count += 1

        await self.db.commit()

        if archived_count > 0:
            logger.info(
                "archived_old_entries",
                count=archived_count,
                days_old=self.MAX_AGE_DAYS,
            )

        return archived_count

    async def get_knowledge(
        self,
        market_id: str,
        content_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get knowledge for a market, retrieving from R2 if needed.

        Args:
            market_id: Market ID
            content_type: Filter by type
            limit: Max entries

        Returns:
            List of knowledge entries with content
        """
        # Build query
        query = select(MarketKnowledge).where(
            MarketKnowledge.market_id == market_id
        )

        if content_type:
            query = query.where(MarketKnowledge.content_type == content_type)

        query = query.order_by(
            MarketKnowledge.relevance_score.desc(),
            MarketKnowledge.collected_at.desc()
        ).limit(limit)

        result = await self.db.execute(query)
        entries = result.scalars().all()

        # Retrieve content from R2 if needed
        enriched_entries = []

        for entry in entries:
            entry_dict = {
                "id": str(entry.id),
                "market_id": entry.market_id,
                "content_type": entry.content_type,
                "source_url": entry.source_url,
                "title": entry.title,
                "summary": entry.summary,
                "relevance_score": float(entry.relevance_score) if entry.relevance_score else 0,
                "collected_at": entry.collected_at.isoformat(),
            }

            # Get content (from DB or R2)
            if entry.content:
                entry_dict["content"] = entry.content
            elif entry.r2_url:
                # Lazy load from R2
                content = await self.retrieve_from_r2(entry.r2_url)
                entry_dict["content"] = content
                entry_dict["from_r2"] = True
            else:
                entry_dict["content"] = None

            enriched_entries.append(entry_dict)

        return enriched_entries

    async def get_storage_stats(self) -> Dict:
        """Get storage statistics."""
        # Total entries
        total_result = await self.db.execute(
            select(func.count(MarketKnowledge.id))
        )
        total_entries = total_result.scalar() or 0

        # Archived entries
        archived_result = await self.db.execute(
            select(func.count(MarketKnowledge.id))
            .where(MarketKnowledge.r2_url.isnot(None))
        )
        archived_entries = archived_result.scalar() or 0

        # Size estimate (rough)
        avg_entry_size = 5 * 1024  # 5KB average
        estimated_size_mb = round((total_entries * avg_entry_size) / (1024 * 1024), 2)

        return {
            "total_entries": total_entries,
            "archived_entries": archived_entries,
            "hot_entries": total_entries - archived_entries,
            "estimated_size_mb": estimated_size_mb,
            "max_entries": self.MAX_KNOWLEDGE_ENTRIES,
            "usage_percent": round((total_entries / self.MAX_KNOWLEDGE_ENTRIES) * 100, 1),
        }


__all__ = ["HybridStorage"]
