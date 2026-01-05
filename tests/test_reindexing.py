"""Integration tests for re-indexing without duplicates (Story #16).

Tests verify:
- Deterministic chunk IDs enable upsert operations
- Re-indexing updates existing chunks without duplicates
- Orphaned chunks are removed when document changes
- Re-index operation is idempotent
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from indexing.dataset import iter_chunk_records, load_manifest
from indexing.models import ChunkRecord
from indexing.pipeline import ChromaIndexingPipeline, IndexingConfig


class TestDeterministicChunkIds:
    """Test that chunk IDs follow deterministic format."""

    def test_chunk_id_format(self, tmp_path: Path):
        """Chunk IDs follow {doc_id}::chunk-{index:04d} format."""
        doc_id = "abc123"
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()

        # Create manifest
        manifest = {
            doc_id: {
                "source_path": "/test/doc.pdf",
                "content_hash": "hash123",
            }
        }

        # Create chunk file with deterministic IDs
        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        chunks = [
            {
                "doc_id": doc_id,
                "chunk_id": f"{doc_id}::chunk-0000",
                "chunk_index": 0,
                "text": "First chunk",
            },
            {
                "doc_id": doc_id,
                "chunk_id": f"{doc_id}::chunk-0001",
                "chunk_index": 1,
                "text": "Second chunk",
            },
        ]
        with chunk_file.open("w") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk) + "\n")

        # Load and verify IDs
        records = list(iter_chunk_records(manifest, chunks_dir, [doc_id]))
        assert len(records) == 2
        assert records[0].chunk_id == f"{doc_id}::chunk-0000"
        assert records[1].chunk_id == f"{doc_id}::chunk-0001"

    def test_chunk_id_is_deterministic_across_loads(self, tmp_path: Path):
        """Same content produces same chunk ID on multiple loads."""
        doc_id = "test-doc"
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()

        manifest = {doc_id: {"source_path": "/test.md", "content_hash": "hash"}}

        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        chunk_data = {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}::chunk-0000",
            "chunk_index": 0,
            "text": "Test content",
        }
        chunk_file.write_text(json.dumps(chunk_data) + "\n")

        # Load twice and compare
        records1 = list(iter_chunk_records(manifest, chunks_dir, [doc_id]))
        records2 = list(iter_chunk_records(manifest, chunks_dir, [doc_id]))

        assert records1[0].chunk_id == records2[0].chunk_id


class TestUpsertOperation:
    """Test that upsert updates existing chunks without duplicates."""

    def test_upsert_updates_existing_chunks(self, tmp_path: Path):
        """Re-indexing same document updates chunks, not duplicates."""
        processed_dir = tmp_path / "processed"
        chroma_dir = tmp_path / "chroma"
        processed_dir.mkdir()
        chroma_dir.mkdir()
        chunks_dir = processed_dir / "chunks"
        chunks_dir.mkdir()

        doc_id = "doc1"

        # Create manifest
        manifest = {
            doc_id: {
                "source_path": "/test/doc.pdf",
                "content_hash": "hash_v1",
            }
        }
        (processed_dir / "manifest.json").write_text(json.dumps(manifest))

        # Create chunk file
        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        chunk_data = {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}::chunk-0000",
            "chunk_index": 0,
            "text": "Original content",
        }
        chunk_file.write_text(json.dumps(chunk_data) + "\n")

        config = IndexingConfig(
            processed_dir=processed_dir,
            chroma_dir=chroma_dir,
            collection_name="test-upsert",
        )

        # Mock embedding service
        with patch.object(
            ChromaIndexingPipeline,
            "__init__",
            lambda self, cfg: None,
        ):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.config = config
            pipeline.manifest_path = processed_dir / "manifest.json"
            pipeline.chunks_dir = chunks_dir

            # Create mock collection
            mock_collection = MagicMock()
            mock_collection.count.return_value = 1
            pipeline.collection = mock_collection

            # Mock embedding service
            mock_embed_service = MagicMock()
            mock_embed_service.embed_batch.return_value = [[0.1] * 384]
            pipeline.embedding_service = mock_embed_service

            # First index
            result1 = pipeline.run()
            assert result1.indexed_chunks == 1

            # Verify upsert was called (not add)
            mock_collection.upsert.assert_called()

            # Second index (same content)
            result2 = pipeline.run()
            assert result2.indexed_chunks == 1

            # Should delete before upsert to ensure clean state
            mock_collection.delete.assert_called()


class TestOrphanedChunkRemoval:
    """Test that orphaned chunks are removed when source changes."""

    def test_delete_called_before_upsert(self, tmp_path: Path):
        """Pipeline deletes old chunks before upserting new ones."""
        processed_dir = tmp_path / "processed"
        chroma_dir = tmp_path / "chroma"
        processed_dir.mkdir()
        chroma_dir.mkdir()
        chunks_dir = processed_dir / "chunks"
        chunks_dir.mkdir()

        doc_id = "orphan-test"

        # Create manifest
        manifest = {doc_id: {"source_path": "/test.pdf", "content_hash": "h1"}}
        (processed_dir / "manifest.json").write_text(json.dumps(manifest))

        # Create chunk file
        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        chunk_data = {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}::chunk-0000",
            "chunk_index": 0,
            "text": "Content",
        }
        chunk_file.write_text(json.dumps(chunk_data) + "\n")

        config = IndexingConfig(
            processed_dir=processed_dir,
            chroma_dir=chroma_dir,
            collection_name="test-orphan",
        )

        with patch.object(
            ChromaIndexingPipeline, "__init__", lambda self, cfg: None
        ):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.config = config
            pipeline.manifest_path = processed_dir / "manifest.json"
            pipeline.chunks_dir = chunks_dir

            mock_collection = MagicMock()
            pipeline.collection = mock_collection

            mock_embed_service = MagicMock()
            mock_embed_service.embed_batch.return_value = [[0.1] * 384]
            pipeline.embedding_service = mock_embed_service

            pipeline.run()

            # Verify delete was called with doc_id filter
            mock_collection.delete.assert_called_with(where={"doc_id": doc_id})


class TestIdempotentReindex:
    """Test that re-indexing is idempotent."""

    def test_multiple_reindex_produces_same_count(self, tmp_path: Path):
        """Running index multiple times produces same chunk count."""
        processed_dir = tmp_path / "processed"
        chroma_dir = tmp_path / "chroma"
        processed_dir.mkdir()
        chroma_dir.mkdir()
        chunks_dir = processed_dir / "chunks"
        chunks_dir.mkdir()

        doc_id = "idempotent-doc"

        manifest = {doc_id: {"source_path": "/test.pdf", "content_hash": "h"}}
        (processed_dir / "manifest.json").write_text(json.dumps(manifest))

        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        chunks = [
            {"doc_id": doc_id, "chunk_id": f"{doc_id}::chunk-{i:04d}", "chunk_index": i, "text": f"Chunk {i}"}
            for i in range(5)
        ]
        with chunk_file.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")

        config = IndexingConfig(
            processed_dir=processed_dir,
            chroma_dir=chroma_dir,
            collection_name="test-idempotent",
        )

        with patch.object(
            ChromaIndexingPipeline, "__init__", lambda self, cfg: None
        ):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.config = config
            pipeline.manifest_path = processed_dir / "manifest.json"
            pipeline.chunks_dir = chunks_dir

            mock_collection = MagicMock()
            pipeline.collection = mock_collection

            mock_embed_service = MagicMock()
            mock_embed_service.embed_batch.return_value = [[0.1] * 384 for _ in range(5)]
            pipeline.embedding_service = mock_embed_service

            # Run multiple times
            result1 = pipeline.run()
            result2 = pipeline.run()
            result3 = pipeline.run()

            # All should produce same count
            assert result1.indexed_chunks == 5
            assert result2.indexed_chunks == 5
            assert result3.indexed_chunks == 5

    def test_reindex_same_content_no_changes(self, tmp_path: Path):
        """Re-indexing unchanged content should upsert same data."""
        processed_dir = tmp_path / "processed"
        chroma_dir = tmp_path / "chroma"
        processed_dir.mkdir()
        chroma_dir.mkdir()
        chunks_dir = processed_dir / "chunks"
        chunks_dir.mkdir()

        doc_id = "stable-doc"

        manifest = {doc_id: {"source_path": "/doc.md", "content_hash": "stable"}}
        (processed_dir / "manifest.json").write_text(json.dumps(manifest))

        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        chunk_data = {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}::chunk-0000",
            "chunk_index": 0,
            "text": "Stable content that never changes",
        }
        chunk_file.write_text(json.dumps(chunk_data) + "\n")

        config = IndexingConfig(
            processed_dir=processed_dir,
            chroma_dir=chroma_dir,
            collection_name="test-stable",
        )

        with patch.object(
            ChromaIndexingPipeline, "__init__", lambda self, cfg: None
        ):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.config = config
            pipeline.manifest_path = processed_dir / "manifest.json"
            pipeline.chunks_dir = chunks_dir

            mock_collection = MagicMock()
            pipeline.collection = mock_collection

            mock_embed_service = MagicMock()
            mock_embed_service.embed_batch.return_value = [[0.1] * 384]
            pipeline.embedding_service = mock_embed_service

            pipeline.run()

            # Capture the upsert call args
            call1_args = mock_collection.upsert.call_args

            pipeline.run()

            call2_args = mock_collection.upsert.call_args

            # Same IDs should be upserted
            assert call1_args.kwargs["ids"] == call2_args.kwargs["ids"]


class TestSelectiveReindex:
    """Test selective re-indexing by doc_id."""

    def test_reindex_specific_doc_only(self, tmp_path: Path):
        """Can re-index specific document without touching others."""
        processed_dir = tmp_path / "processed"
        chroma_dir = tmp_path / "chroma"
        processed_dir.mkdir()
        chroma_dir.mkdir()
        chunks_dir = processed_dir / "chunks"
        chunks_dir.mkdir()

        # Create two documents
        manifest = {
            "doc1": {"source_path": "/doc1.pdf", "content_hash": "h1"},
            "doc2": {"source_path": "/doc2.pdf", "content_hash": "h2"},
        }
        (processed_dir / "manifest.json").write_text(json.dumps(manifest))

        for doc_id in ["doc1", "doc2"]:
            chunk_file = chunks_dir / f"{doc_id}.jsonl"
            chunk_data = {
                "doc_id": doc_id,
                "chunk_id": f"{doc_id}::chunk-0000",
                "chunk_index": 0,
                "text": f"Content for {doc_id}",
            }
            chunk_file.write_text(json.dumps(chunk_data) + "\n")

        # Configure to only index doc1
        config = IndexingConfig(
            processed_dir=processed_dir,
            chroma_dir=chroma_dir,
            collection_name="test-selective",
            doc_filter=["doc1"],
        )

        with patch.object(
            ChromaIndexingPipeline, "__init__", lambda self, cfg: None
        ):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.config = config
            pipeline.manifest_path = processed_dir / "manifest.json"
            pipeline.chunks_dir = chunks_dir

            mock_collection = MagicMock()
            pipeline.collection = mock_collection

            mock_embed_service = MagicMock()
            mock_embed_service.embed_batch.return_value = [[0.1] * 384]
            pipeline.embedding_service = mock_embed_service

            result = pipeline.run()

            # Only doc1 should be indexed
            assert result.indexed_docs == 1
            assert result.indexed_chunks == 1

            # Delete should only be called for doc1
            mock_collection.delete.assert_called_once_with(where={"doc_id": "doc1"})
