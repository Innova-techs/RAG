from __future__ import annotations

from chromadb.utils import embedding_functions


def build_embedding_function(model_name: str):
    """Create a SentenceTransformer embedding function for Chroma."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=model_name,
    )
