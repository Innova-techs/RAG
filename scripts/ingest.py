from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from ingestion.normalizer import NormalizationConfig, TextNormalizer
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

    # Normalization arguments
    normalize_group = parser.add_argument_group("normalization", "Text normalization options")
    normalize_group.add_argument(
        "--normalize",
        choices=["default", "minimal", "aggressive", "none"],
        default="default",
        help="Normalization preset to use (default: default).",
    )
    normalize_group.add_argument(
        "--normalize-config",
        type=str,
        default=None,
        help="Path to YAML configuration file for custom normalization settings.",
    )
    normalize_group.add_argument(
        "--no-remove-page-numbers",
        action="store_true",
        help="Disable removal of page number patterns.",
    )
    normalize_group.add_argument(
        "--no-remove-headers-footers",
        action="store_true",
        help="Disable removal of repeated header/footer lines.",
    )
    normalize_group.add_argument(
        "--no-remove-boilerplate",
        action="store_true",
        help="Disable removal of boilerplate text (confidential, copyright, etc.).",
    )

    return parser.parse_args()


def build_normalization_config(args: argparse.Namespace) -> Optional[NormalizationConfig]:
    """Build a NormalizationConfig from command line arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        NormalizationConfig or None if normalization is disabled.
    """
    # If a YAML config file is provided, load it
    if args.normalize_config:
        normalizer = TextNormalizer.from_yaml(Path(args.normalize_config))
        config = normalizer.config
        # Apply CLI overrides
        if args.no_remove_page_numbers:
            config.remove_page_numbers = False
        if args.no_remove_headers_footers:
            config.remove_headers_footers = False
        if args.no_remove_boilerplate:
            config.remove_boilerplate = False
        return config

    # Handle preset selection
    if args.normalize == "none":
        return None

    if args.normalize == "minimal":
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
    elif args.normalize == "aggressive":
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
    else:  # "default"
        config = NormalizationConfig()

    # Apply CLI overrides
    if args.no_remove_page_numbers:
        config.remove_page_numbers = False
    if args.no_remove_headers_footers:
        config.remove_headers_footers = False
    if args.no_remove_boilerplate:
        config.remove_boilerplate = False

    return config


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)

    # Build normalization configuration
    normalization_config = build_normalization_config(args)

    if normalization_config is not None:
        logging.info("Text normalization enabled with preset: %s", args.normalize)
    else:
        logging.info("Text normalization disabled")

    config = PipelineConfig(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        chunk_size_tokens=args.chunk_size,
        chunk_overlap_tokens=args.chunk_overlap,
        fail_fast=args.fail_fast,
        normalization_config=normalization_config,
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
