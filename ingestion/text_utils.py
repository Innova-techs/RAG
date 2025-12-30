from __future__ import annotations

import re

MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")
MULTI_SPACE_PATTERN = re.compile(r"[ \t]{2,}")
NON_ASCII_QUOTES = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2013": "-",
    "\u2014": "-",
}


def normalize_text(text: str) -> str:
    """Clean up boilerplate whitespace and punctuation."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for bad, replacement in NON_ASCII_QUOTES.items():
        normalized = normalized.replace(bad, replacement)
    normalized = MULTI_NEWLINE_PATTERN.sub("\n\n", normalized)
    normalized = MULTI_SPACE_PATTERN.sub(" ", normalized)
    return normalized.strip()


def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|\S", text)))


def split_paragraphs(text: str):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paragraphs or [text.strip()]
