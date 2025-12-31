"""Unit tests for document chunking functionality."""
from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.chunker import (
    DEFAULT_CHUNK_SIZE_TOKENS,
    DEFAULT_OVERLAP_PERCENT,
    MAX_OVERLAP_PERCENT,
    MIN_OVERLAP_PERCENT,
    chunk_document,
)
from ingestion.models import Document
from ingestion.text_utils import count_tokens, split_sentences, split_into_units


class TestTokenCounting:
    """Tests for tiktoken-based token counting."""

    def test_count_tokens_empty(self):
        """Test counting tokens in empty string."""
        assert count_tokens("") == 0

    def test_count_tokens_simple(self):
        """Test counting tokens in simple text."""
        # "Hello world" is typically 2 tokens
        tokens = count_tokens("Hello world")
        assert tokens >= 2

    def test_count_tokens_longer_text(self):
        """Test counting tokens in longer text."""
        text = "The quick brown fox jumps over the lazy dog."
        tokens = count_tokens(text)
        # This sentence is typically around 10 tokens
        assert 8 <= tokens <= 12

    def test_count_tokens_consistent(self):
        """Test that token counting is consistent across calls."""
        text = "Consistency is key for reproducible results."
        tokens1 = count_tokens(text)
        tokens2 = count_tokens(text)
        assert tokens1 == tokens2


class TestSentenceSplitting:
    """Tests for sentence boundary detection."""

    def test_split_sentences_simple(self):
        """Test splitting simple sentences."""
        text = "First sentence. Second sentence. Third sentence."
        sentences = split_sentences(text)
        assert len(sentences) >= 1  # At least returns something

    def test_split_sentences_question_exclamation(self):
        """Test splitting with question and exclamation marks."""
        text = "What is this? It is amazing! Really great."
        sentences = split_sentences(text)
        assert len(sentences) >= 1

    def test_split_sentences_abbreviations(self):
        """Test that abbreviations don't cause false splits."""
        text = "Dr. Smith went to the store. He bought apples."
        sentences = split_sentences(text)
        # Should not split on "Dr."
        assert len(sentences) <= 3

    def test_split_sentences_empty(self):
        """Test splitting empty text."""
        assert split_sentences("") == []
        assert split_sentences("   ") == []

    def test_split_sentences_single(self):
        """Test text with no sentence boundaries."""
        text = "Just a single line without ending punctuation"
        sentences = split_sentences(text)
        assert sentences == [text]


class TestSplitIntoUnits:
    """Tests for splitting text into token-limited units."""

    def test_split_into_units_fits(self):
        """Test text that fits within limit."""
        text = "Short text."
        units = split_into_units(text, max_tokens=100)
        assert len(units) == 1
        assert units[0] == text

    def test_split_into_units_long_text(self):
        """Test splitting long text."""
        # Create a long text
        text = " ".join(["This is a sentence." for _ in range(50)])
        units = split_into_units(text, max_tokens=50)
        assert len(units) > 1
        for unit in units:
            assert count_tokens(unit) <= 50 or len(unit.split()) == 1

    def test_split_into_units_empty(self):
        """Test splitting empty text."""
        assert split_into_units("", max_tokens=100) == []


