"""LLM provider implementations.

This package contains client implementations for various LLM providers:
- OpenAI (GPT-4, GPT-4o, etc.)
- Anthropic (Claude)
- Ollama (local/offline models)

All providers implement the BaseLLMClient protocol defined in generation.base.
"""

from .anthropic_client import AnthropicClient
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient

__all__ = ["OpenAIClient", "AnthropicClient", "OllamaClient"]
