from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable

from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.chunks_dir = output_root / "chunks"
        self.logs_dir = output_root / "logs"
        self.manifest_path = output_root / "manifest.json"
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
