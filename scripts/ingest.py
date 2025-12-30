from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ingestion.pipeline import IngestionPipeline, PipelineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-ingest documents (PDF/DOCX/MD) into normalized chunks.",
    )
    parser.add_argument("--input-dir", default="data/raw", help="Directory containing source documents.")
    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory where chunks + manifest will be stored.",
    )
    parser.add_argument("--chunk-size", type=int, default=400, help="Approximate target token count per chunk.")
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=80,
        help="Approximate overlapping tokens retained between chunks.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort immediately on the first failure instead of logging and continuing.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging output.")
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)

    config = PipelineConfig(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        chunk_size_tokens=args.chunk_size,
        chunk_overlap_tokens=args.chunk_overlap,
        fail_fast=args.fail_fast,
    )

    pipeline = IngestionPipeline(config)
    result = pipeline.run()

    logging.info(
        "Ingestion complete: processed=%d skipped=%d failed=%d chunks=%d",
        result.processed,
        result.skipped,
        result.failed,
        result.chunk_count,
    )

    if result.failures:
        logging.info("Failure details:")
        for failure in result.failures:
            logging.info(" - %s", failure)

    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
