"""
Provider-agnostic LLM client base interface.

Defines the abstract interface that all LLM providers must implement.
This allows easy migration between providers (Groq, DeepSeek, OpenAI, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, api_key: str, model: str, **kwargs):
        """
        Initialize LLM client.

        Args:
            api_key: API key for the provider
            model: Model identifier
            **kwargs: Additional provider-specific config
        """
        self.api_key = api_key
        self.model = model
        self.config = kwargs

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        Generate chat completion.

        Args:
            messages: Chat messages array
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            Generated response text
        """
        pass

    @abstractmethod
    async def classify_intent(self, message: str) -> str:
        """
        Classify user message intent.

        Args:
            message: User message

        Returns:
            Intent classification
        """
        pass

    @abstractmethod
    async def analyze_sentiment(
        self,
        text: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze
            context: Optional context

        Returns:
            Dict with score, confidence, key_points
        """
        pass
