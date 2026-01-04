"""
Z.ai GLM-4.7 client wrapper for VOID AI features.

Provides async interface with timeout, retry, and error handling.
Uses official zai-sdk package.
"""

import asyncio
import json
from typing import Optional, Dict, Any

from zai import ZaiClient

from void.config import config
import structlog

logger = structlog.get_logger()


class ZAIClient:
    """Async client for Z.ai GLM-4.7 API."""

    def __init__(self):
        self.api_key = config.ai.zai_api_key.get_secret_value()
        self.model = config.ai.zai_model
        self.timeout = config.ai.chat_timeout_seconds
        self.max_tokens = config.ai.chat_max_tokens
        self.temperature = config.ai.chat_temperature

        # Initialize ZaiClient
        self.client = ZaiClient(api_key=self.api_key)

    async def _call_api(
        self,
        messages: list[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
    ) -> str:
        """
        Call Z.ai API with retry logic.

        Args:
            messages: Chat messages array
            temperature: Override default temperature
            max_tokens: Override default max tokens
            response_format: "text" or "json" (for structured output)

        Returns:
            Response text

        Raises:
            Exception: On API errors after retries
        """
        # Build request parameters
        request_params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        # Add response format if specified
        if response_format == "json":
            request_params["response_format"] = {"type": "json_object"}

        try:
            logger.debug(
                "zai_api_call",
                model=self.model,
                message_count=len(messages),
            )

            # Call API in thread pool to avoid blocking (zai-sdk is synchronous)
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                **request_params
            )

            # Extract content from response
            content = response.choices[0].message.content

            logger.info(
                "zai_api_success",
                model=self.model,
                tokens_used=response.usage.total_tokens if hasattr(response, 'usage') else "unknown",
            )

            return content

        except Exception as e:
            logger.error(
                "zai_api_http_error",
                response=str(e),
                status_code=getattr(e, 'status_code', None),
            )
            raise

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message intent.

        Args:
            message: User message

        Returns:
            Intent classification: PORTFOLIO_QUERY, MARKET_RESEARCH, TRADING_ADVICE, SIGNAL_ANALYSIS, GENERAL_KNOWLEDGE
        """
        from void.ai.prompt_templates import PromptTemplates

        response = await self._call_api(
            messages=[
                {"role": "system", "content": PromptTemplates.INTENT_CLASSIFICATION},
                {"role": "user", "content": message},
            ],
            temperature=0.1,
            response_format="text",
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

        response = await self._call_api(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response

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

        response = await self._call_api(
            messages=[
                {"role": "system", "content": "You are a sentiment analyzer. Always respond with valid JSON only, no markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format="json",
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
