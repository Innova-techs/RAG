"""Unit tests for document loaders (PDF, DOCX, Markdown)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.loader import (
    DocumentParseError,
    load_docx,
    load_markdown,
    load_pdf,
)


class TestPDFLoader:
    """Tests for PDF parser functionality."""

    def test_load_pdf_single_page(self, tmp_path: Path):
        """Test PDF with single page extracts text correctly."""
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Hello World"
            mock_reader.return_value.pages = [mock_page]
            mock_reader.return_value.is_encrypted = False

            pdf_path = tmp_path / "test.pdf"
            pdf_path.touch()

            text, metadata = load_pdf(pdf_path)

            assert text == "Hello World"
            assert metadata["page_count"] == 1
            assert metadata["is_encrypted"] is False

    def test_load_pdf_multi_page(self, tmp_path: Path):
        """Test PDF with multiple pages extracts all text."""
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_pages = []
            for i in range(3):
                mock_page = MagicMock()
                mock_page.extract_text.return_value = f"Page {i + 1} content"
                mock_pages.append(mock_page)

            mock_reader.return_value.pages = mock_pages
            mock_reader.return_value.is_encrypted = False

            pdf_path = tmp_path / "test.pdf"
            pdf_path.touch()

            text, metadata = load_pdf(pdf_path)

            assert "Page 1 content" in text
            assert "Page 2 content" in text
            assert "Page 3 content" in text
            assert metadata["page_count"] == 3

    def test_load_pdf_encrypted(self, tmp_path: Path):
        """Test encrypted PDF returns empty content with warning."""
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_reader.return_value.pages = []
            mock_reader.return_value.is_encrypted = True

            pdf_path = tmp_path / "encrypted.pdf"
            pdf_path.touch()

            text, metadata = load_pdf(pdf_path)

            assert text == ""
            assert metadata["is_encrypted"] is True
            assert metadata["parse_warning"] == "encrypted_pdf"

    def test_load_pdf_partial_extraction_failure(self, tmp_path: Path):
        """Test PDF with some pages failing extraction handles gracefully."""
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Good page"

            mock_page2 = MagicMock()
            mock_page2.extract_text.side_effect = Exception("Extraction failed")

            mock_page3 = MagicMock()
            mock_page3.extract_text.return_value = "Another good page"

            mock_reader.return_value.pages = [mock_page1, mock_page2, mock_page3]
            mock_reader.return_value.is_encrypted = False

            pdf_path = tmp_path / "partial.pdf"
            pdf_path.touch()

            text, metadata = load_pdf(pdf_path)

            assert "Good page" in text
            assert "Another good page" in text
            assert metadata["failed_pages"] == [2]
            assert "partial_extraction" in metadata.get("parse_warning", "")

    def test_load_pdf_corrupted_raises_error(self, tmp_path: Path):
        """Test corrupted PDF raises DocumentParseError."""
        from PyPDF2.errors import PdfReadError

        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_reader.side_effect = PdfReadError("Corrupted PDF")

            pdf_path = tmp_path / "corrupted.pdf"
            pdf_path.touch()

            with pytest.raises(DocumentParseError) as exc_info:
                load_pdf(pdf_path)

            assert "Corrupted PDF" in str(exc_info.value)

    def test_load_pdf_empty_pages(self, tmp_path: Path):
        """Test PDF with empty pages handles None text."""
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = None

            mock_reader.return_value.pages = [mock_page]
            mock_reader.return_value.is_encrypted = False

            pdf_path = tmp_path / "empty.pdf"
            pdf_path.touch()

            text, metadata = load_pdf(pdf_path)

            assert text == ""
            assert metadata["page_count"] == 1


class TestDOCXLoader:
    """Tests for DOCX parser functionality."""

    def test_load_docx_paragraphs(self, tmp_path: Path):
        """Test DOCX with paragraphs extracts text correctly."""
        with patch("docx.Document") as mock_doc:
            mock_para1 = MagicMock()
            mock_para1.text = "First paragraph"
            mock_para2 = MagicMock()
            mock_para2.text = "Second paragraph"

            mock_doc.return_value.paragraphs = [mock_para1, mock_para2]
            mock_doc.return_value.tables = []
            mock_doc.return_value.sections = []

            docx_path = tmp_path / "test.docx"
            docx_path.touch()

            text, metadata = load_docx(docx_path)

            assert "First paragraph" in text
            assert "Second paragraph" in text
            assert metadata["paragraph_count"] == 2

    def test_load_docx_with_tables(self, tmp_path: Path):
        """Test DOCX with tables extracts table content."""
        with patch("docx.Document") as mock_doc:
            mock_doc.return_value.paragraphs = []

            # Mock table with rows and cells
            mock_cell1 = MagicMock()
            mock_cell1.text = "Header 1"
            mock_cell2 = MagicMock()
            mock_cell2.text = "Header 2"

            mock_cell3 = MagicMock()
            mock_cell3.text = "Data 1"
            mock_cell4 = MagicMock()
            mock_cell4.text = "Data 2"

            mock_row1 = MagicMock()
            mock_row1.cells = [mock_cell1, mock_cell2]
            mock_row2 = MagicMock()
            mock_row2.cells = [mock_cell3, mock_cell4]

            mock_table = MagicMock()
            mock_table.rows = [mock_row1, mock_row2]

            mock_doc.return_value.tables = [mock_table]
            mock_doc.return_value.sections = []

            docx_path = tmp_path / "tables.docx"
            docx_path.touch()

            text, metadata = load_docx(docx_path)

            assert "[TABLE]" in text
            assert "Header 1 | Header 2" in text
            assert "Data 1 | Data 2" in text
            assert metadata["table_count"] == 1

    def test_load_docx_empty_paragraphs_skipped(self, tmp_path: Path):
        """Test DOCX skips empty paragraphs."""
        with patch("docx.Document") as mock_doc:
            mock_para1 = MagicMock()
            mock_para1.text = "Content"
            mock_para2 = MagicMock()
            mock_para2.text = "   "  # Whitespace only
            mock_para3 = MagicMock()
            mock_para3.text = ""  # Empty

            mock_doc.return_value.paragraphs = [mock_para1, mock_para2, mock_para3]
            mock_doc.return_value.tables = []
            mock_doc.return_value.sections = []

            docx_path = tmp_path / "sparse.docx"
            docx_path.touch()

            text, metadata = load_docx(docx_path)

            assert text == "Content"
            assert metadata["paragraph_count"] == 1

    def test_load_docx_corrupted_raises_error(self, tmp_path: Path):
        """Test corrupted DOCX raises DocumentParseError."""
        import zipfile

        with patch("docx.Document") as mock_doc:
            mock_doc.side_effect = zipfile.BadZipFile("Not a zip file")

            docx_path = tmp_path / "corrupted.docx"
            docx_path.touch()

            with pytest.raises(DocumentParseError) as exc_info:
                load_docx(docx_path)

            assert "Corrupted DOCX" in str(exc_info.value)

    def test_load_docx_with_headers_footers(self, tmp_path: Path):
        """Test DOCX with headers and footers sets metadata flags."""
        with patch("docx.Document") as mock_doc:
            mock_doc.return_value.paragraphs = []
            mock_doc.return_value.tables = []

            # Mock section with header
            mock_header_para = MagicMock()
            mock_header_para.text = "Document Header"
            mock_header = MagicMock()
            mock_header.paragraphs = [mock_header_para]

            mock_footer_para = MagicMock()
            mock_footer_para.text = "Page 1"
            mock_footer = MagicMock()
            mock_footer.paragraphs = [mock_footer_para]

            mock_section = MagicMock()
            mock_section.header = mock_header
            mock_section.footer = mock_footer

            mock_doc.return_value.sections = [mock_section]

            docx_path = tmp_path / "headers.docx"
            docx_path.touch()

            text, metadata = load_docx(docx_path)

            assert metadata.get("has_headers") is True
            assert metadata.get("has_footers") is True


class TestMarkdownLoader:
    """Tests for Markdown parser functionality."""

    def test_load_markdown_plain_text(self, tmp_path: Path):
        """Test plain text markdown loads correctly."""
        md_path = tmp_path / "plain.md"
        md_path.write_text("Just some plain text content.", encoding="utf-8")

        text, metadata = load_markdown(md_path)

        assert text == "Just some plain text content."
        assert metadata["line_count"] == 1

    def test_load_markdown_headers_detected(self, tmp_path: Path):
        """Test markdown headers are counted in metadata."""
        content = """# Main Title
