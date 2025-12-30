"""Comprehensive tests for the text normalization pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.normalizer import NormalizationConfig, NormalizationResult, TextNormalizer
from ingestion.normalization_rules import (
    BOILERPLATE_PATTERNS,
    BULLET_CHARS,
    PAGE_NUMBER_PATTERNS,
    SPECIAL_CHAR_MAP,
    ZERO_WIDTH_CHARS,
)


class TestPageNumberRemoval:
    """Tests for page number pattern removal."""

    def test_remove_page_number_format_page_n(self):
        """Test removal of 'Page N' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content here\nPage 1\nMore content\nPage 2\nFinal content"
        result = normalizer.normalize(text)
        assert "Page 1" not in result.text
        assert "Page 2" not in result.text
        assert "Content here" in result.text
        assert "More content" in result.text
        assert result.removed_patterns.get("page_numbers", 0) == 2

    def test_remove_page_number_format_lowercase(self):
        """Test removal of 'page N' (lowercase) format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\npage 42\nMore content"
        result = normalizer.normalize(text)
        assert "page 42" not in result.text
        assert "Content" in result.text

    def test_remove_page_number_format_dashes(self):
        """Test removal of '- N -' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\n- 5 -\nMore content"
        result = normalizer.normalize(text)
        assert "- 5 -" not in result.text

    def test_remove_page_number_format_brackets(self):
        """Test removal of '[N]' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\n[ 10 ]\nMore content"
        result = normalizer.normalize(text)
        assert "[ 10 ]" not in result.text

    def test_remove_page_number_format_n_of_m(self):
        """Test removal of 'N of M' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\n3 of 10\nMore content"
        result = normalizer.normalize(text)
        assert "3 of 10" not in result.text

    def test_remove_page_number_format_n_slash_m(self):
        """Test removal of 'N/M' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\n5 / 20\nMore content"
        result = normalizer.normalize(text)
        assert "5 / 20" not in result.text

    def test_remove_page_number_format_parentheses(self):
        """Test removal of '(N)' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\n( 7 )\nMore content"
        result = normalizer.normalize(text)
        assert "( 7 )" not in result.text

    def test_remove_page_number_format_p_dot(self):
        """Test removal of 'p.N' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\np. 15\nMore content"
        result = normalizer.normalize(text)
        assert "p. 15" not in result.text

    def test_remove_page_number_format_pg_dot(self):
        """Test removal of 'pg.N' format."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "Content\npg. 99\nMore content"
        result = normalizer.normalize(text)
        assert "pg. 99" not in result.text

    def test_preserve_page_numbers_when_disabled(self):
        """Test that page numbers are preserved when removal is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=False))
        text = "Content\nPage 1\nMore content"
        result = normalizer.normalize(text)
        assert "Page 1" in result.text

    def test_page_number_in_sentence_preserved(self):
        """Test that page references in sentences are preserved."""
        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        text = "See page 5 for details.\nPage 1\nThe reference on page 10 is important."
        result = normalizer.normalize(text)
        # Standalone page number should be removed
        assert "See page 5 for details." in result.text
        # Sentence with page reference should be preserved
        assert "page 10" in result.text


class TestHeaderFooterRemoval:
    """Tests for repeated header/footer line removal."""

    def test_remove_repeated_header(self):
        """Test removal of repeated header lines."""
        normalizer = TextNormalizer(
            NormalizationConfig(remove_headers_footers=True, header_footer_threshold=2)
        )
        text = "Company Name\nContent paragraph 1.\nCompany Name\nContent paragraph 2.\nCompany Name"
        result = normalizer.normalize(text)
        assert "Company Name" not in result.text
        assert "Content paragraph 1." in result.text
        assert result.removed_patterns.get("headers_footers", 0) == 3

    def test_remove_repeated_footer(self):
        """Test removal of repeated footer lines."""
        normalizer = TextNormalizer(
            NormalizationConfig(remove_headers_footers=True, header_footer_threshold=2)
        )
        text = "Content 1\nFooter Text\nContent 2\nFooter Text\nContent 3\nFooter Text"
        result = normalizer.normalize(text)
        assert "Footer Text" not in result.text
        assert "Content 1" in result.text

    def test_preserve_unique_lines(self):
        """Test that unique lines are preserved."""
        normalizer = TextNormalizer(
            NormalizationConfig(remove_headers_footers=True, header_footer_threshold=2)
        )
        text = "Unique line 1\nUnique line 2\nUnique line 3"
        result = normalizer.normalize(text)
        assert "Unique line 1" in result.text
        assert "Unique line 2" in result.text
        assert "Unique line 3" in result.text

    def test_header_footer_threshold(self):
        """Test that threshold affects removal."""
        normalizer = TextNormalizer(
            NormalizationConfig(remove_headers_footers=True, header_footer_threshold=3)
        )
        # Line appears only twice, below threshold of 3
        text = "Repeated\nContent\nRepeated"
        result = normalizer.normalize(text)
        assert "Repeated" in result.text  # Should be preserved

    def test_preserve_headers_footers_when_disabled(self):
        """Test that repeated lines are preserved when removal is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(remove_headers_footers=False))
        text = "Header\nContent\nHeader\nMore\nHeader"
        result = normalizer.normalize(text)
        assert result.text.count("Header") == 3


