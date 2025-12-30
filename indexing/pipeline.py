from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from chromadb.api.types import Documents, IDs, Metadatas

from .chroma_store import get_collection
from .dataset import iter_chunk_records, load_manifest
from .embeddings import build_embedding_function

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


class ChromaIndexingPipeline:
    def __init__(self, config: IndexingConfig):
        self.config = config
        embedding_function = build_embedding_function(config.embedding_model_name)
        self.collection = get_collection(
            config.chroma_dir,
            config.collection_name,
            embedding_function,
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

        for doc_id in doc_ids:
            records = list(iter_chunk_records(manifest, self.chunks_dir, [doc_id]))
            if not records:
                skipped_docs += 1
                logger.warning("No chunk records found for %s; skipping.", doc_id)
                continue

            logger.info("Re-indexing %s (%d chunks).", doc_id, len(records))
            self.collection.delete(where={"doc_id": doc_id})
            chunk_count = self._upsert_records(records)
            indexed_docs += 1
            indexed_chunks += chunk_count
            logger.info(
                "Indexed %s: %d chunks (collection=%s).",
                doc_id,
                chunk_count,
                self.config.collection_name,
            )

        return IndexingResult(
            indexed_docs=indexed_docs,
            indexed_chunks=indexed_chunks,
            skipped_docs=skipped_docs,
        )

    def _upsert_records(self, records) -> int:
        batch_size = max(1, self.config.batch_size)
        chunk_total = 0
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            ids: IDs = [record.chunk_id for record in batch]
            documents: Documents = [record.text for record in batch]
            metadatas: Metadatas = [record.metadata for record in batch]
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            chunk_total += len(batch)
        return chunk_total
