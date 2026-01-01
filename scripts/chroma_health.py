"""CLI script to check Chroma vector store health."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from indexing.chroma_store import health_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Chroma vector store health and status.",
    )
    parser.add_argument(
        "--chroma-dir",
        default="data/vectorstore",
        help="Directory containing Chroma persistence (default: data/vectorstore).",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Specific collection to check (optional).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chroma_path = Path(args.chroma_dir)

    result = health_check(chroma_path, collection_name=args.collection)

    if result.healthy:
        print(f"[OK] {result.message}")
        if result.collection_count > 0:
            print(f"     Collections: {result.collection_count}")
        if result.document_count > 0:
            print(f"     Documents: {result.document_count}")
        return 0
    else:
        print(f"[FAIL] {result.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
