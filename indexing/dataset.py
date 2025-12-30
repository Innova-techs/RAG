from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Sequence

from .models import ChunkRecord

logger = logging.getLogger(__name__)


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
                metadata = {
                    "doc_id": doc_id,
                    "chunk_index": chunk_data.get("chunk_index"),
                    "chunk_id": chunk_data.get("chunk_id"),
                    "source_path": doc_entry.get("source_path"),
                    "relative_path": doc_entry.get("relative_path"),
                    "file_extension": doc_entry.get("file_extension"),
                    "content_hash": doc_entry.get("content_hash"),
                }
                metadata.update(doc_entry.get("metadata", {}))

                chunk_meta = dict(chunk_data.get("metadata") or {})
                paragraph_span = chunk_meta.pop("paragraph_span", None)
                if (
                    isinstance(paragraph_span, (list, tuple))
                    and len(paragraph_span) == 2
                ):
                    metadata["paragraph_start"] = int(paragraph_span[0])
                    metadata["paragraph_end"] = int(paragraph_span[1])
                elif paragraph_span is not None:
                    metadata["paragraph_span"] = str(paragraph_span)
                metadata.update(chunk_meta)

                yield ChunkRecord(
                    chunk_id=chunk_data["chunk_id"],
                    doc_id=chunk_data["doc_id"],
                    chunk_index=int(chunk_data["chunk_index"]),
                    text=chunk_data["text"],
                    metadata=metadata,
                )
