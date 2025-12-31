from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from chromadb.api.types import Documents, Embeddings, IDs, Metadatas

from .chroma_store import get_collection
from .dataset import iter_chunk_records, load_manifest
from .embeddings import EmbeddingConfig, EmbeddingError, EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class IndexingConfig:
    processed_dir: Path
    chroma_dir: Path
    collection_name: str = "pilot-docs"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 32
    doc_filter: Optional[Sequence[str]] = None


@dataclass
class IndexingResult:
    indexed_docs: int
    indexed_chunks: int
    skipped_docs: int
    failed_chunks: int = 0


class ChromaIndexingPipeline:
    def __init__(self, config: IndexingConfig):
        self.config = config

        # Initialize embedding service with retry logic
        embedding_config = EmbeddingConfig(model_name=config.embedding_model_name)
        self.embedding_service = EmbeddingService(embedding_config)

        # Create collection without embedding function (we pre-compute embeddings)
        self.collection = get_collection(
            config.chroma_dir,
            config.collection_name,
            embedding_function=None,
        )

        self.manifest_path = config.processed_dir / "manifest.json"
        self.chunks_dir = config.processed_dir / "chunks"

    def run(self) -> IndexingResult:
        manifest = load_manifest(self.manifest_path)
        available_doc_ids = set(manifest.keys())

        if self.config.doc_filter:
            doc_ids = [doc_id for doc_id in self.config.doc_filter if doc_id in available_doc_ids]
            missing = set(self.config.doc_filter) - available_doc_ids
            for doc_id in sorted(missing):
                logger.warning("Requested doc_id %s not in manifest; skipping.", doc_id)
        else:
            doc_ids = sorted(available_doc_ids)

        indexed_docs = 0
        indexed_chunks = 0
        skipped_docs = 0
        failed_chunks = 0

        for doc_id in doc_ids:
            records = list(iter_chunk_records(manifest, self.chunks_dir, [doc_id]))
            if not records:
                skipped_docs += 1
                logger.warning("No chunk records found for %s; skipping.", doc_id)
                continue

            logger.info("Re-indexing %s (%d chunks).", doc_id, len(records))
            self.collection.delete(where={"doc_id": doc_id})
            success_count, fail_count = self._upsert_records(records)
            indexed_docs += 1
            indexed_chunks += success_count
            failed_chunks += fail_count
            if fail_count > 0:
                logger.warning(
                    "Indexed %s: %d chunks succeeded, %d failed (collection=%s).",
                    doc_id,
                    success_count,
                    fail_count,
                    self.config.collection_name,
                )
            else:
                logger.info(
                    "Indexed %s: %d chunks (collection=%s).",
                    doc_id,
                    success_count,
                    self.config.collection_name,
                )

        return IndexingResult(
            indexed_docs=indexed_docs,
            indexed_chunks=indexed_chunks,
            skipped_docs=skipped_docs,
            failed_chunks=failed_chunks,
        )

    def _upsert_records(self, records) -> Tuple[int, int]:
        """Upsert records in batches with error handling.

        Pre-computes embeddings using EmbeddingService with retry logic,
        then upserts to Chroma.

        Returns:
            Tuple of (success_count, fail_count).
        """
        batch_size = max(1, self.config.batch_size)
        success_count = 0
        fail_count = 0

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            ids: IDs = [record.chunk_id for record in batch]
            documents: Documents = [record.text for record in batch]
            metadatas: Metadatas = [record.metadata for record in batch]

            try:
                # Pre-compute embeddings with retry logic
                embeddings: Embeddings = self.embedding_service.embed_batch(documents)
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
                success_count += len(batch)
            except EmbeddingError as exc:
                fail_count += len(batch)
                logger.error(
                    "Failed to embed batch of %d chunks (ids=%s...): %s",
                    len(batch),
                    ids[0] if ids else "none",
                    exc,
                )
            except Exception as exc:
                fail_count += len(batch)
                logger.error(
                    "Failed to upsert batch of %d chunks (ids=%s...): %s",
                    len(batch),
                    ids[0] if ids else "none",
                    exc,
                )

        return success_count, fail_count