class TestBoilerplateRemoval:
    """Tests for boilerplate text removal."""

    def test_remove_confidential(self):
        """Test removal of 'Confidential' boilerplate."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content here\nConfidential\nMore content"
        result = normalizer.normalize(text)
        assert "Confidential" not in result.text
        assert "Content here" in result.text

    def test_remove_proprietary_confidential(self):
        """Test removal of 'Proprietary and Confidential' boilerplate."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nProprietary and Confidential\nMore content"
        result = normalizer.normalize(text)
        assert "Proprietary" not in result.text

    def test_remove_internal_use_only(self):
        """Test removal of 'For Internal Use Only' boilerplate."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nFor Internal Use Only\nMore content"
        result = normalizer.normalize(text)
        assert "Internal Use Only" not in result.text

    def test_remove_draft(self):
        """Test removal of 'Draft' boilerplate."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nDraft\nMore content"
        result = normalizer.normalize(text)
        # After whitespace normalization, consecutive newlines become double newline,
        # but since Draft is removed, we get Content\n\nMore content which normalizes
        # to Content\nMore content after trailing/leading whitespace handling
        assert "Draft" not in result.text
        assert "Content" in result.text
        assert "More content" in result.text

    def test_remove_copyright_notice(self):
        """Test removal of copyright notices."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nCopyright 2024 Company Inc.\nMore content"
        result = normalizer.normalize(text)
        assert "Copyright" not in result.text

    def test_remove_copyright_symbol(self):
        """Test removal of copyright with symbol."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\n\u00a9 2024 Company Inc.\nMore content"
        result = normalizer.normalize(text)
        assert "\u00a9" not in result.text

    def test_remove_all_rights_reserved(self):
        """Test removal of 'All Rights Reserved'."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nAll Rights Reserved.\nMore content"
        result = normalizer.normalize(text)
        assert "All Rights Reserved" not in result.text

    def test_remove_do_not_distribute(self):
        """Test removal of 'Do Not Distribute'."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nDo Not Distribute\nMore content"
        result = normalizer.normalize(text)
        assert "Do Not Distribute" not in result.text

    def test_preserve_boilerplate_when_disabled(self):
        """Test that boilerplate is preserved when removal is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=False))
        text = "Content\nConfidential\nMore content"
        result = normalizer.normalize(text)
        assert "Confidential" in result.text

    def test_boilerplate_case_insensitive(self):
        """Test that boilerplate removal is case insensitive."""
        normalizer = TextNormalizer(NormalizationConfig(remove_boilerplate=True))
        text = "Content\nCONFIDENTIAL\nMore\nconfidential\nEnd"
        result = normalizer.normalize(text)
        assert "CONFIDENTIAL" not in result.text
        assert "confidential" not in result.text


class TestSpecialCharNormalization:
    """Tests for special character normalization."""

    def test_normalize_curly_double_quotes(self):
        """Test normalization of curly double quotes."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=True))
        text = "\u201cHello World\u201d"
        result = normalizer.normalize(text)
        assert result.text == '"Hello World"'

    def test_normalize_curly_single_quotes(self):
        """Test normalization of curly single quotes."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=True))
        text = "\u2018It\u2019s working\u2019"
        result = normalizer.normalize(text)
        assert result.text == "'It's working'"

    def test_normalize_em_dash(self):
        """Test normalization of em dash."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=True))
        text = "Hello\u2014World"
        result = normalizer.normalize(text)
        assert result.text == "Hello-World"

    def test_normalize_en_dash(self):
        """Test normalization of en dash."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=True))
        text = "2020\u20132024"
        result = normalizer.normalize(text)
        assert result.text == "2020-2024"

    def test_normalize_non_breaking_space(self):
        """Test normalization of non-breaking space."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=True))
        text = "Hello\u00a0World"
        result = normalizer.normalize(text)
        assert result.text == "Hello World"

    def test_normalize_angle_quotes(self):
        """Test normalization of angle quotation marks."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=True))
        text = "\u00abQuoted\u00bb"
        result = normalizer.normalize(text)
        assert result.text == '"Quoted"'

    def test_preserve_special_chars_when_disabled(self):
        """Test that special chars are preserved when normalization is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_special_chars=False))
        text = "\u201cHello\u201d"
        result = normalizer.normalize(text)
        assert "\u201c" in result.text