## Section 1
### Subsection 1.1
## Section 2
### Subsection 2.1
### Subsection 2.2
"""
        md_path = tmp_path / "headers.md"
        md_path.write_text(content, encoding="utf-8")

        text, metadata = load_markdown(md_path)

        assert metadata["headers"]["h1"] == 1
        assert metadata["headers"]["h2"] == 2
        assert metadata["headers"]["h3"] == 3

    def test_load_markdown_code_blocks_detected(self, tmp_path: Path):
        """Test code blocks are counted in metadata."""
        content = """Some text

```python
def hello():
    print("Hello")
```

More text

```javascript
console.log("World");
```
"""
        md_path = tmp_path / "code.md"
        md_path.write_text(content, encoding="utf-8")

        text, metadata = load_markdown(md_path)

        assert metadata["code_blocks"] == 2

    def test_load_markdown_lists_detected(self, tmp_path: Path):
        """Test list items are counted in metadata."""
        content = """Shopping list:
- Apples
- Bananas
* Oranges

Steps:
1. First step
2. Second step
3. Third step
"""
        md_path = tmp_path / "lists.md"
        md_path.write_text(content, encoding="utf-8")

        text, metadata = load_markdown(md_path)

        assert metadata["list_items"] == 6

    def test_load_markdown_links_detected(self, tmp_path: Path):
        """Test links are counted in metadata."""
        content = """Check out [Google](https://google.com) and [GitHub](https://github.com)."""
        md_path = tmp_path / "links.md"
        md_path.write_text(content, encoding="utf-8")

        text, metadata = load_markdown(md_path)

        assert metadata["link_count"] == 2

    def test_load_markdown_frontmatter_detected(self, tmp_path: Path):
        """Test YAML frontmatter is detected."""
        content = """---
title: My Document
author: John Doe
---

# Content starts here
"""
        md_path = tmp_path / "frontmatter.md"
        md_path.write_text(content, encoding="utf-8")

        text, metadata = load_markdown(md_path)

        assert metadata.get("has_frontmatter") is True

    def test_load_markdown_encoding_fallback(self, tmp_path: Path):
        """Test fallback encoding for non-UTF-8 files."""
        md_path = tmp_path / "latin1.md"
        # Write with latin-1 encoding
        md_path.write_bytes("Café résumé naïve".encode("latin-1"))

        text, metadata = load_markdown(md_path)

        assert "Café" in text
        assert metadata.get("encoding_fallback") == "latin-1"

    def test_load_markdown_file_not_found(self, tmp_path: Path):
        """Test missing markdown file raises DocumentParseError."""
        md_path = tmp_path / "missing.md"

        with pytest.raises(DocumentParseError) as exc_info:
            load_markdown(md_path)

        assert "File read error" in str(exc_info.value)


class TestErrorHandling:
    """Tests for error handling across all loaders."""

    def test_pdf_general_exception_handling(self, tmp_path: Path):
        """Test general exceptions in PDF loading are caught."""
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_reader.side_effect = RuntimeError("Unexpected error")

            pdf_path = tmp_path / "error.pdf"
            pdf_path.touch()

            with pytest.raises(DocumentParseError) as exc_info:
                load_pdf(pdf_path)

            assert "PDF read error" in str(exc_info.value)

    def test_docx_package_not_found_error(self, tmp_path: Path):
        """Test PackageNotFoundError in DOCX loading is caught."""
        from docx.opc.exceptions import PackageNotFoundError

        with patch("docx.Document") as mock_doc:
            mock_doc.side_effect = PackageNotFoundError("Package not found")

            docx_path = tmp_path / "notfound.docx"
            docx_path.touch()

            with pytest.raises(DocumentParseError) as exc_info:
                load_docx(docx_path)

            assert "Corrupted DOCX" in str(exc_info.value)
