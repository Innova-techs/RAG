from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Sequence

from .models import ChunkRecord

logger = logging.getLogger(__name__)


def _sanitize_metadata(metadata: Dict[str, object]) -> Dict[str, object]:
    """Ensure metadata values are compatible with Chroma's type constraints.

    Chroma requires metadata values to be str, int, float, or bool.
    Complex types (lists, dicts) are serialized to JSON strings.
    None values are omitted.
    """
    sanitized: Dict[str, object] = {}
    for key, value in metadata.items():
        if value is None:
            continue  # Chroma doesn't accept None
        elif isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        else:
            sanitized[key] = json.dumps(value, ensure_ascii=False)
    return sanitized


def load_manifest(manifest_path: Path) -> Dict[str, Dict]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def iter_chunk_records(
    manifest: Dict[str, Dict],
    chunks_dir: Path,
    doc_filter: Optional[Sequence[str]] = None,
) -> Iterator[ChunkRecord]:
    selected_doc_ids = list(doc_filter) if doc_filter else sorted(manifest.keys())
    for doc_id in selected_doc_ids:
        doc_entry = manifest.get(doc_id)
        if not doc_entry:
            logger.warning("Doc id %s not found in manifest, skipping.", doc_id)
            continue

        chunk_path = chunks_dir / f"{doc_id}.jsonl"
        if not chunk_path.exists():
            logger.warning("Chunk file %s missing, skipping.", chunk_path)
            continue

        with chunk_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                chunk_data = json.loads(line)

                # Get document-level metadata
                doc_metadata = doc_entry.get("metadata", {})

                # Build metadata with all required fields for Chroma indexing
                metadata = {
                    # Required fields (Issue #14)
                    "doc_id": doc_id,
                    "chunk_index": chunk_data.get("chunk_index"),
                    "chunk_id": chunk_data.get("chunk_id"),
                    "source_path": doc_entry.get("source_path"),
                    # Document info
                    "relative_path": doc_entry.get("relative_path"),
                    "file_extension": doc_entry.get("file_extension"),
                    "content_hash": doc_entry.get("content_hash"),
                }

                # Timestamp for freshness queries (only include if present)
                timestamp = doc_metadata.get("ingestion_timestamp")
                if timestamp:
                    metadata["timestamp"] = timestamp

                # Add document-level metadata
                metadata.update(doc_metadata)

                # Process chunk-level metadata
                chunk_meta = dict(chunk_data.get("metadata") or {})

                # Handle paragraph span
                paragraph_span = chunk_meta.pop("paragraph_span", None)
                if (
                    isinstance(paragraph_span, (list, tuple))
                    and len(paragraph_span) == 2
                ):
                    metadata["paragraph_start"] = int(paragraph_span[0])
                    metadata["paragraph_end"] = int(paragraph_span[1])
                elif paragraph_span is not None:
                    metadata["paragraph_span"] = str(paragraph_span)

                # Extract page and section from chunk metadata (added by chunker)
                page = chunk_meta.pop("page", None)
                if page is not None:
                    metadata["page"] = int(page)

                section = chunk_meta.pop("section", None)
                if section is not None:
                    metadata["section"] = str(section)

                # Add remaining chunk metadata
                metadata.update(chunk_meta)
                metadata = _sanitize_metadata(metadata)

                yield ChunkRecord(
                    chunk_id=chunk_data["chunk_id"],
                    doc_id=chunk_data["doc_id"],
                    chunk_index=int(chunk_data["chunk_index"]),
                    text=chunk_data["text"],
                    metadata=metadata,
                )
