# Embedding Models

This directory contains locally cached embedding models for offline use.

## Download Model

Run the following command to download the default embedding model:

```bash
python -m scripts.download_model --output-dir models
```

This will download `sentence-transformers/all-MiniLM-L6-v2` (~80MB) to:
```
models/sentence-transformers_all-MiniLM-L6-v2/
```

## Usage

The code automatically detects models in this directory. No configuration needed.

## Why Local Models?

- **Corporate environments**: SSL certificate issues with HuggingFace
- **Offline deployments**: No internet access required
- **Reproducibility**: Same model version across environments
