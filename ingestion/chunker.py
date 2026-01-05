from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import Document, DocumentChunk
from .text_utils import count_tokens, split_into_units, split_paragraphs

# Default chunking parameters
DEFAULT_CHUNK_SIZE_TOKENS = 400
DEFAULT_OVERLAP_PERCENT = 0.15  # 15% overlap
MIN_OVERLAP_PERCENT = 0.10  # 10% minimum
MAX_OVERLAP_PERCENT = 0.20  # 20% maximum

# Patterns for section and page detection
_PAGE_MARKER_PATTERN = re.compile(r"^\[PAGE:(\d+)\]$", re.MULTILINE)
_SECTION_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _extract_page_from_text(text: str) -> Optional[int]:
    """Extract page number from text containing page markers.

    Returns the first page marker found, or None if no marker exists.
    """
    match = _PAGE_MARKER_PATTERN.search(text)
    if match:
        return int(match.group(1))
    return None


def _extract_section_from_text(text: str) -> Optional[str]:
    """Extract the most recent section header from text.

    Returns the last markdown header found (closest to the content),
    or None if no headers exist.
    """
    matches = list(_SECTION_HEADER_PATTERN.finditer(text))
    if matches:
        # Return the last (most recent) header text
        return matches[-1].group(2).strip()
    return None


def _strip_page_markers(text: str) -> str:
    """Remove page markers from text for clean chunk content."""
    return _PAGE_MARKER_PATTERN.sub("", text).strip()


def _build_chunk(
    doc: Document,
    units: Sequence[Tuple[str, int, int]],
    chunk_index: int,
    source_metadata: Optional[Dict[str, Any]] = None,
    current_page: Optional[int] = None,
    current_section: Optional[str] = None,
) -> DocumentChunk:
    """Build a DocumentChunk from a sequence of text units.

    Args:
        doc: Source document.
        units: List of (text, unit_index, token_count) tuples.
        chunk_index: Index of this chunk in the document.
        source_metadata: Optional metadata from source document (page, section).
        current_page: Current page number (1-indexed) for PDF documents.
        current_section: Current section header text.

    Returns:
        DocumentChunk with combined text and metadata.
    """
    if not units:
        raise ValueError("Cannot build chunk from empty buffer.")

    texts = [item[0] for item in units]
    raw_chunk_text = "\n\n".join(texts).strip()

    # Extract page/section from chunk content if not provided
    if current_page is None:
        current_page = _extract_page_from_text(raw_chunk_text)
    if current_section is None:
        current_section = _extract_section_from_text(raw_chunk_text)

    # Clean text by removing page markers
    chunk_text = _strip_page_markers(raw_chunk_text)
    # Normalize whitespace after marker removal
    chunk_text = re.sub(r"\n{3,}", "\n\n", chunk_text).strip()

    token_count = count_tokens(chunk_text)

    start_unit = units[0][1]
    end_unit = units[-1][1]

    metadata: Dict[str, Any] = {
        "paragraph_span": [start_unit, end_unit],
        "chunk_char_count": len(chunk_text),
        "chunk_token_count": token_count,
    }

    # Add page and section metadata
    if current_page is not None:
        metadata["page"] = current_page
    if current_section is not None:
        metadata["section"] = current_section

    # Propagate source metadata if available
    if source_metadata:
        if "page_count" in source_metadata:
            metadata["source_page_count"] = source_metadata["page_count"]
        if "title" in source_metadata:
            metadata["source_title"] = source_metadata["title"]

    chunk_id = f"{doc.doc_id}::chunk-{chunk_index:04d}"
    return DocumentChunk(
        chunk_id=chunk_id,
        doc_id=doc.doc_id,
        chunk_index=chunk_index,
        text=chunk_text,
        token_estimate=token_count,
        metadata=metadata,
    )


