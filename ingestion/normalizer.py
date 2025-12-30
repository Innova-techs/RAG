"""Text normalization pipeline for cleaning and standardizing document text."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from .normalization_rules import (
    BOILERPLATE_PATTERNS,
    BULLET_CHARS,
    PAGE_NUMBER_PATTERNS,
    SPECIAL_CHAR_MAP,
    ZERO_WIDTH_CHARS,
)

logger = logging.getLogger(__name__)


@dataclass
class NormalizationConfig:
    """Configuration options for text normalization.

    Attributes:
        remove_page_numbers: Remove lines matching page number patterns.
        remove_headers_footers: Remove repeated lines appearing at document boundaries.
        remove_boilerplate: Remove common boilerplate text (confidential, copyright, etc.).
        normalize_whitespace: Collapse multiple spaces/newlines into single instances.
        normalize_special_chars: Replace curly quotes, dashes, etc. with ASCII equivalents.
        normalize_bullets: Convert various bullet characters to standard dash.
        remove_zero_width: Remove zero-width and invisible characters.
        preserve_code_blocks: Keep code blocks (```...```) unchanged during normalization.
        min_line_length: Minimum line length to keep (shorter lines may be headers/footers).
        header_footer_threshold: Number of times a line must repeat to be considered header/footer.
        header_footer_max_length: Maximum line length to consider as header/footer (longer lines preserved).
        custom_patterns: Additional regex patterns to remove.
        custom_replacements: Additional character replacements {from: to}.
    """

    remove_page_numbers: bool = True
    remove_headers_footers: bool = True
    remove_boilerplate: bool = True
    normalize_whitespace: bool = True
    normalize_special_chars: bool = True
    normalize_bullets: bool = True
    remove_zero_width: bool = True
    preserve_code_blocks: bool = True
    min_line_length: int = 0
    header_footer_threshold: int = 2
    header_footer_max_length: int = 100
    custom_patterns: list[str] = field(default_factory=list)
    custom_replacements: dict[str, str] = field(default_factory=dict)


@dataclass
class NormalizationResult:
    """Result of text normalization.

    Attributes:
        text: The normalized text content.
        original_length: Character count of the original text.
        normalized_length: Character count of the normalized text.
        rules_applied: List of normalization rules that were applied.
        removed_patterns: Dictionary mapping rule names to count of matches removed.
    """

    text: str
    original_length: int
    normalized_length: int
    rules_applied: list[str]
    removed_patterns: dict[str, int]


class TextNormalizer:
    """Text normalizer with configurable normalization rules.

    This class provides comprehensive text normalization for documents,
    including removal of page numbers, headers/footers, boilerplate text,
    and normalization of special characters and whitespace.

    Example:
        >>> config = NormalizationConfig(remove_page_numbers=True)
        >>> normalizer = TextNormalizer(config)
        >>> result = normalizer.normalize("Page 1\\nContent here\\nPage 2")
        >>> print(result.text)
        Content here
    """

    def __init__(self, config: NormalizationConfig | None = None):
        """Initialize the TextNormalizer.

        Args:
            config: Normalization configuration. Uses defaults if not provided.
        """
        self.config = config or NormalizationConfig()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        # Page number patterns
        self._page_number_patterns = [
            re.compile(pattern) for pattern in PAGE_NUMBER_PATTERNS
        ]

        # Boilerplate patterns
        self._boilerplate_patterns = [
            re.compile(pattern) for pattern in BOILERPLATE_PATTERNS
        ]

        # Custom patterns
        self._custom_patterns = [
            re.compile(pattern) for pattern in self.config.custom_patterns
        ]

        # Code block pattern for preservation
        self._code_block_pattern = re.compile(r"```[\s\S]*?```", re.MULTILINE)

        # Whitespace patterns
        self._multi_newline_pattern = re.compile(r"\n{3,}")
        self._multi_space_pattern = re.compile(r"[ \t]{2,}")
        self._trailing_whitespace_pattern = re.compile(r"[ \t]+$", re.MULTILINE)

    def normalize(self, text: str) -> NormalizationResult:
        """Normalize the input text according to configuration.

        Args:
            text: The text to normalize.

        Returns:
            NormalizationResult containing the normalized text and metadata.
        """
        original_length = len(text)
        rules_applied: list[str] = []
        removed_patterns: dict[str, int] = {}

        # Preserve code blocks if configured
        code_blocks: list[str] = []
        if self.config.preserve_code_blocks:
            text, code_blocks = self._extract_code_blocks(text)
            if code_blocks:
                rules_applied.append("preserve_code_blocks")

        # Remove zero-width characters first
        if self.config.remove_zero_width:
            text, count = self._remove_zero_width(text)
            if count > 0:
                rules_applied.append("remove_zero_width")
                removed_patterns["zero_width_chars"] = count

        # Normalize special characters
        if self.config.normalize_special_chars:
            text, count = self._normalize_special_chars(text)
            if count > 0:
                rules_applied.append("normalize_special_chars")
                removed_patterns["special_chars"] = count

        # Normalize bullets
        if self.config.normalize_bullets:
            text, count = self._normalize_bullets(text)
            if count > 0:
                rules_applied.append("normalize_bullets")
                removed_patterns["bullet_chars"] = count

        # Remove page numbers
        if self.config.remove_page_numbers:
            text, count = self._remove_page_numbers(text)
            if count > 0:
                rules_applied.append("remove_page_numbers")
                removed_patterns["page_numbers"] = count

        # Remove boilerplate
        if self.config.remove_boilerplate:
            text, count = self._remove_boilerplate(text)
            if count > 0:
                rules_applied.append("remove_boilerplate")
                removed_patterns["boilerplate"] = count

        # Remove headers/footers (repeated lines)
        if self.config.remove_headers_footers:
            text, count = self._remove_headers_footers(text)
            if count > 0:
                rules_applied.append("remove_headers_footers")
                removed_patterns["headers_footers"] = count

        # Apply custom patterns
        if self._custom_patterns:
            text, count = self._apply_custom_patterns(text)
            if count > 0:
                rules_applied.append("custom_patterns")
                removed_patterns["custom_patterns"] = count

        # Apply custom replacements
        if self.config.custom_replacements:
            text, count = self._apply_custom_replacements(text)
            if count > 0:
                rules_applied.append("custom_replacements")
                removed_patterns["custom_replacements"] = count

        # Normalize whitespace (do this last before restoring code blocks)
        if self.config.normalize_whitespace:
            text = self._normalize_whitespace(text)
            rules_applied.append("normalize_whitespace")

        # Restore code blocks
        if self.config.preserve_code_blocks and code_blocks:
            text = self._restore_code_blocks(text, code_blocks)

        return NormalizationResult(
            text=text.strip(),
            original_length=original_length,
            normalized_length=len(text.strip()),
            rules_applied=rules_applied,
            removed_patterns=removed_patterns,
        )

    def _extract_code_blocks(self, text: str) -> tuple[str, list[str]]:
        """Extract code blocks and replace with placeholders.

        Args:
            text: The input text.

        Returns:
            Tuple of (text with placeholders, list of extracted code blocks).
        """
        code_blocks: list[str] = []

        def replace_block(match: re.Match) -> str:
            code_blocks.append(match.group(0))
            return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

        text = self._code_block_pattern.sub(replace_block, text)
        return text, code_blocks

    def _restore_code_blocks(self, text: str, code_blocks: list[str]) -> str:
        """Restore code blocks from placeholders.

        Args:
            text: Text with placeholders.
            code_blocks: List of code blocks to restore.

        Returns:
            Text with code blocks restored.
        """
        for i, block in enumerate(code_blocks):
            text = text.replace(f"__CODE_BLOCK_{i}__", block)
        return text

    def _remove_zero_width(self, text: str) -> tuple[str, int]:
        """Remove zero-width and invisible characters.

        Args:
            text: The input text.

        Returns:
            Tuple of (cleaned text, count of characters removed).
        """
        count = 0
        for char in ZERO_WIDTH_CHARS:
            char_count = text.count(char)
            if char_count > 0:
                text = text.replace(char, "")
                count += char_count
        return text, count

    def _normalize_special_chars(self, text: str) -> tuple[str, int]:
        """Replace special characters with ASCII equivalents.

        Args:
            text: The input text.

        Returns:
            Tuple of (normalized text, count of replacements).
        """
        count = 0
        char_map = {**SPECIAL_CHAR_MAP, **self.config.custom_replacements}
        for old_char, new_char in char_map.items():
            if old_char in self.config.custom_replacements:
                continue  # Handle custom replacements separately
            char_count = text.count(old_char)
            if char_count > 0:
                text = text.replace(old_char, new_char)
                count += char_count
        return text, count

    def _normalize_bullets(self, text: str) -> tuple[str, int]:
        """Normalize various bullet characters to standard dash.

        Args:
            text: The input text.

        Returns:
            Tuple of (normalized text, count of replacements).
        """
        count = 0
        for bullet in BULLET_CHARS:
            char_count = text.count(bullet)
            if char_count > 0:
                text = text.replace(bullet, "-")
                count += char_count
        return text, count

    def _remove_page_numbers(self, text: str) -> tuple[str, int]:
        """Remove lines matching page number patterns.

        Args:
            text: The input text.

        Returns:
            Tuple of (cleaned text, count of lines removed).
        """
        lines = text.split("\n")
        filtered_lines: list[str] = []
        count = 0

        for line in lines:
            is_page_number = False
            for pattern in self._page_number_patterns:
                if pattern.match(line):
                    is_page_number = True
                    count += 1
                    break
            if not is_page_number:
                filtered_lines.append(line)

        return "\n".join(filtered_lines), count

    def _remove_boilerplate(self, text: str) -> tuple[str, int]:
        """Remove lines matching boilerplate patterns.

        Args:
            text: The input text.

        Returns:
            Tuple of (cleaned text, count of lines removed).
        """
        lines = text.split("\n")
        filtered_lines: list[str] = []
        count = 0

        for line in lines:
            is_boilerplate = False
            for pattern in self._boilerplate_patterns:
                if pattern.match(line):
                    is_boilerplate = True
                    count += 1
                    break
            if not is_boilerplate:
                filtered_lines.append(line)

        return "\n".join(filtered_lines), count

    def _remove_headers_footers(self, text: str) -> tuple[str, int]:
        """Remove repeated lines that appear to be headers/footers.

        This identifies lines that appear multiple times in the document,
        especially at regular intervals, and removes them.

        Args:
            text: The input text.

        Returns:
            Tuple of (cleaned text, count of lines removed).
        """
        lines = text.split("\n")
        if len(lines) < 3:
            return text, 0

        # Count line occurrences (ignoring very short and empty lines)
        line_counts: dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if len(stripped) >= self.config.min_line_length and stripped:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

        # Identify header/footer candidates (lines appearing multiple times)
        header_footer_lines: set[str] = set()
        for line, count in line_counts.items():
            if count >= self.config.header_footer_threshold:
                # Only consider lines shorter than max length as potential headers/footers
                if len(line) < self.config.header_footer_max_length:
                    header_footer_lines.add(line)

        # Filter out header/footer lines
        filtered_lines: list[str] = []
        removal_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped in header_footer_lines:
                removal_count += 1
            else:
                filtered_lines.append(line)

        return "\n".join(filtered_lines), removal_count

    def _apply_custom_patterns(self, text: str) -> tuple[str, int]:
        """Apply custom regex patterns to remove matching lines.

        Custom patterns are applied per-line, removing entire lines that match.
        This is consistent with how page numbers and boilerplate are handled.

        Args:
            text: The input text.

        Returns:
            Tuple of (cleaned text, count of lines removed).
        """
        lines = text.split("\n")
        filtered_lines: list[str] = []
        count = 0

        for line in lines:
            matched = False
            for pattern in self._custom_patterns:
                if pattern.match(line):
                    matched = True
                    count += 1
                    break
            if not matched:
                filtered_lines.append(line)

        return "\n".join(filtered_lines), count

    def _apply_custom_replacements(self, text: str) -> tuple[str, int]:
        """Apply custom character replacements.

        Args:
            text: The input text.

        Returns:
            Tuple of (cleaned text, count of replacements).
        """
        count = 0
        for old_str, new_str in self.config.custom_replacements.items():
            char_count = text.count(old_str)
            if char_count > 0:
                text = text.replace(old_str, new_str)
                count += char_count
        return text, count

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in the text.

        This collapses multiple spaces/tabs into single spaces,
        multiple newlines into double newlines, and removes trailing whitespace.

        Args:
            text: The input text.

        Returns:
            Text with normalized whitespace.
        """
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove trailing whitespace from lines
        text = self._trailing_whitespace_pattern.sub("", text)

        # Collapse multiple spaces/tabs
        text = self._multi_space_pattern.sub(" ", text)

        # Collapse multiple newlines (more than 2) into exactly 2
        text = self._multi_newline_pattern.sub("\n\n", text)

        return text

    @classmethod
    def minimal(cls) -> TextNormalizer:
        """Create a minimal normalizer that only normalizes whitespace and special chars.

        This preset is useful when you want to preserve most of the original
        document structure while still cleaning up formatting issues.

        Returns:
            TextNormalizer with minimal configuration.
        """
        config = NormalizationConfig(
            remove_page_numbers=False,
            remove_headers_footers=False,
            remove_boilerplate=False,
            normalize_whitespace=True,
            normalize_special_chars=True,
            normalize_bullets=False,
            remove_zero_width=True,
            preserve_code_blocks=True,
        )
        return cls(config)

    @classmethod
    def aggressive(cls) -> TextNormalizer:
        """Create an aggressive normalizer that applies all cleaning rules.

        This preset is useful when you want to maximize content extraction
        and minimize noise in the output.

        Returns:
            TextNormalizer with aggressive configuration.
        """
        config = NormalizationConfig(
            remove_page_numbers=True,
            remove_headers_footers=True,
            remove_boilerplate=True,
            normalize_whitespace=True,
            normalize_special_chars=True,
            normalize_bullets=True,
            remove_zero_width=True,
            preserve_code_blocks=True,
            min_line_length=3,
            header_footer_threshold=2,
        )
        return cls(config)

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> TextNormalizer:
        """Create a normalizer from a YAML configuration file.

        The YAML file should contain keys matching NormalizationConfig fields.

        Args:
            yaml_path: Path to the YAML configuration file.

        Returns:
            TextNormalizer with configuration from file.

        Raises:
            FileNotFoundError: If the YAML file doesn't exist.
            ValueError: If the YAML file contains invalid configuration.
        """
        import yaml

        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")

        with yaml_path.open("r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}

        # Validate and create config
        try:
            config = NormalizationConfig(
                remove_page_numbers=yaml_config.get("remove_page_numbers", True),
                remove_headers_footers=yaml_config.get("remove_headers_footers", True),
                remove_boilerplate=yaml_config.get("remove_boilerplate", True),
                normalize_whitespace=yaml_config.get("normalize_whitespace", True),
                normalize_special_chars=yaml_config.get("normalize_special_chars", True),
                normalize_bullets=yaml_config.get("normalize_bullets", True),
                remove_zero_width=yaml_config.get("remove_zero_width", True),
                preserve_code_blocks=yaml_config.get("preserve_code_blocks", True),
                min_line_length=yaml_config.get("min_line_length", 0),
                header_footer_threshold=yaml_config.get("header_footer_threshold", 2),
                header_footer_max_length=yaml_config.get("header_footer_max_length", 100),
                custom_patterns=yaml_config.get("custom_patterns", []),
                custom_replacements=yaml_config.get("custom_replacements", {}),
            )
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid configuration in {yaml_path}: {e}") from e

        return cls(config)
