"""Unit tests for ingestion idempotency (Issue #10)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.storage import StorageManager
from ingestion.pipeline import IngestionPipeline, PipelineConfig, PipelineResult
from ingestion.models import Document, DocumentChunk


class TestContentHashIdempotency:
    """Tests for content hash based idempotency."""

    def test_is_up_to_date_returns_true_for_same_hash(self, tmp_path: Path):
        """Test that is_up_to_date returns True when hash matches."""
        storage = StorageManager(tmp_path)

        # Manually add an entry to manifest
        storage._manifest["test-doc"] = {
            "doc_id": "test-doc",
            "content_hash": "abc123",
            "chunk_count": 5,
        }

        assert storage.is_up_to_date("test-doc", "abc123") is True

    def test_is_up_to_date_returns_false_for_different_hash(self, tmp_path: Path):
        """Test that is_up_to_date returns False when hash differs."""
        storage = StorageManager(tmp_path)

        storage._manifest["test-doc"] = {
            "doc_id": "test-doc",
            "content_hash": "abc123",
            "chunk_count": 5,
        }

        assert storage.is_up_to_date("test-doc", "xyz789") is False

    def test_is_up_to_date_returns_false_for_new_doc(self, tmp_path: Path):
        """Test that is_up_to_date returns False for new documents."""
        storage = StorageManager(tmp_path)

        assert storage.is_up_to_date("new-doc", "abc123") is False

    def test_manifest_persists_across_instances(self, tmp_path: Path):
        """Test that manifest is persisted and reloaded correctly."""
        # First instance writes
        storage1 = StorageManager(tmp_path)
        storage1._manifest["test-doc"] = {
            "doc_id": "test-doc",
            "content_hash": "abc123",
        }
        storage1._write_manifest()

        # Second instance reads
        storage2 = StorageManager(tmp_path)
        assert storage2.is_up_to_date("test-doc", "abc123") is True


class TestPersistDocumentUpdates:
    """Tests for document persistence and updates."""

    def test_persist_document_creates_chunk_file(self, tmp_path: Path):
        """Test that persist_document creates chunk JSONL file."""
        storage = StorageManager(tmp_path)

        doc = Document(
            doc_id="test-doc",
            path=Path("/fake/doc.txt"),
            source_type="txt",
            text="Test content",
            metadata={"source_path": "/fake/doc.txt", "relative_path": "doc.txt"},
        )
        chunks = [
            DocumentChunk(
                chunk_id="test-doc::chunk-0000",
                doc_id="test-doc",
                chunk_index=0,
                text="Test content",
                token_estimate=10,
                metadata={},
            )
        ]

        storage.persist_document(doc, chunks, "hash123")

        chunk_file = tmp_path / "chunks" / "test-doc.jsonl"
        assert chunk_file.exists()

        # Verify content
        with chunk_file.open() as f:
            line = f.readline()
            data = json.loads(line)
            assert data["chunk_id"] == "test-doc::chunk-0000"

    def test_persist_document_updates_manifest(self, tmp_path: Path):
        """Test that persist_document updates manifest with new hash."""
        storage = StorageManager(tmp_path)

        doc = Document(
            doc_id="test-doc",
            path=Path("/fake/doc.txt"),
            source_type="txt",
            text="Test content",
            metadata={"source_path": "/fake/doc.txt"},
        )

        # First persist
        storage.persist_document(doc, [], "hash_v1")
        assert storage._manifest["test-doc"]["content_hash"] == "hash_v1"

        # Second persist with different hash (simulating update)
        storage.persist_document(doc, [], "hash_v2")
        assert storage._manifest["test-doc"]["content_hash"] == "hash_v2"

    def test_persist_document_overwrites_existing_chunks(self, tmp_path: Path):
        """Test that re-persisting overwrites chunk file."""
        storage = StorageManager(tmp_path)

        doc = Document(
            doc_id="test-doc",
            path=Path("/fake/doc.txt"),
            source_type="txt",
            text="Test content",
            metadata={},
        )

        # First persist with 2 chunks
        chunks_v1 = [
            DocumentChunk("test-doc::chunk-0000", "test-doc", 0, "Chunk 1", 5, {}),
            DocumentChunk("test-doc::chunk-0001", "test-doc", 1, "Chunk 2", 5, {}),
        ]
        storage.persist_document(doc, chunks_v1, "hash_v1")

        # Second persist with 1 chunk
        chunks_v2 = [
            DocumentChunk("test-doc::chunk-0000", "test-doc", 0, "Updated", 5, {}),
        ]
        storage.persist_document(doc, chunks_v2, "hash_v2")

        # Verify only 1 chunk in file
        chunk_file = tmp_path / "chunks" / "test-doc.jsonl"
        with chunk_file.open() as f:
            lines = f.readlines()
            assert len(lines) == 1
            assert "Updated" in lines[0]


class TestOrphanedDocumentCleanup:
    """Tests for orphaned document cleanup functionality."""

    def test_find_orphaned_docs_detects_missing_files(self, tmp_path: Path):
        """Test that find_orphaned_docs detects docs with deleted source files."""
        storage = StorageManager(tmp_path)

        # Add doc with non-existent source path
        storage._manifest["orphan-doc"] = {
            "doc_id": "orphan-doc",
            "source_path": "/nonexistent/path/doc.txt",
            "content_hash": "abc123",
        }
        storage._write_manifest()

        orphaned = storage.find_orphaned_docs([])
        assert "orphan-doc" in orphaned

    def test_find_orphaned_docs_excludes_existing_files(self, tmp_path: Path):
        """Test that find_orphaned_docs excludes docs with existing source files."""
        storage = StorageManager(tmp_path)

        # Create a real file
        source_file = tmp_path / "existing.txt"
        source_file.write_text("content")

        storage._manifest["existing-doc"] = {
            "doc_id": "existing-doc",
            "source_path": str(source_file),
            "content_hash": "abc123",
        }
        storage._write_manifest()

        orphaned = storage.find_orphaned_docs([str(source_file)])
        assert "existing-doc" not in orphaned

    def test_cleanup_orphaned_docs_removes_manifest_entry(self, tmp_path: Path):
        """Test that cleanup_orphaned_docs removes from manifest."""
        storage = StorageManager(tmp_path)

        storage._manifest["orphan-doc"] = {
            "doc_id": "orphan-doc",
            "source_path": "/nonexistent/path.txt",
        }
        storage._write_manifest()

        cleaned = storage.cleanup_orphaned_docs(["orphan-doc"])

        assert cleaned == 1
        assert "orphan-doc" not in storage._manifest

    def test_cleanup_orphaned_docs_deletes_chunk_file(self, tmp_path: Path):
        """Test that cleanup_orphaned_docs deletes chunk file."""
        storage = StorageManager(tmp_path)

        # Create chunk file
        chunk_file = storage.chunks_dir / "orphan-doc.jsonl"
        chunk_file.write_text('{"chunk_id": "orphan-doc::chunk-0000"}')

        storage._manifest["orphan-doc"] = {
            "doc_id": "orphan-doc",
            "source_path": "/nonexistent/path.txt",
        }

        storage.cleanup_orphaned_docs(["orphan-doc"])

        assert not chunk_file.exists()

    def test_cleanup_handles_missing_chunk_file(self, tmp_path: Path):
        """Test that cleanup works even if chunk file doesn't exist."""
        storage = StorageManager(tmp_path)

        storage._manifest["orphan-doc"] = {
            "doc_id": "orphan-doc",
            "source_path": "/nonexistent/path.txt",
        }

        # Should not raise even though chunk file doesn't exist
        cleaned = storage.cleanup_orphaned_docs(["orphan-doc"])
        assert cleaned == 1


