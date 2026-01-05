"""Download and cache the embedding model locally for offline use."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download embedding model for offline use.",
    )
    parser.add_argument(
        "--model-name",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="HuggingFace model name to download.",
    )
    parser.add_argument(
        "--output-dir",
        default="models",
        help="Directory to save the model.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading model: {args.model_name}")
    print(f"Output directory: {output_dir.absolute()}")

    try:
        from sentence_transformers import SentenceTransformer

        # Download and save model
        model = SentenceTransformer(args.model_name)

        # Create a clean model name for the folder
        model_folder = args.model_name.replace("/", "_")
        save_path = output_dir / model_folder

        model.save(str(save_path))
        print(f"\nModel saved to: {save_path}")
        print(f"\nTo use this model, set --embedding-model to: {save_path}")

        # Test the saved model
        print("\nTesting saved model...")
        loaded_model = SentenceTransformer(str(save_path))
        test_embedding = loaded_model.encode(["test sentence"])
        print(f"Model loaded successfully. Embedding dimensions: {len(test_embedding[0])}")

        return 0

    except Exception as e:
        print(f"Error downloading model: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
