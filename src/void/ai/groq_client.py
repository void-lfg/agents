"""
Groq LLM client implementation.

Uses Groq's free tier with llama-3.3-70b-versatile model.
OpenAI-compatible API with rate limiting: 30 RPM, 6K TPM, 14.4K RPD
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from groq import AsyncGroq
from void.ai.llm_base import BaseLLMClient
from void.config import config
import structlog

logger = structlog.get_logger()


class GroqClient(BaseLLMClient):
    """Groq LLM client with rate limiting and retry logic."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile", **kwargs):
        super().__init__(api_key, model, **kwargs)

        # Rate limiting: 30 RPM (requests per minute), 6K TPM (tokens per minute)
        self.max_requests_per_minute = 30
        self.max_tokens_per_minute = 6000

        # Rate limiting state
        self.request_timestamps: List[datetime] = []
        self.token_usage: List[tuple[datetime, int]] = []

        # Initialize async Groq client
        self.client = AsyncGroq(api_key=api_key)

    async def _check_rate_limits(self, estimated_tokens: int = 100) -> None:
        """
        Check and enforce rate limits.

        Args:
            estimated_tokens: Estimated tokens for this request

        Raises:
            Exception: If rate limit would be exceeded
        """
        now = datetime.utcnow()

        # Clean old timestamps (older than 1 minute)
        one_minute_ago = now - timedelta(minutes=1)
        self.request_timestamps = [
            ts for ts in self.request_timestamps if ts > one_minute_ago
        ]
        self.token_usage = [
            (ts, tokens) for ts, tokens in self.token_usage if ts > one_minute_ago
        ]

        # Check request rate limit (30 RPM)
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            wait_time = 60 - (now - self.request_timestamps[0]).total_seconds()
            if wait_time > 0:
                logger.warning(
                    "groq_rate_limit_wait",
                    wait_seconds=wait_time,
                    reason="request_rate_limit"
                )
                await asyncio.sleep(wait_time)
                # Clear after waiting
                self.request_timestamps = []
                self.token_usage = []

        # Check token rate limit (6K TPM)
        tokens_last_minute = sum(tokens for _, tokens in self.token_usage)
        if tokens_last_minute + estimated_tokens > self.max_tokens_per_minute:
            wait_time = 60 - (now - self.token_usage[0][0]).total_seconds()
            if wait_time > 0:
                logger.warning(
                    "groq_rate_limit_wait",
                    wait_seconds=wait_time,
                    reason="token_rate_limit",
                    current_tokens=tokens_last_minute,
                    estimated_new_tokens=estimated_tokens
                )
                await asyncio.sleep(wait_time)
                # Clear after waiting
                self.token_usage = []

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        Generate chat completion using Groq.

        Args:
            messages: Chat messages array
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Groq parameters

        Returns:
            Generated response text

        Raises:
            Exception: On API errors
        """
        # Estimate input tokens (rough estimate: ~4 characters per token)
        input_text = " ".join(m.get("content", "") for m in messages)
        estimated_input_tokens = len(input_text) // 4

        # Check rate limits
        await self._check_rate_limits(estimated_input_tokens + max_tokens)

        try:
            logger.debug(
                "groq_api_call",
                model=self.model,
                message_count=len(messages),
                estimated_input_tokens=estimated_input_tokens,
                max_tokens=max_tokens,
            )

            # Call Groq API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            # Extract content
            content = response.choices[0].message.content

            # Track usage
            now = datetime.utcnow()
            self.request_timestamps.append(now)

            if hasattr(response, 'usage') and response.usage:
                total_tokens = response.usage.total_tokens
                self.token_usage.append((now, total_tokens))

                logger.info(
                    "groq_api_success",
                    model=self.model,
                    tokens_used=total_tokens,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                )
            else:
                logger.info(
                    "groq_api_success",
                    model=self.model,
                    tokens_used="unknown"
                )

            return content

        except Exception as e:
            logger.error(
                "groq_api_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def chat_with_context(
        self,
        message: str,
        system_prompt: str,
        user_context: str = "",
        conversation_history: list = [],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate chat response with context.

        Args:
            message: User message
            system_prompt: System prompt
            user_context: User context (portfolio, positions, etc.)
            conversation_history: Previous conversation
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            AI response
        """
        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history
        for turn in conversation_history[-10:]:  # Last 10 turns
            if isinstance(turn, dict):
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role and content:
                    messages.append({"role": role, "content": content})

        # Add user context if provided
        if user_context:
            messages.append({
                "role": "system",
                "content": f"USER CONTEXT:\n{user_context}"
            })

        # Add current message
        messages.append({"role": "user", "content": message})

        return await self.chat_completion(
            messages=messages,
            temperature=temperature or self.config.get("temperature", 0.7),
            max_tokens=max_tokens or self.config.get("max_tokens", 2000),
        )

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message intent.

        Args:
            message: User message

        Returns:
            Intent classification: PORTFOLIO_QUERY, MARKET_RESEARCH, TRADING_ADVICE, SIGNAL_ANALYSIS, GENERAL_KNOWLEDGE
        """
        from void.ai.prompt_templates import PromptTemplates

        response = await self.chat_completion(
            messages=[
                {"role": "system", "content": PromptTemplates.INTENT_CLASSIFICATION},
                {"role": "user", "content": message},
            ],
            temperature=0.1,
            max_tokens=50,
        )

        # Parse intent from response
        intent = response.strip().upper()
        valid_intents = [
            "PORTFOLIO_QUERY",
            "MARKET_RESEARCH",
            "TRADING_ADVICE",
            "SIGNAL_ANALYSIS",
            "GENERAL_KNOWLEDGE",
        ]

        for valid_intent in valid_intents:
            if valid_intent in intent:
                return valid_intent

        return "GENERAL_KNOWLEDGE"

    async def analyze_sentiment(
        self,
        text: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze
            context: Optional context (e.g., "tweet about Bitcoin")

        Returns:
            Dict with score, confidence, key_points
        """
        from void.ai.prompt_templates import PromptTemplates

        context_str = f"\nContext: {context}" if context else ""
        prompt = PromptTemplates.SENTIMENT_ANALYSIS.format(
            text=text,
            context=context_str
        )

        response = await self.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a sentiment analyzer. Always respond with valid JSON only, no markdown."
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        # Parse JSON response
        try:
            result = json.loads(response)

            # Ensure all required fields exist
            if "score" not in result:
                result["score"] = 0.0
            if "confidence" not in result:
                result["confidence"] = 0.5
            if "key_points" not in result:
                result["key_points"] = []

            return result

        except json.JSONDecodeError:
            # Fallback if response is not valid JSON
            logger.warning("sentiment_analysis_not_json", response=response[:100])
            return {
                "score": 0.0,
                "confidence": 0.3,
                "key_points": [],
                "raw_response": response,
            }
