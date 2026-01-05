from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# Embedding dimensions for supported models
MODEL_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
    "models/sentence-transformers_all-MiniLM-L6-v2": 384,
}

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_LOCAL_MODEL = "models/sentence-transformers_all-MiniLM-L6-v2"
DEFAULT_DIMENSIONS = 384


def get_model_path(model_name: str) -> str:
    """Resolve model path, preferring local models if available.

    Args:
        model_name: Model name or path.

    Returns:
        Resolved model path (local if exists, otherwise original name).
    """
    # If it's already a local path that exists, use it
    if Path(model_name).exists():
        logger.info("Using local model: %s", model_name)
        return model_name

    # Check for local model in models/ directory
    local_model_name = model_name.replace("/", "_")
    local_path = Path("models") / local_model_name

    if local_path.exists():
        logger.info("Found local model: %s", local_path)
        return str(local_path)

    # Check environment variable for model path
    env_model_path = os.getenv("EMBEDDING_MODEL_PATH")
    if env_model_path and Path(env_model_path).exists():
        logger.info("Using model from EMBEDDING_MODEL_PATH: %s", env_model_path)
        return env_model_path

    # Fall back to downloading from HuggingFace
    logger.info("Using remote model: %s", model_name)
    return model_name


class EmbeddingError(Exception):
    """Raised when embedding generation fails after all retries."""


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""

    model_name: str = DEFAULT_MODEL
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0


class EmbeddingService:
    """Service for generating embeddings with retry logic and error handling."""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._embedding_fn = None
        self._model_loaded = False

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions for the configured model."""
        return MODEL_DIMENSIONS.get(self.config.model_name, DEFAULT_DIMENSIONS)

    @property
    def embedding_function(self):
        """Lazy-load the embedding function."""
        if self._embedding_fn is None:
            self._embedding_fn = build_embedding_function(self.config.model_name)
            self._model_loaded = True
            logger.info(
                "Loaded embedding model: %s (dimensions=%d)",
                self.config.model_name,
                self.dimensions,
            )
        return self._embedding_fn

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts with retry logic.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.

        Raises:
            EmbeddingError: If embedding fails after all retries.
        """
        if not texts:
            return []

        last_error: Optional[Exception] = None
        delay = self.config.retry_delay

        for attempt in range(1, self.config.max_retries + 1):
            try:
                embeddings = self.embedding_function(texts)
                if attempt > 1:
                    logger.info(
                        "Embedding succeeded on attempt %d/%d",
                        attempt,
                        self.config.max_retries,
                    )
                return embeddings
            except Exception as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    logger.warning(
                        "Embedding attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt,
                        self.config.max_retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= self.config.retry_backoff
                else:
                    logger.error(
                        "Embedding failed after %d attempts: %s",
                        self.config.max_retries,
                        exc,
                    )

        raise EmbeddingError(
            f"Failed to generate embeddings after {self.config.max_retries} attempts: {last_error}"
        ) from last_error


def build_embedding_function(model_name: str):
    """Create a SentenceTransformer embedding function for Chroma.

    Automatically resolves to local model if available in models/ directory.
    """
    resolved_path = get_model_path(model_name)
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=resolved_path,
    )
