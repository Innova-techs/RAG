from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# Embedding dimensions for supported models
MODEL_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
}

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSIONS = 384


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
    """Create a SentenceTransformer embedding function for Chroma."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=model_name,
    )