class TestPipelineIdempotency:
    """Tests for pipeline-level idempotency behavior."""

    def test_pipeline_skips_unchanged_documents(self, tmp_path: Path):
        """Test that pipeline skips documents with unchanged content hash."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        # Create a test document
        doc_file = input_dir / "test.txt"
        doc_file.write_text("Test content")

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            chunk_size_tokens=400,
        )

        pipeline = IngestionPipeline(config)

        # First run - should process
        result1 = pipeline.run()
        assert result1.processed == 1
        assert result1.skipped == 0

        # Second run - should skip (same content)
        result2 = pipeline.run()
        assert result2.processed == 0
        assert result2.skipped == 1

    def test_pipeline_reprocesses_changed_documents(self, tmp_path: Path):
        """Test that pipeline reprocesses documents when content changes."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        # Create a test document
        doc_file = input_dir / "test.txt"
        doc_file.write_text("Original content")

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            chunk_size_tokens=400,
        )

        pipeline = IngestionPipeline(config)

        # First run
        result1 = pipeline.run()
        assert result1.processed == 1

        # Modify the document
        doc_file.write_text("Modified content - different hash")

        # Second run - should reprocess
        result2 = pipeline.run()
        assert result2.processed == 1
        assert result2.skipped == 0

    def test_pipeline_cleanup_removes_orphaned_docs(self, tmp_path: Path):
        """Test that pipeline with cleanup removes orphaned documents."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        # Create two documents
        doc1 = input_dir / "doc1.txt"
        doc2 = input_dir / "doc2.txt"
        doc1.write_text("Document 1")
        doc2.write_text("Document 2")

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            chunk_size_tokens=400,
            cleanup_deleted=True,
        )

        pipeline = IngestionPipeline(config)

        # First run - process both
        result1 = pipeline.run()
        assert result1.processed == 2

        # Delete one document
        doc2.unlink()

        # Second run with cleanup
        result2 = pipeline.run()
        assert result2.cleaned_up == 1

        # Verify manifest only has doc1
        manifest = json.loads((output_dir / "manifest.json").read_text())
        assert len(manifest) == 1
        assert "doc2-txt" not in manifest or "doc1-txt" in manifest


class TestManifestDocIds:
    """Tests for manifest document ID retrieval."""

    def test_get_manifest_doc_ids_returns_all_ids(self, tmp_path: Path):
        """Test that get_manifest_doc_ids returns all document IDs."""
        storage = StorageManager(tmp_path)

        storage._manifest = {
            "doc-1": {"doc_id": "doc-1"},
            "doc-2": {"doc_id": "doc-2"},
            "doc-3": {"doc_id": "doc-3"},
        }

        doc_ids = storage.get_manifest_doc_ids()
        assert set(doc_ids) == {"doc-1", "doc-2", "doc-3"}

    def test_get_manifest_doc_ids_empty_manifest(self, tmp_path: Path):
        """Test that get_manifest_doc_ids returns empty list for empty manifest."""
        storage = StorageManager(tmp_path)

        doc_ids = storage.get_manifest_doc_ids()
        assert doc_ids == []
