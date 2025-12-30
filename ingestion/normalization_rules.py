"""Pre-defined regex patterns and character maps for text normalization."""

from __future__ import annotations

# Page number patterns
PAGE_NUMBER_PATTERNS = [
    r"^\s*Page\s+\d+\s*$",
    r"^\s*page\s+\d+\s*$",
    r"^\s*-\s*\d+\s*-\s*$",
    r"^\s*\[\s*\d+\s*\]\s*$",
    r"^\s*\d+\s+of\s+\d+\s*$",
    r"^\s*\d+\s*/\s*\d+\s*$",
    r"^\s*\(\s*\d+\s*\)\s*$",
    r"^\s*p\.\s*\d+\s*$",
    r"^\s*pg\.\s*\d+\s*$",
]

# Boilerplate patterns
BOILERPLATE_PATTERNS = [
    r"(?i)^\s*confidential\s*$",
    r"(?i)^\s*proprietary\s*(and\s+)?confidential\s*$",
    r"(?i)^\s*strictly\s+confidential\s*$",
    r"(?i)^\s*for\s+internal\s+use\s+only\s*$",
    r"(?i)^\s*internal\s+use\s+only\s*$",
    r"(?i)^\s*not\s+for\s+(public\s+)?distribution\s*$",
    r"(?i)^\s*draft\s*$",
    r"(?i)^\s*draft\s+version\s*$",
    r"(?i)^\s*working\s+draft\s*$",
    r"(?i)^\s*do\s+not\s+distribute\s*$",
    r"(?i)^\s*do\s+not\s+copy\s*$",
    r"(?i)^\s*do\s+not\s+forward\s*$",
    r"(?i)^\s*all\s+rights\s+reserved\.?\s*$",
    r"(?i)^\s*copyright\s*(?:\u00a9|\(c\))?\s*\d{4}.*$",
    r"^\s*\u00a9\s*\d{4}.*$",
    r"(?i)^\s*\(c\)\s*\d{4}.*$",
    r"(?i)^\s*disclaimer\s*:?\s*$",
    r"(?i)^\s*legal\s+notice\s*:?\s*$",
]

# Special character replacements
SPECIAL_CHAR_MAP = {
    "\u201c": '"',  # Left double quotation mark
    "\u201d": '"',  # Right double quotation mark
    "\u2018": "'",  # Left single quotation mark
    "\u2019": "'",  # Right single quotation mark
    "\u00ab": '"',  # Left-pointing double angle quotation mark
    "\u00bb": '"',  # Right-pointing double angle quotation mark
    "\u201e": '"',  # Double low-9 quotation mark
    "\u201a": "'",  # Single low-9 quotation mark
    "\u2013": "-",  # En dash
    "\u2014": "-",  # Em dash
    "\u2015": "-",  # Horizontal bar
    "\u2212": "-",  # Minus sign
    "\u00a0": " ",  # Non-breaking space
    "\u2003": " ",  # Em space
    "\u2002": " ",  # En space
    "\u2009": " ",  # Thin space
    "\u200a": " ",  # Hair space
}

# Bullet characters to normalize
BULLET_CHARS = [
    "\u2022",  # Bullet
    "\u2023",  # Triangular bullet
    "\u2043",  # Hyphen bullet
    "\u204c",  # Black leftwards bullet
    "\u204d",  # Black rightwards bullet
    "\u2219",  # Bullet operator
    "\u25aa",  # Black small square
    "\u25ab",  # White small square
    "\u25cf",  # Black circle
    "\u25cb",  # White circle
    "\u25e6",  # White bullet
    "\u25a0",  # Black square
    "\u25a1",  # White square
    "\u27a4",  # Black rightwards arrowhead
]

# Zero-width characters to remove
ZERO_WIDTH_CHARS = [
    "\u200b",  # Zero-width space
    "\u200c",  # Zero-width non-joiner
    "\u200d",  # Zero-width joiner
    "\ufeff",  # Zero-width no-break space (BOM)
    "\u2060",  # Word joiner
    "\u00ad",  # Soft hyphen
]