class TestBulletNormalization:
    """Tests for bullet character normalization."""

    def test_normalize_bullet_point(self):
        """Test normalization of bullet point."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_bullets=True))
        text = "\u2022 First item\n\u2022 Second item"
        result = normalizer.normalize(text)
        assert "- First item" in result.text
        assert "- Second item" in result.text

    def test_normalize_black_circle(self):
        """Test normalization of black circle bullet."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_bullets=True))
        text = "\u25cf Item one\n\u25cf Item two"
        result = normalizer.normalize(text)
        assert "- Item one" in result.text

    def test_normalize_white_bullet(self):
        """Test normalization of white bullet."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_bullets=True))
        text = "\u25e6 Sub-item"
        result = normalizer.normalize(text)
        assert "- Sub-item" in result.text

    def test_preserve_bullets_when_disabled(self):
        """Test that bullets are preserved when normalization is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_bullets=False))
        text = "\u2022 Item"
        result = normalizer.normalize(text)
        assert "\u2022" in result.text


class TestZeroWidthCharRemoval:
    """Tests for zero-width character removal."""

    def test_remove_zero_width_space(self):
        """Test removal of zero-width space."""
        normalizer = TextNormalizer(NormalizationConfig(remove_zero_width=True))
        text = "Hello\u200bWorld"
        result = normalizer.normalize(text)
        assert result.text == "HelloWorld"

    def test_remove_zero_width_joiner(self):
        """Test removal of zero-width joiner."""
        normalizer = TextNormalizer(NormalizationConfig(remove_zero_width=True))
        text = "Test\u200dText"
        result = normalizer.normalize(text)
        assert result.text == "TestText"

    def test_remove_bom(self):
        """Test removal of byte order mark."""
        normalizer = TextNormalizer(NormalizationConfig(remove_zero_width=True))
        text = "\ufeffContent"
        result = normalizer.normalize(text)
        assert result.text == "Content"

    def test_remove_soft_hyphen(self):
        """Test removal of soft hyphen."""
        normalizer = TextNormalizer(NormalizationConfig(remove_zero_width=True))
        text = "Hel\u00adlo"
        result = normalizer.normalize(text)
        assert result.text == "Hello"

    def test_preserve_zero_width_when_disabled(self):
        """Test that zero-width chars are preserved when removal is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(remove_zero_width=False))
        text = "Hello\u200bWorld"
        result = normalizer.normalize(text)
        assert "\u200b" in result.text


class TestWhitespaceNormalization:
    """Tests for whitespace normalization."""

    def test_collapse_multiple_spaces(self):
        """Test collapsing multiple spaces."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_whitespace=True))
        text = "Hello    World"
        result = normalizer.normalize(text)
        assert result.text == "Hello World"

    def test_collapse_multiple_newlines(self):
        """Test collapsing multiple newlines."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_whitespace=True))
        text = "Paragraph 1\n\n\n\n\nParagraph 2"
        result = normalizer.normalize(text)
        assert result.text == "Paragraph 1\n\nParagraph 2"

    def test_remove_trailing_whitespace(self):
        """Test removal of trailing whitespace."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_whitespace=True))
        text = "Line 1   \nLine 2  \t\nLine 3"
        result = normalizer.normalize(text)
        assert "   \n" not in result.text
        assert "\t\n" not in result.text

    def test_normalize_line_endings(self):
        """Test normalization of line endings."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_whitespace=True))
        text = "Line 1\r\nLine 2\rLine 3"
        result = normalizer.normalize(text)
        assert "\r" not in result.text
        assert "Line 1\nLine 2\nLine 3" in result.text

    def test_preserve_whitespace_when_disabled(self):
        """Test that whitespace is preserved when normalization is disabled."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_whitespace=False))
        text = "Hello    World"
        result = normalizer.normalize(text)
        assert "    " in result.text


