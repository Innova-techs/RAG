from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .chunker import chunk_document
from .loader import DocumentLoader, UnsupportedDocumentError, discover_documents
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
        chunk_overlap_tokens: Overlapping tokens between chunks.
        fail_fast: Stop on first failure instead of continuing.
        normalization_config: Optional configuration for text normalization.
    """

    input_dir: Path
    output_dir: Path
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 80
    fail_fast: bool = False
    normalization_config: Optional[NormalizationConfig] = field(default=None)


@dataclass
class PipelineResult:
    processed: int
    skipped: int
    failed: int
    chunk_count: int
    failures: List[str]


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

    def run(self) -> PipelineResult:
        documents = discover_documents(self.config.input_dir)
        processed = skipped = failed = chunk_total = 0
        failures: List[str] = []

        if not documents:
            logger.warning("No documents found under %s", self.config.input_dir)
            return PipelineResult(0, 0, 0, 0, [])

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
                    chunk_overlap_tokens=self.config.chunk_overlap_tokens,
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
                failures.append(f"{path}: {exc}")
                logger.error("Unsupported document: %s", exc)
                if self.config.fail_fast:
                    raise
            except Exception as exc:  # pylint: disable=broad-except
                failed += 1
                failures.append(f"{path}: {exc}")
                logger.exception("Failed to process %s", path)
                if self.config.fail_fast:
                    raise

        return PipelineResult(processed, skipped, failed, chunk_total, failures)
