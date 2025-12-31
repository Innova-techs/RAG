from __future__ import annotations

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.api import Collection


def get_collection(
    persist_path: Path,
    collection_name: str,
    embedding_function: Optional[object] = None,
) -> Collection:
    """Get or create a Chroma collection.

    Args:
        persist_path: Directory for Chroma persistence.
        collection_name: Name of the collection.
        embedding_function: Optional embedding function. If None, embeddings
            must be provided explicitly during upsert operations.

    Returns:
        Chroma collection instance.
    """
    persist_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_function,
    )
    return collection