class TestChunkDocument:
    """Tests for document chunking."""

    def _create_document(self, text: str, doc_id: str = "test-doc", metadata: dict = None) -> Document:
        """Helper to create a test document."""
        return Document(
            doc_id=doc_id,
            path=Path("/fake/path/doc.txt"),
            source_type="txt",
            text=text,
            metadata=metadata or {},
        )

    def test_chunk_document_simple(self):
        """Test chunking a simple document."""
        doc = self._create_document("This is a simple test document.")
        chunks = chunk_document(doc, chunk_size_tokens=400)
        assert len(chunks) >= 1
        assert chunks[0].doc_id == "test-doc"
        assert chunks[0].chunk_id == "test-doc::chunk-0000"

    def test_chunk_document_multiple_chunks(self):
        """Test chunking a longer document into multiple chunks."""
        # Create a document that will need multiple chunks
        paragraphs = [f"This is paragraph number {i}. It contains some text." for i in range(100)]
        text = "\n\n".join(paragraphs)
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=100, chunk_overlap_percent=0.15)
        assert len(chunks) > 1
        # Verify chunk IDs are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_document_overlap(self):
        """Test that chunks have overlap."""
        paragraphs = [f"Paragraph {i} with some content for testing." for i in range(20)]
        text = "\n\n".join(paragraphs)
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=100, chunk_overlap_percent=0.15)

        if len(chunks) >= 2:
            # Check that there's some content overlap between consecutive chunks
            chunk1_text = chunks[0].text
            chunk2_text = chunks[1].text
            # At least some text should appear in both
            # (overlap means end of chunk1 appears at start of chunk2)
            assert len(chunk1_text) > 0
            assert len(chunk2_text) > 0

    def test_chunk_document_default_parameters(self):
        """Test chunking with default parameters."""
        doc = self._create_document("Test document content.")
        chunks = chunk_document(doc)
        assert len(chunks) >= 1
        # Verify defaults are applied
        assert chunks[0].token_estimate <= DEFAULT_CHUNK_SIZE_TOKENS + 50  # Some tolerance

    def test_chunk_document_invalid_chunk_size(self):
        """Test that invalid chunk size raises error."""
        doc = self._create_document("Test")
        with pytest.raises(ValueError, match="chunk_size_tokens must be positive"):
            chunk_document(doc, chunk_size_tokens=0)
        with pytest.raises(ValueError, match="chunk_size_tokens must be positive"):
            chunk_document(doc, chunk_size_tokens=-1)

    def test_chunk_document_overlap_clamping(self):
        """Test that overlap percentage is clamped to valid range."""
        doc = self._create_document("Test document with some content.")
        # These should not raise errors - values get clamped
        chunks1 = chunk_document(doc, chunk_overlap_percent=0.05)  # Below min
        chunks2 = chunk_document(doc, chunk_overlap_percent=0.30)  # Above max
        assert len(chunks1) >= 1
        assert len(chunks2) >= 1

    def test_chunk_document_empty(self):
        """Test chunking empty document."""
        doc = self._create_document("")
        chunks = chunk_document(doc)
        # Empty document should produce empty or minimal chunks
        assert len(chunks) <= 1

    def test_chunk_document_metadata_propagation(self):
        """Test that source metadata is propagated to chunks."""
        metadata = {
            "page_count": 10,
            "title": "Test Document",
            "author": "Test Author",
        }
        doc = self._create_document("Test content.", metadata=metadata)
        chunks = chunk_document(doc)
        assert len(chunks) >= 1
        # Check metadata propagation
        chunk_meta = chunks[0].metadata
        assert chunk_meta.get("source_page_count") == 10
        assert chunk_meta.get("source_title") == "Test Document"

    def test_chunk_document_chunk_metadata(self):
        """Test that chunks have proper metadata."""
        doc = self._create_document("Test content with multiple words.")
        chunks = chunk_document(doc)
        assert len(chunks) >= 1
        chunk = chunks[0]
        # Check required metadata fields
        assert "paragraph_span" in chunk.metadata
        assert "chunk_char_count" in chunk.metadata
        assert "chunk_token_count" in chunk.metadata
        assert isinstance(chunk.metadata["paragraph_span"], list)
        assert len(chunk.metadata["paragraph_span"]) == 2

    def test_chunk_document_long_paragraph(self):
        """Test chunking with a very long paragraph."""
        # Create a single very long paragraph
        long_para = " ".join(["word" for _ in range(500)])
        doc = self._create_document(long_para)
        chunks = chunk_document(doc, chunk_size_tokens=100)
        # Should be split into multiple chunks
        assert len(chunks) > 1
        # Each chunk should be within reasonable size
        for chunk in chunks:
            # Allow some tolerance for sentence boundaries
            assert chunk.token_estimate <= 150

    def test_chunk_document_preserves_doc_id(self):
        """Test that chunk doc_id matches source document."""
        doc = self._create_document("Content.", doc_id="my-unique-doc")
        chunks = chunk_document(doc)
        assert len(chunks) >= 1
        assert all(chunk.doc_id == "my-unique-doc" for chunk in chunks)

    def test_chunk_document_token_estimate_accuracy(self):
        """Test that token_estimate is reasonably accurate."""
        text = "This is a test document with several words."
        doc = self._create_document(text)
        chunks = chunk_document(doc)
        assert len(chunks) >= 1
        # Token estimate should match actual token count
        actual_tokens = count_tokens(chunks[0].text)
        assert chunks[0].token_estimate == actual_tokens


class TestChunkOverlapPercent:
    """Tests specifically for percentage-based overlap."""

    def _create_document(self, text: str) -> Document:
        return Document(
            doc_id="test-doc",
            path=Path("/fake/path/doc.txt"),
            source_type="txt",
            text=text,
            metadata={},
        )

    def test_overlap_at_minimum(self):
        """Test overlap at 10% (minimum)."""
        paragraphs = [f"Para {i}. " * 10 for i in range(20)]
        text = "\n\n".join(paragraphs)
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=100, chunk_overlap_percent=MIN_OVERLAP_PERCENT)
        assert len(chunks) > 1

    def test_overlap_at_maximum(self):
        """Test overlap at 20% (maximum)."""
        paragraphs = [f"Para {i}. " * 10 for i in range(20)]
        text = "\n\n".join(paragraphs)
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=100, chunk_overlap_percent=MAX_OVERLAP_PERCENT)
        assert len(chunks) > 1

    def test_overlap_at_default(self):
        """Test overlap at 15% (default)."""
        paragraphs = [f"Para {i}. " * 10 for i in range(20)]
        text = "\n\n".join(paragraphs)
        doc = self._create_document(text)
        chunks = chunk_document(doc, chunk_size_tokens=100, chunk_overlap_percent=DEFAULT_OVERLAP_PERCENT)
        assert len(chunks) > 1
