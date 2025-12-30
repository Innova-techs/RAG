from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Tuple

from .models import Document
from .text_utils import normalize_text

logger = logging.getLogger(__name__)


class UnsupportedDocumentError(Exception):
    """Raised when the pipeline encounters an unsupported extension."""


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return normalized or "document"


def hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_pdf(path: Path) -> Tuple[str, Dict[str, str]]:
    from PyPDF2 import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.strip())
    metadata = {"page_count": len(pages)}
    return "\n\n".join(pages), metadata


def load_docx(path: Path) -> Tuple[str, Dict[str, str]]:
    import docx

    doc = docx.Document(str(path))
    paragraphs = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
    metadata = {"paragraph_count": len(paragraphs)}
    return "\n".join(paragraphs), metadata


def load_markdown(path: Path) -> Tuple[str, Dict[str, str]]:
    return path.read_text(encoding="utf-8"), {}


HANDLERS: Dict[str, Callable[[Path], Tuple[str, Dict[str, str]]]] = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".md": load_markdown,
    ".txt": load_markdown,
}


@dataclass
class DocumentLoader:
    input_root: Path

    def load(self, path: Path) -> Tuple[Document, str]:
        ext = path.suffix.lower()
        if ext not in HANDLERS:
            raise UnsupportedDocumentError(f"No loader configured for {ext} files.")
        handler = HANDLERS[ext]
        raw_text, extra_metadata = handler(path)
        normalized_text = normalize_text(raw_text)
        try:
            rel_path = str(path.relative_to(self.input_root)).replace("\\", "/")
        except ValueError:
            rel_path = path.name
        stat_info = path.stat()
        metadata = {
            "source_path": str(path.resolve()),
            "relative_path": rel_path,
            "file_extension": ext.lstrip("."),
            "last_modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "size_bytes": stat_info.st_size,
        }
        metadata.update(extra_metadata or {})
        content_hash = hash_file(path)
        metadata["content_hash"] = content_hash
        doc_id = slugify(rel_path)
        document = Document(
            doc_id=doc_id,
            path=path,
            source_type=metadata["file_extension"],
            text=normalized_text,
            metadata=metadata,
        )
        return document, content_hash


def discover_documents(input_root: Path):
    documents = []
    for ext in HANDLERS:
        documents.extend(input_root.rglob(f"*{ext}"))
    documents.sort()
    return tuple(documents)