class TestCodeBlockPreservation:
    """Tests for code block preservation during normalization."""

    def test_preserve_code_block_content(self):
        """Test that content inside code blocks is preserved."""
        normalizer = TextNormalizer(
            NormalizationConfig(
                preserve_code_blocks=True,
                normalize_whitespace=True,
                normalize_special_chars=True,
            )
        )
        text = 'Regular text\n```python\ndef hello():\n    print("Hello    World")\n```\nMore text'
        result = normalizer.normalize(text)
        # Code block content should be preserved as-is
        assert '    print("Hello    World")' in result.text

    def test_preserve_special_chars_in_code_block(self):
        """Test that special characters in code blocks are preserved."""
        normalizer = TextNormalizer(
            NormalizationConfig(
                preserve_code_blocks=True,
                normalize_special_chars=True,
            )
        )
        text = 'Text with \u201cquotes\u201d\n```\nCode with \u201cquotes\u201d\n```'
        result = normalizer.normalize(text)
        # Outside code block - normalized
        assert 'Text with "quotes"' in result.text
        # Inside code block - preserved
        assert '\u201cquotes\u201d' in result.text

    def test_multiple_code_blocks(self):
        """Test preservation of multiple code blocks."""
        normalizer = TextNormalizer(
            NormalizationConfig(preserve_code_blocks=True, normalize_whitespace=True)
        )
        text = "Text\n```\nCode 1\n```\nMiddle\n```\nCode 2\n```\nEnd"
        result = normalizer.normalize(text)
        assert "Code 1" in result.text
        assert "Code 2" in result.text

    def test_code_block_not_preserved_when_disabled(self):
        """Test that code blocks are normalized when preservation is disabled."""
        normalizer = TextNormalizer(
            NormalizationConfig(
                preserve_code_blocks=False,
                normalize_whitespace=True,
            )
        )
        text = "Text\n```\nCode    with    spaces\n```"
        result = normalizer.normalize(text)
        # Spaces should be collapsed when code block preservation is disabled
        # Note: The code block markers will still be present
        assert "Code with spaces" in result.text


class TestConfigurationPresets:
    """Tests for configuration presets."""

    def test_minimal_preset(self):
        """Test minimal normalization preset."""
        normalizer = TextNormalizer.minimal()
        config = normalizer.config

        assert config.remove_page_numbers is False
        assert config.remove_headers_footers is False
        assert config.remove_boilerplate is False
        assert config.normalize_whitespace is True
        assert config.normalize_special_chars is True
        assert config.normalize_bullets is False
        assert config.remove_zero_width is True

    def test_aggressive_preset(self):
        """Test aggressive normalization preset."""
        normalizer = TextNormalizer.aggressive()
        config = normalizer.config

        assert config.remove_page_numbers is True
        assert config.remove_headers_footers is True
        assert config.remove_boilerplate is True
        assert config.normalize_whitespace is True
        assert config.normalize_special_chars is True
        assert config.normalize_bullets is True
        assert config.remove_zero_width is True
        assert config.min_line_length == 3
        assert config.header_footer_threshold == 2

    def test_minimal_preserves_page_numbers(self):
        """Test that minimal preset preserves page numbers."""
        normalizer = TextNormalizer.minimal()
        text = "Content\nPage 1\nMore content"
        result = normalizer.normalize(text)
        assert "Page 1" in result.text

    def test_aggressive_removes_all_noise(self):
        """Test that aggressive preset removes all noise."""
        normalizer = TextNormalizer.aggressive()
        text = "Confidential\nContent\nPage 1\nHeader\nMore\nHeader"
        result = normalizer.normalize(text)
        assert "Confidential" not in result.text
        assert "Page 1" not in result.text


