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


class DocumentParseError(Exception):
    """Raised when a document cannot be parsed."""

    def __init__(self, message: str, path: Path, partial_content: str = ""):
        super().__init__(message)
        self.path = path
        self.partial_content = partial_content


def load_pdf(path: Path) -> Tuple[str, Dict[str, str]]:
    """Load PDF file with error handling for corrupted/invalid files."""
    from PyPDF2 import PdfReader
    from PyPDF2.errors import PdfReadError

    pages = []
    failed_pages = []
    metadata = {}

    try:
        reader = PdfReader(str(path))
        metadata["page_count"] = len(reader.pages)
        metadata["is_encrypted"] = reader.is_encrypted

        if reader.is_encrypted:
            logger.warning(f"PDF is encrypted: {path}")
            metadata["parse_warning"] = "encrypted_pdf"
            return "", metadata

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                pages.append(text.strip())
            except Exception as e:
                logger.warning(f"Failed to extract page {i + 1} from {path}: {e}")
                failed_pages.append(i + 1)
                pages.append("")

        if failed_pages:
            metadata["failed_pages"] = failed_pages
            metadata["parse_warning"] = f"partial_extraction_{len(failed_pages)}_pages_failed"

    except PdfReadError as e:
        logger.error(f"Corrupted PDF file: {path} - {e}")
        raise DocumentParseError(f"Corrupted PDF: {e}", path)
    except Exception as e:
        logger.error(f"Failed to read PDF: {path} - {e}")
        raise DocumentParseError(f"PDF read error: {e}", path)

    return "\n\n".join(pages), metadata


def load_docx(path: Path) -> Tuple[str, Dict[str, str]]:
    """Load DOCX file with table extraction and error handling."""
    import docx
    from docx.opc.exceptions import PackageNotFoundError
    import zipfile

    content_parts = []
    metadata = {}

    try:
        doc = docx.Document(str(path))

        # Extract paragraphs
        paragraphs = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
        metadata["paragraph_count"] = len(paragraphs)
        content_parts.extend(paragraphs)

        # Extract tables
        table_count = 0
        for table in doc.tables:
            table_count += 1
            table_text = []
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells]
                if any(row_cells):
                    table_text.append(" | ".join(row_cells))
            if table_text:
                content_parts.append("\n[TABLE]\n" + "\n".join(table_text) + "\n[/TABLE]")

        metadata["table_count"] = table_count

        # Extract headers and footers
        header_text = []
        footer_text = []
        for section in doc.sections:
            if section.header and section.header.paragraphs:
                for para in section.header.paragraphs:
                    if para.text.strip():
                        header_text.append(para.text.strip())
            if section.footer and section.footer.paragraphs:
                for para in section.footer.paragraphs:
                    if para.text.strip():
                        footer_text.append(para.text.strip())

        if header_text:
            metadata["has_headers"] = True
        if footer_text:
            metadata["has_footers"] = True

    except (PackageNotFoundError, zipfile.BadZipFile) as e:
        logger.error(f"Invalid or corrupted DOCX file: {path} - {e}")
        raise DocumentParseError(f"Corrupted DOCX: {e}", path)
    except Exception as e:
        logger.error(f"Failed to read DOCX: {path} - {e}")
        raise DocumentParseError(f"DOCX read error: {e}", path)

    return "\n\n".join(content_parts), metadata


def load_markdown(path: Path) -> Tuple[str, Dict[str, str]]:
    """Load Markdown/text file with structure-aware parsing and error handling."""
    metadata = {}

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try fallback encodings
        for encoding in ["latin-1", "cp1252", "iso-8859-1"]:
            try:
                content = path.read_text(encoding=encoding)
                metadata["encoding_fallback"] = encoding
                logger.warning(f"Used fallback encoding {encoding} for: {path}")
                break
            except UnicodeDecodeError:
                continue
        else:
            logger.error(f"Failed to decode file with any encoding: {path}")
            raise DocumentParseError(f"Unable to decode file", path)
    except Exception as e:
        logger.error(f"Failed to read file: {path} - {e}")
        raise DocumentParseError(f"File read error: {e}", path)

    # Extract markdown structure metadata
    lines = content.split("\n")

    # Count headers by level
    headers = {"h1": 0, "h2": 0, "h3": 0, "h4": 0, "h5": 0, "h6": 0}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("######"):
            headers["h6"] += 1
        elif stripped.startswith("#####"):
            headers["h5"] += 1
        elif stripped.startswith("####"):
            headers["h4"] += 1
        elif stripped.startswith("###"):
            headers["h3"] += 1
        elif stripped.startswith("##"):
            headers["h2"] += 1
        elif stripped.startswith("#"):
            headers["h1"] += 1

    if any(headers.values()):
        metadata["headers"] = {k: v for k, v in headers.items() if v > 0}

    # Detect code blocks
    code_block_count = content.count("```") // 2
    if code_block_count > 0:
        metadata["code_blocks"] = code_block_count

    # Detect lists
    list_items = sum(1 for line in lines if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+\.\s+", line))
    if list_items > 0:
        metadata["list_items"] = list_items

    # Detect links
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    if links:
        metadata["link_count"] = len(links)

    # Extract front matter if present (YAML)
    if content.startswith("---"):
        end_marker = content.find("---", 3)
        if end_marker != -1:
            metadata["has_frontmatter"] = True

    metadata["line_count"] = len(lines)

    return content, metadata


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
