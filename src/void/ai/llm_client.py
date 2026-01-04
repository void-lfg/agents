"""
Z.ai GLM-4.7 client wrapper for VOID AI features.

Provides async interface with timeout, retry, and error handling.
"""

import asyncio
import json
from typing import Optional, Dict, Any
from decimal import Decimal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

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

        # Z.ai API endpoint (adjust based on actual API)
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
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
            httpx.HTTPError: On API errors after retries
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        # Add response format if specified
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                logger.debug(
                    "zai_api_call",
                    model=self.model,
                    message_count=len(messages),
                )

                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                # Extract content from response
                content = data["choices"][0]["message"]["content"]

                logger.info(
                    "zai_api_success",
                    model=self.model,
                    tokens_used=data.get("usage", {}).get("total_tokens", "unknown"),
                )

                return content

            except httpx.HTTPStatusError as e:
                logger.error(
                    "zai_api_http_error",
                    status_code=e.response.status_code,
                    response=e.response.text,
                )
                raise

            except httpx.TimeoutException:
                logger.warning("zai_api_timeout")
                raise

            except Exception as e:
                logger.error("zai_api_error", error=str(e))
                raise

    async def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[Dict]] = None,
    ) -> str:
        """
        Simple chat interface.

        Args:
            message: User message
            system_prompt: Optional system prompt
            history: Optional conversation history

        Returns:
            Assistant response
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": message})

        return await self._call_api(messages)

    async def chat_with_context(
        self,
        message: str,
        system_prompt: str,
        user_context: str,
        conversation_history: list[Dict],
    ) -> str:
        """
        Chat with full context (system + user + history).

        Args:
            message: Current user message
            system_prompt: System prompt
            user_context: User/portfolio context
            conversation_history: Previous messages

        Returns:
            Assistant response
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"CONTEXT:\n{user_context}"},
        ]

        # Add conversation history (limited to last 5 exchanges)
        for msg in conversation_history[-10:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        messages.append({"role": "user", "content": message})

        return await self._call_api(messages)

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message intent.

        Args:
            message: User message

        Returns:
            Intent class (e.g., "PORTFOLIO_QUERY")
        """
        from void.ai.prompt_templates import PromptTemplates

        prompt = PromptTemplates.INTENT_CLASSIFICATION.format(message=message)

        messages = [
            {"role": "system", "content": "You are a precise intent classifier. Respond ONLY with the intent name."},
            {"role": "user", "content": prompt},
        ]

        # Use low temperature for consistent classification
        response = await self._call_api(messages, temperature=0.1)

        # Clean up response
        intent = response.strip().upper()

        logger.debug("intent_classified", intent=intent, message=message[:50])

        return intent

    async def analyze_sentiment(
        self,
        text: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze
            context: Optional context (e.g., market ID)

        Returns:
            Dict with score, confidence, sentiment, etc.
        """
        from void.ai.prompt_templates import PromptTemplates

        prompt = PromptTemplates.SENTIMENT_ANALYSIS.format(
            text=text,
            context=context or "general"
        )

        messages = [
            {"role": "system", "content": "You are a sentiment analyzer. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ]

        # Request JSON response
        response = await self._call_api(messages, response_format="json")

        try:
            # Parse JSON response
            result = json.loads(response)

            # Convert to proper types
            result["score"] = float(result.get("score", 0))
            result["confidence"] = float(result.get("confidence", 0))

            return result

        except json.JSONDecodeError:
            logger.error("sentiment_json_parse_error", response=response)

            # Fallback to default
            return {
                "score": 0.0,
                "confidence": 0.0,
                "sentiment": "neutral",
                "key_points": [],
                "reasoning": "Parse error",
            }

    async def generate_response(
        self,
        template: str,
        **kwargs,
    ) -> str:
        """
        Generate response from template with parameters.

        Args:
            template: Prompt template string
            **kwargs: Template variables

        Returns:
            Generated response
        """
        # Format template
        prompt = template.format(**kwargs)

        messages = [
            {"role": "system", "content": "You are VOID AI assistant."},
            {"role": "user", "content": prompt},
        ]

        return await self._call_api(messages)


__all__ = ["ZAIClient"]
