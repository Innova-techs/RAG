from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict


@dataclass(slots=True)
class Document:
    """Represents a parsed document ready for chunking."""

    doc_id: str
    path: Path
    source_type: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(slots=True)
class DocumentChunk:
    """Single chunk produced from a document."""

    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    token_estimate: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "token_estimate": self.token_estimate,
            "metadata": self.metadata,
        }
