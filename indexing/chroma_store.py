from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api import Collection


def get_collection(
    persist_path: Path,
    collection_name: str,
    embedding_function,
) -> Collection:
    persist_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_function,
    )
    return collection
