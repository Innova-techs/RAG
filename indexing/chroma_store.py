from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.api import Collection
from chromadb.errors import NotFoundError

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a Chroma health check."""

    healthy: bool
    message: str
    collection_count: int = 0
    document_count: int = 0


def health_check(persist_path: Path, collection_name: Optional[str] = None) -> HealthCheckResult:
    """Check if Chroma is healthy and accessible.

    Args:
        persist_path: Directory for Chroma persistence.
        collection_name: Optional collection to check. If provided, also checks
            the collection exists and returns document count.

    Returns:
        HealthCheckResult with status and details.
    """
    try:
        if not persist_path.exists():
            return HealthCheckResult(
                healthy=False,
                message=f"Persistence path does not exist: {persist_path}",
            )

        client = chromadb.PersistentClient(path=str(persist_path))
        collections = client.list_collections()
        collection_count = len(collections)

        if collection_name:
            try:
                collection = client.get_collection(collection_name)
                doc_count = collection.count()
                return HealthCheckResult(
                    healthy=True,
                    message=f"Chroma healthy. Collection '{collection_name}' has {doc_count} documents.",
                    collection_count=collection_count,
                    document_count=doc_count,
                )
            except NotFoundError:
                return HealthCheckResult(
                    healthy=False,
                    message=f"Collection '{collection_name}' not found",
                    collection_count=collection_count,
                )
            except Exception as e:
                logger.exception("Unexpected error checking collection '%s'", collection_name)
                return HealthCheckResult(
                    healthy=False,
                    message=f"Error checking collection '{collection_name}': {e}",
                    collection_count=collection_count,
                )

        return HealthCheckResult(
            healthy=True,
            message=f"Chroma healthy. {collection_count} collection(s) available.",
            collection_count=collection_count,
        )

    except Exception as e:
        logger.exception("Chroma health check failed")
        return HealthCheckResult(
            healthy=False,
            message=f"Chroma health check failed: {e}",
        )


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
