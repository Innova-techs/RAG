"""Factory function for creating LLM clients.

This module provides a factory function that instantiates the correct LLM client
based on configuration. The default provider is 'custom' which uses the existing
HMAC-authenticated client for backwards compatibility.
"""

from __future__ import annotations

import os
from typing import Optional

from .api_client import LLMClient, LLMConfig
from .base import BaseLLMClient


# Supported provider names
PROVIDERS = frozenset({"custom", "openai", "anthropic", "ollama"})

# Default provider (backwards compatible with existing behavior)
DEFAULT_PROVIDER = "custom"


class ProviderError(Exception):
    """Error related to LLM provider configuration."""

    pass


def create_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """Create an LLM client based on the specified provider.

    This factory function instantiates the appropriate LLM client based on
    the provider name. If no provider is specified, it reads from the
    LLM_PROVIDER environment variable, defaulting to 'custom' for
    backwards compatibility.

    Args:
        provider: Provider name. One of: custom, openai, anthropic, ollama.
                  If None, reads from LLM_PROVIDER env var (default: custom).

    Returns:
        An LLM client implementing the BaseLLMClient protocol.

    Raises:
        ProviderError: If the provider is unknown or configuration is invalid.

    Examples:
        # Use default provider (from env or 'custom')
        client = create_llm_client()

        # Explicitly specify provider
        client = create_llm_client("openai")

        # Use with RAGChain
        from generation.factory import create_llm_client
        from generation.rag_chain import RAGChain
        rag = RAGChain(create_llm_client())
    """
    # Get provider from argument, env var, or default
    provider = provider or os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    provider = provider.lower().strip()

    if provider not in PROVIDERS:
        raise ProviderError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported providers: {', '.join(sorted(PROVIDERS))}"
        )

    try:
        if provider == "custom":
            return _create_custom_client()
        elif provider == "openai":
            return _create_openai_client()
        elif provider == "anthropic":
            return _create_anthropic_client()
        elif provider == "ollama":
            return _create_ollama_client()
        else:
            raise ProviderError(f"Provider '{provider}' is not implemented")
    except ValueError as e:
        raise ProviderError(f"Failed to configure {provider} provider: {e}") from e


def _create_custom_client() -> LLMClient:
    """Create the custom HMAC-authenticated client."""
    config = LLMConfig.from_env()
    return LLMClient(config)


def _create_openai_client() -> BaseLLMClient:
    """Create an OpenAI client."""
    from .providers.openai_client import OpenAIClient

    return OpenAIClient()


def _create_anthropic_client() -> BaseLLMClient:
    """Create an Anthropic client."""
    from .providers.anthropic_client import AnthropicClient

    return AnthropicClient()


def _create_ollama_client() -> BaseLLMClient:
    """Create an Ollama client."""
    from .providers.ollama_client import OllamaClient

    return OllamaClient()


def get_available_providers() -> list[str]:
    """Get list of available provider names.

    Returns:
        Sorted list of provider names.
    """
    return sorted(PROVIDERS)
