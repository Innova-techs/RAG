from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    metadata: Dict[str, str] = field(default_factory=dict)

