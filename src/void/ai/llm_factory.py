"""
LLM Client Factory

Creates the appropriate LLM client based on configuration.
Supports: Groq, DeepSeek, OpenAI (with extensibility for more providers)
"""

from void.config import config
from void.ai.groq_client import GroqClient
# from void.ai.deepseek_client import DeepSeekClient  # Future
# from void.ai.openai_client import OpenAIClient  # Future
import structlog

logger = structlog.get_logger()


def create_llm_client():
    """
    Create LLM client based on configured provider.

    Returns:
        LLM client instance (GroqClient, DeepSeekClient, or OpenAIClient)

    Raises:
        ValueError: If provider is not supported or credentials are missing
    """
    provider = config.ai.llm_provider.lower()

    logger.info(
        "creating_llm_client",
        provider=provider,
        model=config.ai.groq_model if provider == "groq" else
               config.ai.deepseek_model if provider == "deepseek" else
               config.ai.openai_model if provider == "openai" else "unknown"
    )

    if provider == "groq":
        api_key = config.ai.groq_api_key.get_secret_value()
        if not api_key:
            raise ValueError("Groq API key not configured. Set AI_GROQ_API_KEY in .env")

        return GroqClient(
            api_key=api_key,
            model=config.ai.groq_model,
            temperature=config.ai.chat_temperature,
            max_tokens=config.ai.chat_max_tokens,
            timeout=config.ai.chat_timeout_seconds,
        )

    elif provider == "deepseek":
        # Future implementation
        api_key = config.ai.deepseek_api_key.get_secret_value()
        if not api_key:
            raise ValueError("DeepSeek API key not configured. Set AI_DEEPSEEK_API_KEY in .env")

        # return DeepSeekClient(
        #     api_key=api_key,
        #     model=config.ai.deepseek_model,
        # )
        raise NotImplementedError("DeepSeek client not yet implemented. Use 'groq' provider.")

    elif provider == "openai":
        # Future implementation
        api_key = config.ai.openai_api_key.get_secret_value()
        if not api_key:
            raise ValueError("OpenAI API key not configured. Set AI_OPENAI_API_KEY in .env")

        # return OpenAIClient(
        #     api_key=api_key,
        #     model=config.ai.openai_model,
        # )
        raise NotImplementedError("OpenAI client not yet implemented. Use 'groq' provider.")

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Supported providers: groq, deepseek, openai. "
            f"Set AI_LLM_PROVIDER in .env"
        )
