# Vector Collection Schema

This document describes the Chroma vector collection schema used by the RAG indexing pipeline. Chunks are indexed with embeddings and metadata for semantic retrieval.

## Schema Version

**Version:** 1.0.0

## Collection Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Collection Name | `rag-chunks` (default) | Configurable via `--collection` CLI flag |
| Distance Metric | `cosine` | Cosine similarity for semantic search |
| Persistence | `PersistentClient` | Data persisted to disk |
| HNSW Space | `cosine` | Hierarchical Navigable Small World graph |

## Chunk Metadata Fields

### Core Identification

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `doc_id` | string | Yes | Unique document identifier (SHA-256 based) |
| `chunk_id` | string | Yes | Unique chunk identifier: `{doc_id}::chunk-{index:04d}` |
| `chunk_index` | integer | Yes | Zero-based index of chunk within document |

### Source Information (for Citations)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_path` | string | Yes | Absolute path to source document |
| `relative_path` | string | No | Path relative to input directory |
| `file_extension` | string | No | File extension (pdf, docx, md, txt) |
| `page` | integer | No | Page number (1-indexed, PDF only) |
| `section` | string | No | Current section header text |

### Content Tracking

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_hash` | string | Yes | SHA-256 hash of source document |
| `timestamp` | string | No | ISO 8601 ingestion timestamp for freshness queries |

### Chunk Position

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `paragraph_start` | integer | No | Starting paragraph index |
| `paragraph_end` | integer | No | Ending paragraph index |
| `chunk_token_count` | integer | No | Token count of chunk text |

### Access Control (Future)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `acl_read` | string | No | Placeholder for read permissions (comma-separated) |
| `acl_write` | string | No | Placeholder for write permissions (comma-separated) |

## Deterministic Chunk IDs

Chunk IDs follow a deterministic format that enables:
- **Upsert Operations**: Updates overwrite existing chunks without duplicates
- **Selective Re-indexing**: Target specific documents by doc_id
- **Orphan Cleanup**: Identify and remove stale chunks

Format: `{doc_id}::chunk-{index:04d}`

Example: `abc123def456::chunk-0005`

## Re-indexing Behavior

The indexing pipeline supports idempotent re-indexing:

1. **Same Content**: Chunks with matching IDs are upserted (updated)
2. **Modified Content**: New chunks replace old ones via upsert
3. **Deleted Source**: Orphaned chunks are removed via `delete(where={"doc_id": id})`

## Query Capabilities

The schema enables these Chroma `where` filter operations:

```python
# Filter by document
collection.query(where={"doc_id": "abc123"})

# Filter by file type
collection.query(where={"file_extension": "pdf"})

# Filter by timestamp (freshness)
collection.query(where={"timestamp": {"$gte": "2024-01-01"}})

# Filter by page (citations)
collection.query(where={"page": {"$gte": 10, "$lte": 20}})

# Future: Filter by ACL
collection.query(where={"acl_read": {"$contains": "team-a"}})
```

## Example Chunk Metadata

```json
{
  "doc_id": "a1b2c3d4e5f6",
  "chunk_id": "a1b2c3d4e5f6::chunk-0003",
  "chunk_index": 3,
  "source_path": "/data/raw/reports/annual-report.pdf",
  "relative_path": "reports/annual-report.pdf",
  "file_extension": "pdf",
  "content_hash": "sha256:abc123...",
  "timestamp": "2024-12-31T15:30:00Z",
  "page": 5,
  "section": "Financial Summary",
  "paragraph_start": 12,
  "paragraph_end": 18,
  "chunk_token_count": 385,
  "acl_read": "",
  "acl_write": ""
}
```

## Migration Notes

### From v0 (No Schema)
- Add `timestamp` field from `ingestion_timestamp` in manifest
- Add `page` and `section` from chunk metadata
- Add empty `acl_read` and `acl_write` placeholders
- Existing chunks without new fields will have default values

### Future Considerations
- Schema version stored in collection metadata
- Migration scripts for schema updates
- Backward compatibility for older chunks
