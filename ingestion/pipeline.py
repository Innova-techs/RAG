from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .chunker import chunk_document
from .loader import DocumentLoader, UnsupportedDocumentError, discover_documents
from .storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 80
    fail_fast: bool = False


@dataclass
class PipelineResult:
    processed: int
    skipped: int
    failed: int
    chunk_count: int
    failures: List[str]


class IngestionPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.loader = DocumentLoader(config.input_dir)
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
