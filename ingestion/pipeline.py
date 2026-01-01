from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .chunker import chunk_document
from .loader import DocumentLoader, UnsupportedDocumentError, discover_documents
from .models import FailureInfo
from .normalizer import NormalizationConfig, TextNormalizer
from .storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the ingestion pipeline.

    Attributes:
        input_dir: Directory containing source documents.
        output_dir: Directory for processed chunks and manifest.
        chunk_size_tokens: Target token count per chunk.
        chunk_overlap_percent: Overlap as percentage of chunk size (0.10-0.20).
        fail_fast: Stop on first failure instead of continuing.
        normalization_config: Optional configuration for text normalization.
        cleanup_deleted: Remove orphaned docs whose source files were deleted.
    """

    input_dir: Path
    output_dir: Path
    chunk_size_tokens: int = 400
    chunk_overlap_percent: float = 0.15
    fail_fast: bool = False
    normalization_config: Optional[NormalizationConfig] = field(default=None)
    cleanup_deleted: bool = False


@dataclass
class PipelineResult:
    processed: int
    skipped: int
    failed: int
    chunk_count: int
    failures: List[FailureInfo]
    start_time: str
    end_time: str
    duration_seconds: float
    cleaned_up: int = 0


class IngestionPipeline:
    """Pipeline for ingesting documents into normalized, chunked format.

    The pipeline discovers documents, loads them, optionally normalizes text,
    chunks the content, and persists the results.
    """

    def __init__(self, config: PipelineConfig):
        """Initialize the ingestion pipeline.

        Args:
            config: Pipeline configuration including paths and normalization settings.
        """
        self.config = config

        # Create normalizer if config provided
        normalizer: Optional[TextNormalizer] = None
        if config.normalization_config is not None:
            normalizer = TextNormalizer(config.normalization_config)

        self.loader = DocumentLoader(config.input_dir, normalizer=normalizer)
        self.storage = StorageManager(config.output_dir)

    def run(self, document_paths: Optional[List[Path]] = None) -> PipelineResult:
        """Run the ingestion pipeline.

        Args:
            document_paths: Optional list of specific document paths to process.
                           If None, discovers all documents in input_dir.

        Returns:
            PipelineResult with processing statistics and failure details.
        """
        start = datetime.utcnow()
        documents = document_paths or discover_documents(self.config.input_dir)
        processed = skipped = failed = chunk_total = 0
        failures: List[FailureInfo] = []

        if not documents:
            logger.warning("No documents found under %s", self.config.input_dir)
            end = datetime.utcnow()
            return PipelineResult(
                0, 0, 0, 0, [],
                start.isoformat() + "Z",
                end.isoformat() + "Z",
                (end - start).total_seconds(),
            )

        for path in documents:
            try:
                document, content_hash = self.loader.load(path)
                if self.storage.is_up_to_date(document.doc_id, content_hash):
                    skipped += 1
                    logger.info("Skipping %s (no changes detected)", path)
                    continue

                chunks = chunk_document(
                    document,
                    chunk_size_tokens=self.config.chunk_size_tokens,
                    chunk_overlap_percent=self.config.chunk_overlap_percent,
                )

                if not chunks:
                    skipped += 1
                    logger.warning("No chunks produced for %s", path)
                    continue

                self.storage.persist_document(document, chunks, content_hash)
                processed += 1
                chunk_total += len(chunks)
                logger.info(
                    "Processed %s -> %d chunks",
                    document.metadata.get("relative_path", document.doc_id),
                    len(chunks),
                )
            except UnsupportedDocumentError as exc:
                failed += 1
                failure = FailureInfo(
                    source_path=str(path),
                    doc_id=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback=traceback.format_exc(),
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                failures.append(failure)
                logger.error("Unsupported document: %s", exc)
                if self.config.fail_fast:
                    raise
            except Exception as exc:  # pylint: disable=broad-except
                failed += 1
                failure = FailureInfo(
                    source_path=str(path),
                    doc_id=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback=traceback.format_exc(),
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                failures.append(failure)
                logger.exception("Failed to process %s", path)
                if self.config.fail_fast:
                    raise

        # Cleanup orphaned documents if enabled
        cleaned_up = 0
        if self.config.cleanup_deleted:
            current_paths = [str(p.resolve()) for p in documents]
            orphaned = self.storage.find_orphaned_docs(current_paths)
            if orphaned:
                cleaned_up = self.storage.cleanup_orphaned_docs(orphaned)
                logger.info("Cleaned up %d orphaned document(s)", cleaned_up)

        end = datetime.utcnow()
        result = PipelineResult(
            processed,
            skipped,
            failed,
            chunk_total,
            failures,
            start.isoformat() + "Z",
            end.isoformat() + "Z",
            (end - start).total_seconds(),
            cleaned_up,
        )

        # Save failures and report
        self.storage.save_failures(failures)
        self.storage.save_report(result)

        return result
