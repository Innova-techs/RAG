# Document Metadata Schema

This document describes the metadata schema used by the RAG ingestion pipeline. Metadata is extracted during document loading and stored in the manifest and chunk files.

## Core Metadata Fields

These fields are present for all document types:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title (extracted or filename fallback) |
| `source_path` | string | Absolute path to the source file |
| `relative_path` | string | Path relative to input directory |
| `file_extension` | string | File extension without dot (e.g., "pdf", "docx") |
| `size_bytes` | integer | File size in bytes |
| `last_modified` | string (ISO 8601) | File system modification timestamp |
| `content_hash` | string | SHA-256 hash of file contents |
| `ingestion_timestamp` | string (ISO 8601) | UTC timestamp when document was ingested |

## Optional Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `author` | string | Document author |
| `creation_date` | string (ISO 8601) | Document creation date |
| `modification_date` | string (ISO 8601) | Document modification date |
| `subject` | string | Document subject |

## PDF-Specific Metadata

| Field | Type | Description |
|-------|------|-------------|
| `page_count` | integer | Number of pages |
| `is_encrypted` | boolean | Whether PDF is encrypted |
| `creator` | string | Application that created the PDF |
| `producer` | string | PDF producer software |
| `failed_pages` | array[integer] | List of page numbers that failed to extract |
| `parse_warning` | string | Warning message if partial extraction occurred |

## DOCX-Specific Metadata

| Field | Type | Description |
|-------|------|-------------|
| `paragraph_count` | integer | Number of paragraphs |
| `table_count` | integer | Number of tables |
| `has_headers` | boolean | Document has headers |
| `has_footers` | boolean | Document has footers |
| `keywords` | string | Document keywords |
| `category` | string | Document category |
| `comments` | string | Document comments |
| `last_modified_by` | string | Last person to modify |
| `revision` | integer | Revision number |

## Markdown/Text-Specific Metadata

| Field | Type | Description |
|-------|------|-------------|
| `line_count` | integer | Number of lines |
| `has_frontmatter` | boolean | YAML front matter present |
| `headers` | object | Count by level: `{"h1": 2, "h2": 5}` |
| `code_blocks` | integer | Number of fenced code blocks |
| `list_items` | integer | Number of list items |
| `link_count` | integer | Number of markdown links |
| `tags` | array[string] | Tags from front matter |
| `description` | string | Description from front matter |
| `categories` | array[string] | Categories from front matter |
| `encoding_fallback` | string | Encoding used if UTF-8 failed |

## Normalization Metadata

When text normalization is applied, this nested object is included:

| Field | Type | Description |
|-------|------|-------------|
| `normalization.original_length` | integer | Character count before normalization |
| `normalization.normalized_length` | integer | Character count after normalization |
| `normalization.rules_applied` | array[string] | List of normalization rules applied |
| `normalization.removed_patterns` | array[string] | Patterns that were removed |

## Example: PDF Document

```json
{
  "title": "Technical Report 2024",
  "author": "John Smith",
  "creation_date": "2024-01-15T10:30:00",
  "source_path": "/data/raw/reports/tech-report.pdf",
  "relative_path": "reports/tech-report.pdf",
  "file_extension": "pdf",
  "size_bytes": 1048576,
  "last_modified": "2024-01-20T14:00:00",
  "content_hash": "a1b2c3d4...",
  "ingestion_timestamp": "2024-12-31T10:00:00Z",
  "page_count": 25,
  "is_encrypted": false,
  "creator": "Microsoft Word",
  "producer": "Adobe PDF Library"
}
```

## Example: Markdown Document

```json
{
  "title": "Getting Started Guide",
  "author": "Jane Doe",
  "creation_date": "2024-06-01",
  "source_path": "/data/raw/docs/guide.md",
  "relative_path": "docs/guide.md",
  "file_extension": "md",
  "size_bytes": 8192,
  "last_modified": "2024-06-15T09:00:00",
  "content_hash": "e5f6g7h8...",
  "ingestion_timestamp": "2024-12-31T10:00:00Z",
  "has_frontmatter": true,
  "tags": ["tutorial", "beginner"],
  "headers": {"h1": 1, "h2": 4, "h3": 8},
  "code_blocks": 5,
  "line_count": 150
}
```

## Title Fallback Logic

When `title` is not available in document properties:

1. **PDF**: Uses filename (without extension)
2. **DOCX**: Uses filename (without extension)
3. **Markdown**: Uses first H1 header, then filename (without extension)
