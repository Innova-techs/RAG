# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG MVP - A Python-based Retrieval Augmented Generation system for semantic document search. The pipeline ingests documents, chunks them, generates embeddings, and stores them in a Chroma vector database for retrieval.

## Commands

### Setup
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Run Ingestion Pipeline
```bash
python -m scripts.ingest --input-dir data/raw --output-dir data/processed --verbose
```

### Run Indexing Pipeline
```bash
python -m scripts.index_chunks --processed-dir data/processed --chroma-dir data/vectorstore --verbose
```

### Query the Vector Store
```bash
python -m scripts.query_chunks --question "Your question here" --k 3 --pretty
```

### Re-index Specific Documents
```bash
python -m scripts.index_chunks --doc-ids doc-id-1 doc-id-2 --verbose
```

### RAG Chat (Query with LLM Response)
```bash
# Single question
python -m scripts.rag_chat --question "What are the key findings?" --k 5

# Interactive chat mode
python -m scripts.rag_chat --interactive

# Show retrieved sources
python -m scripts.rag_chat -q "What skills are in demand?" --show-sources

# JSON output
python -m scripts.rag_chat -q "Summarize the report" --json
```

**Required environment variables** (in `.env`):
```
API_KEY=your_api_key
API_SECRET=your_api_secret
BASE_URL=https://your-llm-api-endpoint
```

## Architecture

### Data Flow
```
data/raw/ (PDF, DOCX, MD, TXT)
    → [ingestion]  → data/processed/chunks/*.jsonl + manifest.json + failures.json + ingestion-report.json
    → [indexing]   → data/vectorstore/ (Chroma)
    → [query]      → Top-k semantic matches
    → [generation] → LLM-powered answers with retrieved context
```

### Package Structure

**ingestion/** - Document parsing and chunking
- `loader.py`: Multi-format document loading (PDF via PyPDF2, DOCX via python-docx)
- `chunker.py`: Paragraph-aware chunking (~400 tokens, 80-token overlap)
- `storage.py`: JSONL chunk persistence, manifest tracking, failure/report storage
- `pipeline.py`: `IngestionPipeline` orchestrates discover → load → chunk → store
- `normalizer.py`: Configurable text normalization with `TextNormalizer` and `NormalizationConfig`
- `normalization_rules.py`: Pre-defined regex patterns for page numbers, boilerplate, special chars
- `models.py`: Data models (`Document`, `DocumentChunk`, `FailureInfo`)

**indexing/** - Vector database operations
- `chroma_store.py`: Chroma persistence with cosine distance
- `embeddings.py`: `EmbeddingService` with retry logic, `EmbeddingConfig`, `EmbeddingError`
- `dataset.py`: Loads chunks from manifest/JSONL files
- `pipeline.py`: `ChromaIndexingPipeline` handles batch embedding and upsert with failure tolerance

**generation/** - LLM-powered response generation
- `api_client.py`: HMAC-authenticated LLM client with `LLMClient`, `LLMConfig`
- `rag_chain.py`: `RAGChain` combines retrieval and generation

**scripts/** - CLI entry points for each pipeline stage

### Key Design Patterns

- **Idempotency**: Content SHA256 hashes in `manifest.json` prevent reprocessing unchanged documents
- **Chunk IDs**: Format `{doc_id}::chunk-{index:04d}` enables selective re-indexing
- **Batch Processing**: Configurable batch sizes for embedding and upsert operations
- **Fail-fast Mode**: Optional `--fail-fast` flag to stop on first error vs. continue with failures
- **Failure Tolerance**: Failed documents are logged with full details and can be retried independently

### Configuration Defaults
- Chunk size: 400 tokens
- Chunk overlap: 80 tokens
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Embedding dimensions: 384
- Vector metric: Cosine distance
- Upsert batch size: 32 chunks
- Embedding retries: 3 (with exponential backoff)
- RAG retrieval: Top-5 chunks
- LLM temperature: 0.7
- LLM max tokens: 1000

### Text Normalization

The ingestion pipeline includes configurable text normalization applied after document parsing:

**Components:**
- `NormalizationConfig`: Dataclass with all configuration options
- `TextNormalizer`: Applies configured rules to document text
- `NormalizationResult`: Contains normalized text and metadata

**Normalization Order:**
1. Zero-width character removal
2. Special character normalization (smart quotes → ASCII)
3. Bullet character normalization
4. Page number removal
5. Boilerplate removal (confidential, copyright, etc.)
6. Header/footer removal (repeated lines)
7. Custom pattern/replacement application
8. Whitespace normalization

**CLI Usage:**
```bash
# Default normalization (all features enabled)
python -m scripts.ingest --input-dir data/raw --output-dir data/processed

# Minimal (whitespace and special chars only)
python -m scripts.ingest --normalize minimal

# Aggressive (stricter thresholds)
python -m scripts.ingest --normalize aggressive

# Disable normalization
python -m scripts.ingest --normalize none

# Custom YAML config
python -m scripts.ingest --normalize-config config/normalization.yaml

# Disable specific features
python -m scripts.ingest --no-remove-page-numbers --no-remove-boilerplate
```

**Normalization Presets:**
- `default`: All features enabled with balanced thresholds
- `minimal`: Only whitespace/special chars (preserves structure)
- `aggressive`: All features with stricter header/footer detection
- `none`: No normalization applied

### Batch Processing with Failure Tolerance

The ingestion pipeline continues processing on individual document failures and provides detailed failure reporting:

**Output Files:**
- `failures.json`: Structured failure data with error type, message, and full traceback
- `ingestion-report.json`: Run summary with timing, counts, and failure list

**CLI Usage:**
```bash
# Normal batch run (continues on failures)
python -m scripts.ingest --input-dir data/raw --output-dir data/processed

# Retry only previously failed documents
python -m scripts.ingest --retry-failed --output-dir data/processed

# Stop on first failure
python -m scripts.ingest --fail-fast --input-dir data/raw --output-dir data/processed
```

**FailureInfo Model:**
- `source_path`: Path to failed document
- `error_type`: Exception class name
- `error_message`: Error description
- `traceback`: Full stack trace for debugging
- `timestamp`: When the failure occurred

### Migration Notes

#### Chunk Metadata Indexing (PR #48)
- **New metadata fields**: `page`, `section`, `timestamp` added to indexed chunks
- **Backward compatibility**: Existing chunks will not have `page`/`section` metadata until documents are re-ingested
- **Recommendation**: Re-run ingestion and indexing pipelines to populate new metadata for all documents:
  ```bash
  python -m scripts.ingest --input-dir data/raw --output-dir data/processed --verbose
  python -m scripts.index_chunks --processed-dir data/processed --chroma-dir data/vectorstore --verbose
  ```
