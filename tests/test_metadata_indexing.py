"""Unit tests for chunk metadata indexing functionality (Issue #14)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.chunker import (
    _extract_page_from_text,
    _extract_section_from_text,
    _strip_page_markers,
    chunk_document,
)
from ingestion.models import Document


class TestPageMarkerExtraction:
    """Tests for page marker detection and extraction."""

    def test_extract_page_from_text_simple(self):
        """Test extracting page number from text with marker."""
        text = "[PAGE:1]\nThis is content from page 1."
        assert _extract_page_from_text(text) == 1

    def test_extract_page_from_text_multidigit(self):
        """Test extracting multi-digit page numbers."""
        text = "[PAGE:123]\nContent from page 123."
        assert _extract_page_from_text(text) == 123

    def test_extract_page_from_text_no_marker(self):
        """Test text without page marker returns None."""
        text = "This is plain text without any page markers."
        assert _extract_page_from_text(text) is None

    def test_extract_page_from_text_multiple_markers(self):
        """Test that first page marker is returned."""
        text = "[PAGE:1]\nContent\n\n[PAGE:2]\nMore content"
        assert _extract_page_from_text(text) == 1

    def test_extract_page_from_text_inline_marker(self):
        """Test page marker must be on its own line."""
        text = "Text before [PAGE:5] text after"
        # Should not match inline markers
        assert _extract_page_from_text(text) is None

    def test_strip_page_markers_simple(self):
        """Test stripping page markers from text."""
        text = "[PAGE:1]\nThis is the content."
        result = _strip_page_markers(text)
        assert "[PAGE:1]" not in result
        assert "This is the content." in result

    def test_strip_page_markers_multiple(self):
        """Test stripping multiple page markers."""
        text = "[PAGE:1]\nPage 1 content.\n\n[PAGE:2]\nPage 2 content."
        result = _strip_page_markers(text)
        assert "[PAGE:" not in result
        assert "Page 1 content" in result
        assert "Page 2 content" in result

    def test_strip_page_markers_empty(self):
        """Test stripping from text without markers."""
        text = "No markers here."
        result = _strip_page_markers(text)
        assert result == "No markers here."


class TestSectionHeaderExtraction:
    """Tests for markdown section header detection."""

    def test_extract_section_h1(self):
        """Test extracting H1 header."""
        text = "# Introduction\nSome content here."
        assert _extract_section_from_text(text) == "Introduction"

    def test_extract_section_h2(self):
        """Test extracting H2 header."""
        text = "## Getting Started\nContent follows."
        assert _extract_section_from_text(text) == "Getting Started"

    def test_extract_section_h3(self):
        """Test extracting H3 header."""
        text = "### Implementation Details\nDetails here."
        assert _extract_section_from_text(text) == "Implementation Details"

    def test_extract_section_multiple_headers(self):
        """Test that last header is returned (most recent context)."""
        text = "# Chapter 1\nContent\n\n## Section A\nMore content"
        assert _extract_section_from_text(text) == "Section A"

    def test_extract_section_no_header(self):
        """Test text without headers returns None."""
        text = "This is plain text without any headers."
        assert _extract_section_from_text(text) is None

    def test_extract_section_hash_in_text(self):
        """Test that hash in regular text is not detected as header."""
        text = "Use the # symbol for comments in Python."
        assert _extract_section_from_text(text) is None

    def test_extract_section_h6(self):
        """Test extracting H6 header."""
        text = "###### Deep Nested Section\nContent."
        assert _extract_section_from_text(text) == "Deep Nested Section"


class TestChunkMetadataPage:
    """Tests for page metadata in chunks."""

    def _create_pdf_document(self, pages: list[str], doc_id: str = "test-pdf") -> Document:
        """Helper to create a document with page markers like PDF loader outputs."""
        text_parts = []
        for i, page_content in enumerate(pages, 1):
            text_parts.append(f"[PAGE:{i}]\n{page_content}")
        return Document(
            doc_id=doc_id,
            path=Path("/fake/path/doc.pdf"),
            source_type="pdf",
            text="\n\n".join(text_parts),
            metadata={"page_count": len(pages)},
        )

    def test_chunk_contains_page_metadata(self):
        """Test that chunks from PDF text contain page metadata."""
        doc = self._create_pdf_document(["Page one content.", "Page two content."])
        chunks = chunk_document(doc, chunk_size_tokens=400)
        assert len(chunks) >= 1
        # Chunk should have page metadata (either 1 or 2 depending on content)
        assert "page" in chunks[0].metadata
        assert chunks[0].metadata["page"] in (1, 2)

    def test_chunk_page_tracking_across_chunks(self):
        """Test that page context is maintained across chunks."""
        # Create pages with more content to force multiple chunks
        pages = [
            "First page with substantial content. " * 20,
            "Second page with substantial content. " * 20,
        ]
        doc = self._create_pdf_document(pages)
        chunks = chunk_document(doc, chunk_size_tokens=50)

        # All chunks from first page should have page=1
        # Chunks after page marker should have page=2
        page_numbers = [c.metadata.get("page") for c in chunks if "page" in c.metadata]
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_chunk_text_has_markers_stripped(self):
        """Test that page markers are removed from chunk text."""
        doc = self._create_pdf_document(["Content for testing."])
        chunks = chunk_document(doc, chunk_size_tokens=400)
        assert len(chunks) >= 1
        # Chunk text should not contain page markers
        assert "[PAGE:" not in chunks[0].text


class TestChunkMetadataSection:
    """Tests for section metadata in chunks."""

    def _create_document(self, text: str, doc_id: str = "test-doc") -> Document:
        return Document(
            doc_id=doc_id,
            path=Path("/fake/path/doc.md"),
            source_type="md",
            text=text,
            metadata={},
        )

    def test_chunk_contains_section_metadata(self):
        """Test that chunks from markdown contain section metadata."""
        text = "# Introduction\n\nThis is the introduction content."
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=400)
        assert len(chunks) >= 1
        assert "section" in chunks[0].metadata
        assert chunks[0].metadata["section"] == "Introduction"

    def test_chunk_section_tracking_across_chunks(self):
        """Test that section context is maintained across chunks."""
        text = """# Chapter 1

