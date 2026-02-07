"""
Main AI chat service for VOID.

Orchestrates LLM calls, context building, and conversation management.
Provider-agnostic - supports Groq, DeepSeek, OpenAI through factory pattern.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from void.ai.llm_factory import create_llm_client
from void.ai.conversation_manager import ConversationManager
from void.ai.context_builder import ContextBuilder
from void.ai.prompt_templates import PromptTemplates
from void.ai.web_browser import get_web_browser
from void.config import config

import structlog

logger = structlog.get_logger()


def strip_markdown(text: str) -> str:
    """
    Remove Markdown formatting from text for Telegram plain text messages.

    Args:
        text: Text with Markdown formatting

    Returns:
        Plain text without Markdown
    """
    # Remove bold (**text** or __text__)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)

    # Remove italic (*text* or _text_)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'_(?!.*_)(.*?)_', r'\1', text)

    # Remove headers (###, ##, #)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

    # Remove code blocks (```text```)
    text = re.sub(r'```.*?\n(.*?)```', r'\1', text, flags=re.DOTALL)

    # Remove inline code (`text`)
    text = re.sub(r'`(.*?)`', r'\1', text)

    # Remove strikethrough (~~text~~)
    text = re.sub(r'~~(.*?)~~', r'\1', text)

    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines
    text = text.strip()

    return text


class ChatService:
    """Main chat service coordinating all AI features."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = create_llm_client()
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

            # 5. Strip Markdown formatting for Telegram plain text
            response = strip_markdown(response)

            # 6. Save to conversation history
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

            # VOID-specific friendly error messages
            error_str = str(e)

            if "429" in error_str or "Too Many Requests" in error_str:
                return (
                    "🤖 *VOID AI Assistant*\n\n"
                    "I'm currently experiencing high demand and can't process your request right now. "
                    "Please try again in a moment.\n\n"
                    "In the meantime, you can use these commands:\n"
                    "• /portfolio - View your portfolio\n"
                    "• /positions - See open positions\n"
                    "• /status - Check system status\n"
                    "• /help - See all commands"
                )
            elif "余额不足" in error_str or "balance" in error_str.lower():
                return (
                    "🤖 *VOID AI Assistant*\n\n"
                    "I'm currently unable to access my AI services due to API credit limitations. "
                    "The VOID trading bot is still fully functional!\n\n"
                    "You can use these commands:\n"
                    "• /portfolio - View your portfolio balances\n"
                    "• /positions - See all open positions\n"
                    "• /signals - View recent trading signals\n"
                    "• /agents - Manage trading agents\n"
                    "• /status - System status\n\n"
                    "Try again later for AI-powered responses!"
                )
            else:
                return f"⚠️ Sorry, I encountered an error: {error_str[:200]}"

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

        # Strip Markdown formatting for Telegram plain text
        response = strip_markdown(response)

        # Update market's last_researched timestamp
        market.last_researched_at = datetime.utcnow()
        await self.db.commit()

        return response

    async def clear_history(self, user_id: int) -> str:
        """Clear conversation history for user."""
        await self.conv_manager.clear_history(user_id)
        return "Conversation history cleared."

    async def should_respond_in_group(
        self,
        message: str,
        bot_username: str,
        is_reply_to_bot: bool = False,
        chat_context: str = "",
    ) -> Tuple[bool, str]:
        """
        Determine if the bot should respond to a message in a group chat.

        Uses LLM to intelligently decide if a message is relevant to the bot.

        Args:
            message: The message text
            bot_username: Bot's username (without @)
            is_reply_to_bot: Whether this is a reply to bot's message
            chat_context: Recent chat context for relevance

        Returns:
            Tuple of (should_respond: bool, reason: str)
        """
        # Always respond if directly mentioned
        if f"@{bot_username}" in message.lower() or bot_username.lower() in message.lower():
            return True, "direct_mention"

        # Always respond if replying to bot's message
        if is_reply_to_bot:
            return True, "reply_to_bot"

        # Use LLM to determine relevance
        try:
            relevance_prompt = f"""You are VOID, a trading/crypto AI assistant in a group chat.
Determine if this message is directed at you or relevant to your expertise.

Your expertise includes:
- Cryptocurrency, trading, markets, DeFi
- Polymarket prediction markets
- Portfolio management, trading strategies
- Technical analysis, market research
- Web3, blockchain topics

Message: "{message}"

Recent chat context:
{chat_context[-500:] if chat_context else "No context"}

Respond with ONLY one of these:
- "RESPOND" - if the message is asking you something, mentioning trading/crypto topics, or continuing a conversation with you
- "IGNORE" - if it's just casual chat between other users, off-topic, or not directed at you

Be conservative - only respond when clearly relevant. Don't butt into random conversations.
"""
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": relevance_prompt}],
                temperature=0.1,
                max_tokens=20,
            )

            should_respond = "RESPOND" in response.upper()
            return should_respond, "relevance_check"

        except Exception as e:
            logger.warning("relevance_check_failed", error=str(e))
            # Default to not responding if check fails
            return False, "check_failed"

    async def group_chat(
        self,
        user_id: int,
        username: str,
        message: str,
        chat_id: int,
        chat_context: str = "",
    ) -> str:
        """
        Handle group chat message with a more casual, human-like personality.

        Args:
            user_id: Telegram user ID
            username: User's username
            message: User message
            chat_id: Group chat ID
            chat_context: Recent messages for context

        Returns:
            AI response
        """
        if not config.ai.chat_enabled:
            return "AI chat is currently disabled."

        try:
            # Check if message needs web search
            web_context = ""
            if self._needs_web_search(message):
                web_context = await self._perform_web_search(message)

            # Build group chat prompt
            group_system_prompt = """You're VOID - a chill trading/crypto AI hanging out in this group chat.

PERSONALITY:
- You're like a knowledgeable friend, not a formal assistant
- Keep responses SHORT and conversational (1-3 sentences usually)
- Use casual language: "yo", "ngl", "lmao", "tbh", "fr", "lowkey", "bet"
- Crypto slang is your second language: gm, gn, wagmi, ngmi, ser, anon, ape, degen, based, rekt
- Match the vibe of the conversation
- Don't be cringe or try too hard
- Be witty and slightly sarcastic when appropriate
- If you don't know something, just say so casually

DON'Ts:
- Don't be overly helpful or assistant-like
- Don't use bullet points or formal formatting
- Don't repeat the question back
- Don't give unsolicited advice
- Don't be preachy about risks (unless asked)
- Keep it brief - you're chatting, not writing an essay

Remember: You're part of the group, not serving the group. Be real."""

            # Include web context if available
            context_addition = ""
            if web_context:
                context_addition = f"\n\nWeb search results for context:\n{web_context}\n\n(Use this info naturally, don't announce you searched)"

            # Get conversation history for this group
            history = await self.conv_manager.get_conversation(chat_id)

            response = await self.llm.chat_completion(
                messages=[
                    {"role": "system", "content": group_system_prompt + context_addition},
                    *[{"role": h.get("role", "user"), "content": h.get("content", "")} for h in history[-5:]],
                    {"role": "user", "content": f"@{username}: {message}"}
                ],
                temperature=0.9,  # More creative for casual chat
                max_tokens=300,   # Keep responses short
            )

            # Clean up response
            response = strip_markdown(response)

            # Save to conversation history (use chat_id for group context)
            await self.conv_manager.add_message(chat_id, "user", f"@{username}: {message}")
            await self.conv_manager.add_message(chat_id, "assistant", response)

            return response

        except Exception as e:
            logger.error("group_chat_error", error=str(e), exc_info=True)
            return self._get_casual_error_response()

    def _needs_web_search(self, message: str) -> bool:
        """Check if message might benefit from web search."""
        search_indicators = [
            "what is", "who is", "when did", "how does",
            "latest", "news", "price of", "happened",
            "search", "look up", "find", "google",
            "today", "yesterday", "recent", "current",
            "http://", "https://", ".com", ".io", ".org"
        ]
        message_lower = message.lower()
        return any(indicator in message_lower for indicator in search_indicators)

    async def _perform_web_search(self, message: str) -> str:
        """Perform web search and return summary."""
        try:
            browser = get_web_browser()

            # Extract search query from message
            # Remove common prefixes
            query = message.lower()
            for prefix in ["what is", "who is", "search for", "look up", "google"]:
                query = query.replace(prefix, "")
            query = query.strip()

            if len(query) < 3:
                return ""

            results = await browser.search_duckduckgo(query, max_results=3)

            if not results:
                return ""

            summary = "Recent web info:\n"
            for r in results:
                summary += f"- {r['title']}: {r['snippet'][:150]}\n"

            return summary

        except Exception as e:
            logger.warning("web_search_failed", error=str(e))
            return ""

    async def fetch_url_content(self, url: str) -> str:
        """Fetch and summarize content from a URL."""
        try:
            browser = get_web_browser()
            content = await browser.fetch_url(url, max_chars=3000)

            if not content:
                return "Couldn't fetch that URL"

            # Summarize if too long
            if len(content) > 1000:
                summary_prompt = f"Summarize this in 2-3 sentences:\n\n{content[:2000]}"
                summary = await self.llm.chat_completion(
                    messages=[{"role": "user", "content": summary_prompt}],
                    temperature=0.3,
                    max_tokens=200,
                )
                return strip_markdown(summary)

            return content

        except Exception as e:
            logger.error("url_fetch_error", error=str(e))
            return "couldn't load that link rn"

    def _get_casual_error_response(self) -> str:
        """Get a casual error response."""
        import random
        responses = [
            "brain lagged for a sec, try again",
            "something broke lol, one sec",
            "my bad, didn't catch that",
            "glitched out, say again?",
            "rip, error. try again",
        ]
        return random.choice(responses)


__all__ = ["ChatService"]
