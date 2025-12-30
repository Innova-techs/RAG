from __future__ import annotations

from typing import List, Sequence, Tuple

from .models import Document, DocumentChunk
from .text_utils import estimate_tokens, split_paragraphs


def _build_chunk(
    doc: Document, buffer: Sequence[Tuple[str, int, int]], chunk_index: int
) -> DocumentChunk:
    if not buffer:
        raise ValueError("Cannot build chunk from empty buffer.")
    paragraphs = [item[0] for item in buffer]
    chunk_text = "\n\n".join(paragraphs).strip()
    token_estimate = estimate_tokens(chunk_text)
    start_para = buffer[0][1]
    end_para = buffer[-1][1]
    metadata = {
        "paragraph_span": [start_para, end_para],
        "chunk_char_count": len(chunk_text),
    }
    chunk_id = f"{doc.doc_id}::chunk-{chunk_index:04d}"
    return DocumentChunk(
        chunk_id=chunk_id,
        doc_id=doc.doc_id,
        chunk_index=chunk_index,
        text=chunk_text,
        token_estimate=token_estimate,
        metadata=metadata,
    )


def chunk_document(
    document: Document,
    chunk_size_tokens: int = 400,
    chunk_overlap_tokens: int = 80,
) -> List[DocumentChunk]:
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be positive.")
    if chunk_overlap_tokens >= chunk_size_tokens:
        chunk_overlap_tokens = chunk_size_tokens // 2

    paragraphs = split_paragraphs(document.text)
    annotated_paragraphs = [
        (paragraph, idx, estimate_tokens(paragraph))
        for idx, paragraph in enumerate(paragraphs)
    ]

    chunks: List[DocumentChunk] = []
    buffer: List[Tuple[str, int, int]] = []
    buffer_tokens = 0
    chunk_index = 0

    def flush_buffer() -> None:
        nonlocal buffer, buffer_tokens, chunk_index
        if not buffer:
            return
        chunk = _build_chunk(document, buffer, chunk_index)
        chunks.append(chunk)
        chunk_index += 1

        if chunk_overlap_tokens <= 0:
            buffer = []
            buffer_tokens = 0
            return

        overlap: List[Tuple[str, int, int]] = []
        tokens_accumulated = 0
        for item in reversed(buffer):
            overlap.insert(0, item)
            tokens_accumulated += item[2]
            if tokens_accumulated >= chunk_overlap_tokens:
                break
        buffer = overlap.copy()
        buffer_tokens = sum(item[2] for item in buffer)

    for paragraph, para_idx, token_count in annotated_paragraphs:
        if buffer and buffer_tokens + token_count > chunk_size_tokens:
            flush_buffer()
        buffer.append((paragraph, para_idx, token_count))
        buffer_tokens += token_count

    if buffer:
        flush_buffer()

    return chunks