First chapter content that is long enough. """ + "More content. " * 50 + """

## Section 1.1

Section content that is also long enough. """ + "More section content. " * 50
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=50)

        # Should have chunks with different section values
        sections = [c.metadata.get("section") for c in chunks if "section" in c.metadata]
        assert "Chapter 1" in sections or "Section 1.1" in sections

    def test_chunk_no_section_for_plain_text(self):
        """Test that chunks from plain text may not have section."""
        text = "This is plain text without any markdown headers."
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=400)
        assert len(chunks) >= 1
        # Section should not be present or should be None
        assert chunks[0].metadata.get("section") is None


class TestMetadataVerification:
    """Tests for metadata verification functionality."""

    def test_verify_metadata_empty_collection(self):
        """Test verification with empty collection."""
        from indexing.pipeline import ChromaIndexingPipeline, IndexingConfig, MetadataVerificationResult

        with patch.object(ChromaIndexingPipeline, "__init__", lambda x, y: None):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.collection = MagicMock()
            pipeline.collection.count.return_value = 0

            result = pipeline.verify_metadata()
            assert isinstance(result, MetadataVerificationResult)
            assert result.verified_chunks == 0

    def test_verify_metadata_with_chunks(self):
        """Test verification with indexed chunks."""
        from indexing.pipeline import ChromaIndexingPipeline, MetadataVerificationResult

        with patch.object(ChromaIndexingPipeline, "__init__", lambda x, y: None):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.collection = MagicMock()
            pipeline.collection.count.return_value = 10

            # Mock get response with complete metadata
            pipeline.collection.get.return_value = {
                "metadatas": [
                    {
                        "doc_id": "doc-1",
                        "source_path": "/path/to/doc",
                        "chunk_index": 0,
                        "timestamp": "2024-01-01T00:00:00Z",
                        "page": 1,
                        "section": "Introduction",
                    }
                    for _ in range(10)
                ]
            }

            result = pipeline.verify_metadata(sample_size=10)
            assert isinstance(result, MetadataVerificationResult)
            assert result.verified_chunks == 10
            assert result.missing_fields == 0
            # All required fields should have 100% coverage
            assert result.field_coverage["doc_id"] == 100.0
            assert result.field_coverage["source_path"] == 100.0

    def test_verify_metadata_missing_fields(self):
        """Test verification detects missing required fields."""
        from indexing.pipeline import ChromaIndexingPipeline, MetadataVerificationResult

        with patch.object(ChromaIndexingPipeline, "__init__", lambda x, y: None):
            pipeline = ChromaIndexingPipeline.__new__(ChromaIndexingPipeline)
            pipeline.collection = MagicMock()
            pipeline.collection.count.return_value = 5

            # Mock get response with incomplete metadata
            pipeline.collection.get.return_value = {
                "metadatas": [
                    {"doc_id": "doc-1"},  # Missing required fields
                    {"doc_id": "doc-2", "source_path": "/path", "chunk_index": 0, "timestamp": "2024-01-01"},
                    {"doc_id": "doc-3"},  # Missing required fields
                    {"doc_id": "doc-4", "source_path": "/path", "chunk_index": 1, "timestamp": "2024-01-01"},
                    {"doc_id": "doc-5"},  # Missing required fields
                ]
            }

            result = pipeline.verify_metadata(sample_size=5)
            assert result.verified_chunks == 5
            assert result.missing_fields == 3  # 3 chunks missing required fields


class TestPDFLoaderPageMarkers:
    """Tests for page marker insertion in PDF loader."""

    def test_load_pdf_adds_page_markers(self):
        """Test that PDF loader adds page markers to output."""
        from unittest.mock import MagicMock, patch

        # Mock PyPDF2
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock(), MagicMock()]
        mock_reader.pages[0].extract_text.return_value = "Page 1 content"
        mock_reader.pages[1].extract_text.return_value = "Page 2 content"
        mock_reader.is_encrypted = False
        mock_reader.metadata = None

        with patch("PyPDF2.PdfReader", return_value=mock_reader):
            from ingestion.loader import load_pdf

            text, metadata = load_pdf(Path("/fake/test.pdf"))

            assert "[PAGE:1]" in text
            assert "[PAGE:2]" in text
            assert "Page 1 content" in text
            assert "Page 2 content" in text
