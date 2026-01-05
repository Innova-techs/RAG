from __future__ import annotations

import logging
import random
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


# Required metadata fields for Chroma chunks (Issue #14)
REQUIRED_METADATA_FIELDS = frozenset({
    "doc_id",
    "source_path",
    "chunk_index",
    "timestamp",
})


@dataclass
class MetadataVerificationResult:
    """Result of metadata verification check."""

    verified_chunks: int = 0
    missing_fields: int = 0
    field_coverage: dict = None

    def __post_init__(self):
        if self.field_coverage is None:
            self.field_coverage = {}


@dataclass
class IndexingResult:
    indexed_docs: int
    indexed_chunks: int
    skipped_docs: int
    failed_chunks: int = 0
    verification: MetadataVerificationResult = None


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

    def verify_metadata(self, sample_size: int = 100) -> MetadataVerificationResult:
        """Verify metadata integrity of indexed chunks.

        Samples chunks from the collection and checks for required metadata fields.

        Args:
            sample_size: Number of chunks to sample for verification.

        Returns:
            MetadataVerificationResult with field coverage statistics.
        """
        # Get sample of indexed chunks
        total_count = self.collection.count()
        if total_count == 0:
            logger.warning("Collection is empty, nothing to verify.")
            return MetadataVerificationResult()

        # Get all chunk IDs for random sampling
        all_ids_result = self.collection.get(include=[])
        all_ids = all_ids_result.get("ids", [])

        if not all_ids:
            logger.warning("No chunk IDs found in collection.")
            return MetadataVerificationResult()

        # Randomly sample IDs to avoid insertion-order bias
        actual_sample = min(sample_size, len(all_ids))
        sampled_ids = random.sample(all_ids, actual_sample)

        result = self.collection.get(
            ids=sampled_ids,
            include=["metadatas"],
        )

        metadatas = result.get("metadatas", [])
        if not metadatas:
            return MetadataVerificationResult()

        # Track field presence
        field_counts: dict = {}
        chunks_with_missing = 0

        for metadata in metadatas:
            has_all_required = True
            for field in REQUIRED_METADATA_FIELDS:
                if field not in field_counts:
                    field_counts[field] = 0
                if field in metadata and metadata[field] not in (None, ""):
                    field_counts[field] += 1
                else:
                    has_all_required = False

            # Also track optional fields (page, section)
            for field in ("page", "section"):
                if field not in field_counts:
                    field_counts[field] = 0
                if field in metadata and metadata[field] not in (None, ""):
                    field_counts[field] += 1

            if not has_all_required:
                chunks_with_missing += 1

        # Calculate coverage percentages
        field_coverage = {
            field: round(count / len(metadatas) * 100, 1)
            for field, count in field_counts.items()
        }

        verification_result = MetadataVerificationResult(
            verified_chunks=len(metadatas),
            missing_fields=chunks_with_missing,
            field_coverage=field_coverage,
        )

        logger.info(
            "Metadata verification: %d chunks randomly sampled from %d total, %d with missing required fields.",
            verification_result.verified_chunks,
            total_count,
            verification_result.missing_fields,
        )
        for field, coverage in field_coverage.items():
            status = "required" if field in REQUIRED_METADATA_FIELDS else "optional"
            logger.info("  %s (%s): %.1f%% coverage", field, status, coverage)

        return verification_result
