"""
Conversation history manager for AI chat.

Manages user chat sessions with automatic pruning and size limits.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from void.data.models import ConversationHistory
from void.config import config

import structlog

logger = structlog.get_logger()


class ConversationManager:
    """Manage chat conversation history with size optimization."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.max_history = config.ai.chat_max_history  # Default: 10 messages
        self.max_message_age_hours = 24  # Auto-archive messages older than this

    async def get_conversation(
        self,
        user_id: int,
        max_messages: Optional[int] = None,
    ) -> List[Dict]:
        """
        Get conversation history for a user.

        Args:
            user_id: Telegram user ID
            max_messages: Override default max messages

        Returns:
            List of message dicts: [{role, content, timestamp}, ...]
        """
        max_msg = max_messages or self.max_history

        # Get conversation from DB
        result = await self.db.execute(
            select(ConversationHistory)
            .where(ConversationHistory.user_id == user_id)
            .order_by(ConversationHistory.updated_at.desc())
            .limit(1)
        )
        conv = result.scalar_one_or_none()

        if not conv:
            return []

        # Return messages, limited to max_msg
        messages = conv.messages if conv.messages else []
        return messages[-max_msg:]

    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
    ) -> None:
        """
        Add a message to user's conversation history.

        Args:
            user_id: Telegram user ID
            role: 'user' or 'assistant'
            content: Message content
        """
        # Get existing conversation
        result = await self.db.execute(
            select(ConversationHistory)
            .where(ConversationHistory.user_id == user_id)
            .limit(1)
        )
        conv = result.scalar_one_or_none()

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if conv:
            # Add message to existing conversation
            messages = conv.messages if conv.messages else []
            messages.append(message)

            # Prune to max_history
            if len(messages) > self.max_history:
                messages = messages[-self.max_history:]

            conv.messages = messages
            conv.updated_at = datetime.utcnow()

            logger.debug(
                "conversation_updated",
                user_id=user_id,
                message_count=len(messages),
            )
        else:
            # Create new conversation
            conv = ConversationHistory(
                user_id=user_id,
                messages=[message],
            )

            self.db.add(conv)

            logger.debug(
                "conversation_created",
                user_id=user_id,
            )

        await self.db.commit()

        # Check if we need to prune old messages
        await self._prune_old_messages(user_id)

    async def clear_history(self, user_id: int) -> None:
        """
        Clear conversation history for a user.

        Args:
            user_id: Telegram user ID
        """
        await self.db.execute(
            delete(ConversationHistory)
            .where(ConversationHistory.user_id == user_id)
        )
        await self.db.commit()

        logger.info("conversation_cleared", user_id=user_id)

    async def _prune_old_messages(self, user_id: int) -> None:
        """
        Remove messages older than max_message_age_hours.

        This keeps the conversation fresh and reduces DB size.
        """
        result = await self.db.execute(
            select(ConversationHistory)
            .where(ConversationHistory.user_id == user_id)
            .limit(1)
        )
        conv = result.scalar_one_or_none()

        if not conv or not conv.messages:
            return

        cutoff_time = datetime.utcnow() - timedelta(hours=self.max_message_age_hours)

        # Filter out old messages
        pruned_messages = [
            msg for msg in conv.messages
            if datetime.fromisoformat(msg["timestamp"]) > cutoff_time
        ]

        if len(pruned_messages) < len(conv.messages):
            removed = len(conv.messages) - len(pruned_messages)
            conv.messages = pruned_messages
            conv.updated_at = datetime.utcnow()
            await self.db.commit()

            logger.debug(
                "conversation_pruned",
                user_id=user_id,
                removed_count=removed,
                remaining_count=len(pruned_messages),
            )

    async def get_stats(self, user_id: int) -> Dict:
        """
        Get conversation statistics for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            Dict with stats
        """
        result = await self.db.execute(
            select(ConversationHistory)
            .where(ConversationHistory.user_id == user_id)
            .limit(1)
        )
        conv = result.scalar_one_or_none()

        if not conv:
            return {
                "message_count": 0,
                "last_activity": None,
                "size_bytes": 0,
            }

        messages = conv.messages if conv.messages else []

        # Estimate size (rough calculation)
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        size_bytes = total_chars * 2  # UTF-16 encoding (approximate)

        return {
            "message_count": len(messages),
            "last_activity": conv.updated_at.isoformat() if conv.updated_at else None,
            "size_bytes": size_bytes,
            "size_kb": round(size_bytes / 1024, 2),
        }

    async def cleanup_all_inactive(self, days=7) -> int:
        """
        Delete conversations inactive for X days.

        This is called by a maintenance job to free up space.

        Args:
            days: Inactivity threshold

        Returns:
            Number of conversations deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            delete(ConversationHistory)
            .where(ConversationHistory.updated_at < cutoff)
        )

        deleted_count = result.rowcount
        await self.db.commit()

        if deleted_count > 0:
            logger.info(
                "cleanup_inactive_conversations",
                deleted_count=deleted_count,
                days_inactive=days,
            )

        return deleted_count


__all__ = ["ConversationManager"]