class TestCustomPatterns:
    """Tests for custom pattern support."""

    def test_custom_pattern_removal(self):
        """Test removal using custom regex pattern."""
        config = NormalizationConfig(
            custom_patterns=[r"^\s*REF:\s*\d+\s*$"]
        )
        normalizer = TextNormalizer(config)
        text = "Content\nREF: 12345\nMore content"
        result = normalizer.normalize(text)
        assert "REF: 12345" not in result.text
        assert "custom_patterns" in result.rules_applied

    def test_multiple_custom_patterns(self):
        """Test removal using multiple custom patterns."""
        config = NormalizationConfig(
            custom_patterns=[
                r"^\s*ID:\s*\w+\s*$",
                r"^\s*DATE:\s*\d{4}-\d{2}-\d{2}\s*$",
            ]
        )
        normalizer = TextNormalizer(config)
        text = "Content\nID: ABC123\nDATE: 2024-01-15\nMore content"
        result = normalizer.normalize(text)
        assert "ID: ABC123" not in result.text
        assert "DATE: 2024-01-15" not in result.text


class TestCustomReplacements:
    """Tests for custom character replacements."""

    def test_custom_replacement(self):
        """Test custom character replacement."""
        config = NormalizationConfig(
            custom_replacements={"[TM]": "(TM)", "[R]": "(R)"}
        )
        normalizer = TextNormalizer(config)
        text = "Product[TM] and Brand[R]"
        result = normalizer.normalize(text)
        assert "Product(TM)" in result.text
        assert "Brand(R)" in result.text

    def test_custom_replacement_count(self):
        """Test that custom replacements are counted."""
        config = NormalizationConfig(
            custom_replacements={"XX": "YY"}
        )
        normalizer = TextNormalizer(config)
        text = "XX and XX and XX"
        result = normalizer.normalize(text)
        assert result.removed_patterns.get("custom_replacements", 0) == 3


class TestYAMLConfiguration:
    """Tests for YAML configuration loading."""

    def test_load_from_yaml(self, tmp_path: Path):
        """Test loading configuration from YAML file."""
        yaml_content = """
remove_page_numbers: true
remove_headers_footers: false
remove_boilerplate: true
normalize_whitespace: true
normalize_special_chars: false
min_line_length: 5
header_footer_threshold: 3
custom_patterns:
  - "^\\\\s*TEST:\\\\s*\\\\d+\\\\s*$"
custom_replacements:
  "[X]": "[REDACTED]"
"""
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        normalizer = TextNormalizer.from_yaml(yaml_path)

        assert normalizer.config.remove_page_numbers is True
        assert normalizer.config.remove_headers_footers is False
        assert normalizer.config.normalize_special_chars is False
        assert normalizer.config.min_line_length == 5
        assert normalizer.config.header_footer_threshold == 3

    def test_yaml_file_not_found(self, tmp_path: Path):
        """Test error when YAML file doesn't exist."""
        yaml_path = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            TextNormalizer.from_yaml(yaml_path)

    def test_yaml_empty_file(self, tmp_path: Path):
        """Test loading empty YAML file uses defaults."""
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("", encoding="utf-8")

        normalizer = TextNormalizer.from_yaml(yaml_path)

        # Should use default values
        assert normalizer.config.remove_page_numbers is True
        assert normalizer.config.normalize_whitespace is True


class TestNormalizationResult:
    """Tests for NormalizationResult metadata."""

    def test_result_lengths(self):
        """Test that result contains correct length information."""
        normalizer = TextNormalizer(NormalizationConfig())
        text = "Hello\u200b World\nPage 1\nEnd"
        result = normalizer.normalize(text)

        assert result.original_length == len(text)
        assert result.normalized_length == len(result.text)
        assert result.normalized_length < result.original_length

    def test_result_rules_applied(self):
        """Test that result tracks which rules were applied."""
        normalizer = TextNormalizer(
            NormalizationConfig(
                remove_page_numbers=True,
                remove_zero_width=True,
                normalize_whitespace=True,
            )
        )
        text = "Hello\u200bWorld\nPage 1\nEnd"
        result = normalizer.normalize(text)

        assert "remove_zero_width" in result.rules_applied
        assert "remove_page_numbers" in result.rules_applied
        assert "normalize_whitespace" in result.rules_applied

    def test_result_removed_patterns_count(self):
        """Test that result tracks counts of removed patterns."""
        normalizer = TextNormalizer(
            NormalizationConfig(remove_page_numbers=True)
        )
        text = "Content\nPage 1\nMore\nPage 2\nPage 3\nEnd"
        result = normalizer.normalize(text)

        assert result.removed_patterns.get("page_numbers", 0) == 3


