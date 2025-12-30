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

## Architecture

### Data Flow
```
data/raw/ (PDF, DOCX, MD, TXT)
    → [ingestion] → data/processed/chunks/*.jsonl + manifest.json
    → [indexing]  → data/vectorstore/ (Chroma)
    → [query]     → Top-k semantic matches
```

### Package Structure

**ingestion/** - Document parsing and chunking
- `loader.py`: Multi-format document loading (PDF via PyPDF2, DOCX via python-docx)
- `chunker.py`: Paragraph-aware chunking (~400 tokens, 80-token overlap)
- `storage.py`: JSONL chunk persistence with manifest tracking
- `pipeline.py`: `IngestionPipeline` orchestrates discover → load → chunk → store

**indexing/** - Vector database operations
- `chroma_store.py`: Chroma persistence with cosine distance
- `embeddings.py`: SentenceTransformer wrapper (default: all-MiniLM-L6-v2)
- `dataset.py`: Loads chunks from manifest/JSONL files
- `pipeline.py`: `ChromaIndexingPipeline` handles batch embedding and upsert

**scripts/** - CLI entry points for each pipeline stage

### Key Design Patterns

- **Idempotency**: Content SHA256 hashes in `manifest.json` prevent reprocessing unchanged documents
- **Chunk IDs**: Format `{doc_id}::chunk-{index:04d}` enables selective re-indexing
- **Batch Processing**: Configurable batch sizes for embedding and upsert operations
- **Fail-fast Mode**: Optional `--fail-fast` flag to stop on first error vs. continue with failures

### Configuration Defaults
- Chunk size: 400 tokens
- Chunk overlap: 80 tokens
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Vector metric: Cosine distance
- Upsert batch size: 32 chunks