def chunk_document(
    document: Document,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    chunk_overlap_percent: float = DEFAULT_OVERLAP_PERCENT,
) -> List[DocumentChunk]:
    """Chunk a document into smaller pieces with configurable overlap.

    Uses sentence-aware splitting to respect natural text boundaries.
    Overlap is specified as a percentage of chunk size (default 15%).

    Args:
        document: Document to chunk.
        chunk_size_tokens: Target token count per chunk (default: 400).
        chunk_overlap_percent: Overlap as percentage of chunk size (default: 0.15).
            Must be between 0.10 (10%) and 0.20 (20%).

    Returns:
        List of DocumentChunk objects.

    Raises:
        ValueError: If chunk_size_tokens <= 0 or overlap_percent out of range.
    """
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be positive.")

    # Validate and clamp overlap percentage
    if chunk_overlap_percent < MIN_OVERLAP_PERCENT:
        chunk_overlap_percent = MIN_OVERLAP_PERCENT
    elif chunk_overlap_percent > MAX_OVERLAP_PERCENT:
        chunk_overlap_percent = MAX_OVERLAP_PERCENT

    # Calculate actual overlap in tokens
    chunk_overlap_tokens = int(chunk_size_tokens * chunk_overlap_percent)

    # Split into paragraphs first
    paragraphs = split_paragraphs(document.text)

    # Process each paragraph, splitting long ones by sentences
    annotated_units: List[Tuple[str, int, int]] = []
    unit_idx = 0

    for paragraph in paragraphs:
        para_tokens = count_tokens(paragraph)

        if para_tokens <= chunk_size_tokens:
            # Paragraph fits, add as single unit
            annotated_units.append((paragraph, unit_idx, para_tokens))
            unit_idx += 1
        else:
            # Paragraph too long, split by sentences/words
            sub_units = split_into_units(paragraph, chunk_size_tokens)
            for sub_unit in sub_units:
                sub_tokens = count_tokens(sub_unit)
                annotated_units.append((sub_unit, unit_idx, sub_tokens))
                unit_idx += 1

    if not annotated_units:
        return []

    # Build chunks with overlap
    chunks: List[DocumentChunk] = []
    buffer: List[Tuple[str, int, int]] = []
    buffer_tokens = 0
    chunk_index = 0

    # Track current context (page and section) across chunks
    current_page: Optional[int] = None
    current_section: Optional[str] = None

    # Get source metadata for propagation
    source_metadata = document.metadata if document.metadata else {}

    def flush_buffer() -> None:
        nonlocal buffer, buffer_tokens, chunk_index, current_page, current_section
        if not buffer:
            return

        # Build chunk with current context
        chunk = _build_chunk(
            document,
            buffer,
            chunk_index,
            source_metadata,
            current_page,
            current_section,
        )
        chunks.append(chunk)
        chunk_index += 1

        # Update context from the chunk that was just built
        # This ensures subsequent chunks inherit the context
        chunk_meta = chunk.metadata
        if "page" in chunk_meta:
            current_page = chunk_meta["page"]
        if "section" in chunk_meta:
            current_section = chunk_meta["section"]

        if chunk_overlap_tokens <= 0:
            buffer = []
            buffer_tokens = 0
            return

        # Keep overlap from end of buffer
        overlap: List[Tuple[str, int, int]] = []
        tokens_accumulated = 0
        for item in reversed(buffer):
            overlap.insert(0, item)
            tokens_accumulated += item[2]
            if tokens_accumulated >= chunk_overlap_tokens:
                break

        buffer = overlap.copy()
        buffer_tokens = sum(item[2] for item in buffer)

    for unit, unit_idx, token_count in annotated_units:
        # Update context from incoming units (for page markers and headers)
        unit_page = _extract_page_from_text(unit)
        if unit_page is not None:
            current_page = unit_page
        unit_section = _extract_section_from_text(unit)
        if unit_section is not None:
            current_section = unit_section

        # If adding this unit exceeds chunk size, flush first
        if buffer and buffer_tokens + token_count > chunk_size_tokens:
            flush_buffer()

        buffer.append((unit, unit_idx, token_count))
        buffer_tokens += token_count

    # Flush remaining buffer
    if buffer:
        flush_buffer()

    return chunks
