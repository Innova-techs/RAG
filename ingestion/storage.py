from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List

from .models import Document, DocumentChunk, FailureInfo

if TYPE_CHECKING:
    from .pipeline import PipelineResult

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.chunks_dir = output_root / "chunks"
        self.logs_dir = output_root / "logs"
        self.manifest_path = output_root / "manifest.json"
        self.failures_path = output_root / "failures.json"
        self.report_path = output_root / "ingestion-report.json"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Dict]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Manifest corrupted; recreating.")
        return {}

    def _write_manifest(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_up_to_date(self, doc_id: str, content_hash: str) -> bool:
        entry = self._manifest.get(doc_id)
        return bool(entry and entry.get("content_hash") == content_hash)

    def persist_document(
        self,
        document: Document,
        chunks: Iterable[DocumentChunk],
        content_hash: str,
    ) -> None:
        chunk_list = list(chunks)
        chunk_file = self.chunks_dir / f"{document.doc_id}.jsonl"
        with chunk_file.open("w", encoding="utf-8") as fp:
            for chunk in chunk_list:
                fp.write(json.dumps(chunk.to_dict(), ensure_ascii=False))
                fp.write("\n")

        manifest_entry = {
            "doc_id": document.doc_id,
            "content_hash": content_hash,
            "chunk_count": len(chunk_list),
            "source_path": document.metadata.get("source_path"),
            "relative_path": document.metadata.get("relative_path"),
            "file_extension": document.metadata.get("file_extension"),
            "last_ingested": datetime.utcnow().isoformat() + "Z",
            "metadata": document.metadata,
        }
        self._manifest[document.doc_id] = manifest_entry
        self._write_manifest()

    def save_failures(self, failures: List[FailureInfo]) -> None:
        """Save failure information to failures.json.

        Args:
            failures: List of FailureInfo objects to persist.
        """
        data = [f.to_dict() for f in failures]
        self.failures_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if failures:
            logger.info("Saved %d failure(s) to %s", len(failures), self.failures_path)

    def load_failures(self) -> List[FailureInfo]:
        """Load failure information from failures.json.

        Returns:
            List of FailureInfo objects from previous runs.
        """
        if not self.failures_path.exists():
            return []
        try:
            data = json.loads(self.failures_path.read_text(encoding="utf-8"))
            return [FailureInfo.from_dict(item) for item in data]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load failures.json: %s", exc)
            return []

    def clear_failure(self, source_path: str) -> None:
        """Remove a specific failure entry after successful retry.

        Args:
            source_path: Path of the document that was successfully processed.
        """
        failures = self.load_failures()
        updated = [f for f in failures if f.source_path != source_path]
        if len(updated) != len(failures):
            self.save_failures(updated)
            logger.info("Cleared failure entry for %s", source_path)

    def save_report(self, result: "PipelineResult") -> None:
        """Save ingestion report to ingestion-report.json.

        Args:
            result: PipelineResult containing run statistics.
        """
        report = {
            "run_timestamp": result.start_time,
            "end_timestamp": result.end_time,
            "duration_seconds": result.duration_seconds,
            "processed": result.processed,
            "skipped": result.skipped,
            "failed": result.failed,
            "cleaned_up": result.cleaned_up,
            "total_chunks": result.chunk_count,
            "failures": [f.to_dict() for f in result.failures],
        }
        self.report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Saved ingestion report to %s", self.report_path)

    def find_orphaned_docs(self, current_source_paths: List[str]) -> List[str]:
        """Find documents in manifest whose source files no longer exist.

        Args:
            current_source_paths: List of current source file paths.

        Returns:
            List of doc_ids that are orphaned (source file deleted).
        """
        current_paths_set = set(current_source_paths)
        orphaned = []

        for doc_id, entry in self._manifest.items():
            source_path = entry.get("source_path")
            if source_path and source_path not in current_paths_set:
                # Check if file actually exists on disk
                if not Path(source_path).exists():
                    orphaned.append(doc_id)

        return orphaned

    def cleanup_orphaned_docs(self, doc_ids: List[str]) -> int:
        """Remove orphaned documents from manifest and delete their chunk files.

        Args:
            doc_ids: List of doc_ids to remove.

        Returns:
            Number of documents cleaned up.
        """
        cleaned = 0
        for doc_id in doc_ids:
            if doc_id in self._manifest:
                # Remove chunk file
                chunk_file = self.chunks_dir / f"{doc_id}.jsonl"
                if chunk_file.exists():
                    chunk_file.unlink()
                    logger.info("Deleted chunk file: %s", chunk_file)

                # Remove from manifest
                del self._manifest[doc_id]
                cleaned += 1
                logger.info("Removed orphaned document: %s", doc_id)

        if cleaned > 0:
            self._write_manifest()

        return cleaned

    def get_manifest_doc_ids(self) -> List[str]:
        """Get all document IDs in the manifest.

        Returns:
            List of doc_ids currently in manifest.
        """
        return list(self._manifest.keys())
