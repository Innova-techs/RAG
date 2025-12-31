"""Vector indexing package using Chroma for document chunk storage."""

from .embeddings import (
    DEFAULT_DIMENSIONS,
    DEFAULT_MODEL,
    EmbeddingConfig,
    EmbeddingError,
    EmbeddingService,
    build_embedding_function,
)
from .pipeline import ChromaIndexingPipeline, IndexingConfig, IndexingResult

__all__ = [
    "ChromaIndexingPipeline",
    "IndexingConfig",
    "IndexingResult",
    "EmbeddingService",
    "EmbeddingConfig",
    "EmbeddingError",
    "build_embedding_function",
    "DEFAULT_MODEL",
    "DEFAULT_DIMENSIONS",
]