class TestDocumentLoaderIntegration:
    """Tests for integration with DocumentLoader."""

    def test_loader_with_normalizer(self, tmp_path: Path):
        """Test DocumentLoader with TextNormalizer integration."""
        from ingestion.loader import DocumentLoader

        # Create a test file
        test_file = tmp_path / "test.md"
        test_file.write_text(
            "# Title\nConfidential\nContent here\nPage 1\n\u201cQuoted\u201d",
            encoding="utf-8",
        )

        normalizer = TextNormalizer.aggressive()
        loader = DocumentLoader(input_root=tmp_path, normalizer=normalizer)

        document, _ = loader.load(test_file)

        # Check normalization was applied
        assert "Confidential" not in document.text
        assert "Page 1" not in document.text
        assert '"Quoted"' in document.text

        # Check normalization metadata
        assert "normalization" in document.metadata
        assert "rules_applied" in document.metadata["normalization"]

    def test_loader_without_normalizer(self, tmp_path: Path):
        """Test DocumentLoader without TextNormalizer."""
        from ingestion.loader import DocumentLoader

        # Create a test file
        test_file = tmp_path / "test.md"
        test_file.write_text(
            "Confidential\nContent here\nPage 1",
            encoding="utf-8",
        )

        loader = DocumentLoader(input_root=tmp_path)

        document, _ = loader.load(test_file)

        # Boilerplate should still be present
        assert "Confidential" in document.text
        assert "Page 1" in document.text

        # No normalization metadata
        assert "normalization" not in document.metadata

    def test_loader_normalization_metadata(self, tmp_path: Path):
        """Test that normalization metadata is correctly recorded."""
        from ingestion.loader import DocumentLoader

        test_file = tmp_path / "test.md"
        test_file.write_text(
            "Content\nPage 1\nPage 2\nMore content",
            encoding="utf-8",
        )

        normalizer = TextNormalizer(NormalizationConfig(remove_page_numbers=True))
        loader = DocumentLoader(input_root=tmp_path, normalizer=normalizer)

        document, _ = loader.load(test_file)

        normalization_meta = document.metadata.get("normalization", {})
        assert normalization_meta.get("removed_patterns", {}).get("page_numbers", 0) == 2


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_text(self):
        """Test normalization of empty text."""
        normalizer = TextNormalizer(NormalizationConfig())
        result = normalizer.normalize("")
        assert result.text == ""
        assert result.original_length == 0
        assert result.normalized_length == 0

    def test_whitespace_only_text(self):
        """Test normalization of whitespace-only text."""
        normalizer = TextNormalizer(NormalizationConfig(normalize_whitespace=True))
        result = normalizer.normalize("   \n\n\t  ")
        assert result.text == ""

    def test_very_long_text(self):
        """Test normalization of very long text."""
        normalizer = TextNormalizer(NormalizationConfig())
        long_text = "Content. " * 10000
        result = normalizer.normalize(long_text)
        assert len(result.text) > 0

    def test_unicode_heavy_text(self):
        """Test normalization of Unicode-heavy text."""
        normalizer = TextNormalizer(
            NormalizationConfig(
                normalize_special_chars=True,
                remove_zero_width=True,
            )
        )
        text = "\u201c\u4e2d\u6587\u201d \u200b\u2022 \u0420\u0443\u0441\u0441\u043a\u0438\u0439"
        result = normalizer.normalize(text)
        # Chinese and Russian characters should be preserved
        assert "\u4e2d\u6587" in result.text
        assert "\u0420\u0443\u0441\u0441\u043a\u0438\u0439" in result.text
        # Special chars should be normalized
        assert "\u201c" not in result.text
        assert "\u200b" not in result.text

    def test_nested_code_blocks(self):
        """Test handling of nested code block markers."""
        normalizer = TextNormalizer(
            NormalizationConfig(preserve_code_blocks=True)
        )
        text = "```\nShow how to use:\n```python\ncode\n```\n```"
        result = normalizer.normalize(text)
        # Should handle this gracefully
        assert "```" in result.text

    def test_no_rules_applied(self):
        """Test when no normalization rules match."""
        normalizer = TextNormalizer(
            NormalizationConfig(
                remove_page_numbers=True,
                remove_boilerplate=True,
            )
        )
        text = "Simple clean text without any issues."
        result = normalizer.normalize(text)
        # Only whitespace normalization should be applied
        assert "Simple clean text" in result.text
        assert result.removed_patterns.get("page_numbers", 0) == 0
        assert result.removed_patterns.get("boilerplate", 0) == 0
