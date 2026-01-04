"""
Main AI chat service for VOID.

Orchestrates LLM calls, context building, and conversation management.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from void.ai.llm_client import ZAIClient
from void.ai.conversation_manager import ConversationManager
from void.ai.context_builder import ContextBuilder
from void.ai.prompt_templates import PromptTemplates
from void.config import config

import structlog

logger = structlog.get_logger()


class ChatService:
    """Main chat service coordinating all AI features."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = ZAIClient()
        self.conv_manager = ConversationManager(db)
        self.context_builder = ContextBuilder(db)

        if not config.ai.chat_enabled:
            logger.warning("chat_disabled_in_config")

    async def chat(
        self,
        user_id: int,
        message: str,
        account_id: Optional[int] = None,
    ) -> str:
        """
        Main chat entry point.

        Args:
            user_id: Telegram user ID
            message: User message
            account_id: Optional account ID

        Returns:
            AI response
        """
        if not config.ai.chat_enabled:
            return "AI chat is currently disabled."

        try:
            # 1. Classify intent
            intent = await self.llm.classify_intent(message)
            logger.debug("chat_intent_detected", intent=intent, user_id=user_id)

            # 2. Get conversation history
            history = await self.conv_manager.get_conversation(user_id)

            # 3. Build context
            context = await self.context_builder.build_full_context(
                user_id=user_id,
                market_id=self._extract_market_id(message, intent),
            )

            # 4. Generate response based on intent
            system_prompt = PromptTemplates.format_system_prompt()

            if intent == "PORTFOLIO_QUERY":
                response = await self._handle_portfolio_query(
                    message, system_prompt, context, history
                )
            elif intent == "MARKET_RESEARCH":
                response = await self._handle_market_research(
                    message, system_prompt, context, history
                )
            elif intent == "TRADING_ADVICE":
                response = await self._handle_trading_advice(
                    message, system_prompt, context, history
                )
            elif intent == "SIGNAL_ANALYSIS":
                response = await self._handle_signal_analysis(
                    message, system_prompt, context, history
                )
            else:  # GENERAL_KNOWLEDGE
                response = await self._handle_general_query(
                    message, system_prompt, context, history
                )

            # 5. Save to conversation history
            await self.conv_manager.add_message(user_id, "user", message)
            await self.conv_manager.add_message(user_id, "assistant", response)

            return response

        except Exception as e:
            logger.error(
                "chat_service_error",
                user_id=user_id,
                error=str(e),
                exc_info=True,
            )
            return f"Sorry, I encountered an error: {str(e)}"

    def _extract_market_id(self, message: str, intent: str) -> Optional[str]:
        """
        Extract market ID from message if present.

        Simple heuristic - looks for 0x followed by hex chars.
        """
        import re

        # Look for Polymarket condition IDs (0x + hex)
        matches = re.findall(r'0x[a-fA-F0-9]{40,}', message)
        return matches[0] if matches else None

    async def _handle_portfolio_query(
        self,
        message: str,
        system_prompt: str,
        context: Dict[str, str],
        history: list,
    ) -> str:
        """Handle portfolio-related questions."""

        from void.ai.prompt_templates import PromptTemplates

        prompt = PromptTemplates.PORTFOLIO_ANALYSIS.format(
            portfolio_summary=context["user_context"],
            positions="",  # Already in user_context
            performance_stats="",  # Already in user_context
        )

        response = await self.llm.chat_with_context(
            message=message,
            system_prompt=system_prompt,
            user_context=prompt,
            conversation_history=history,
        )

        return response

    async def _handle_market_research(
        self,
        message: str,
        system_prompt: str,
        context: Dict[str, str],
        history: list,
    ) -> str:
        """Handle market research questions."""

        from void.ai.prompt_templates import PromptTemplates

        # Get full market details if market_id present
        market_id = self._extract_market_id(message, "MARKET_RESEARCH")

        if market_id:
            # Fetch detailed market info
            from void.data.models import Market
            from sqlalchemy import select

            result = await self.db.execute(
                select(Market).where(Market.id == market_id)
            )
            market = result.scalar_one_or_none()

            if market:
                prompt = PromptTemplates.MARKET_RESEARCH.format(
                    market_question=market.question,
                    condition_id=market.condition_id,
                    yes_price=float(market.yes_price),
                    no_price=float(market.no_price),
                    liquidity=float(market.liquidity),
                    volume_24h=float(market.volume_24h),
                    end_date=market.end_date.isoformat() if market.end_date else "N/A",
                    twitter_sentiment=f"{market.sentiment_score:+.2f}" if market.sentiment_score else "N/A",
                    news_count=market.news_count,
                    sentiment_trend="See knowledge base",
                    knowledge_insights=context["knowledge_summary"],
                )

                return await self.llm.chat(prompt)

        # General market overview
        return await self.llm.chat_with_context(
            message=message,
            system_prompt=system_prompt,
            user_context=context["market_context"],
            conversation_history=history,
        )

    async def _handle_trading_advice(
        self,
        message: str,
        system_prompt: str,
        context: Dict[str, str],
        history: list,
    ) -> str:
        """Handle trading advice requests."""

        from void.ai.prompt_templates import PromptTemplates

        prompt = PromptTemplates.TRADING_ADVICE.format(
            portfolio_summary=context["user_context"],
            market_details=context["market_context"],
            question=message,
        )

        response = await self.llm.chat_with_context(
            message=prompt,
            system_prompt=system_prompt,
            user_context="",
            conversation_history=history,
        )

        return response

    async def _handle_signal_analysis(
        self,
        message: str,
        system_prompt: str,
        context: Dict[str, str],
        history: list,
    ) -> str:
        """Handle signal explanation requests."""

        from void.ai.prompt_templates import PromptTemplates

        # Try to extract signal ID or get recent signals
        # For now, provide general signal info
        prompt = PromptTemplates.EXPLAIN_SIGNAL.format(
            signal_type="Recent",
            strategy="Oracle Latency",
            market_question="See portfolio",
            entry_price=0.5,
            expected_payout=1.0,
            profit_margin=5.0,
            confidence=0.85,
            verification_data="Oracle feed confirmed",
            market_context=context["market_context"],
        )

        return await self.llm.chat(prompt)

    async def _handle_general_query(
        self,
        message: str,
        system_prompt: str,
        context: Dict[str, str],
        history: list,
    ) -> str:
        """Handle general knowledge questions."""

        return await self.llm.chat_with_context(
            message=message,
            system_prompt=system_prompt,
            user_context=f"Available Context:\n{context['user_context']}\n\n{context['market_context']}",
            conversation_history=history,
        )

    async def research_market(
        self,
        market_id: str,
        user_id: int,
    ) -> str:
        """
        Perform deep research on a specific market.

        Args:
            market_id: Polymarket market ID
            user_id: User requesting research

        Returns:
            Research report
        """
        from void.ai.prompt_templates import PromptTemplates
        from void.data.models import Market
        from sqlalchemy import select

        # Get market details
        result = await self.db.execute(
            select(Market).where(Market.id == market_id)
        )
        market = result.scalar_one_or_none()

        if not market:
            return f"Market {market_id} not found."

        # Build context
        context = await self.context_builder.build_full_context(
            user_id=user_id,
            market_id=market_id,
        )

        # Generate research report
        report = PromptTemplates.MARKET_RESEARCH.format(
            market_question=market.question,
            condition_id=market.condition_id,
            yes_price=float(market.yes_price),
            no_price=float(market.no_price),
            liquidity=float(market.liquidity),
            volume_24h=float(market.volume_24h),
            end_date=market.end_date.isoformat() if market.end_date else "N/A",
            twitter_sentiment=f"{market.sentiment_score:+.2f}" if market.sentiment_score else "N/A",
            news_count=market.news_count,
            sentiment_trend="See knowledge base",
            knowledge_insights=context["knowledge_summary"],
        )

        response = await self.llm.chat(report)

        # Update market's last_researched timestamp
        market.last_researched_at = datetime.utcnow()
        await self.db.commit()

        return response

    async def clear_history(self, user_id: int) -> str:
        """Clear conversation history for user."""
        await self.conv_manager.clear_history(user_id)
        return "Conversation history cleared."


__all__ = ["ChatService"]
