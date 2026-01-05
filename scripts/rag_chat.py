"""CLI for RAG-powered chat with the indexed document collection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from generation.api_client import LLMClient, LLMConfig
from generation.rag_chain import RAGChain, RAGConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query the RAG system with LLM-powered responses.",
    )
    parser.add_argument(
        "--vectorstore-dir",
        default="data/vectorstore",
        help="Directory where Chroma persistence files live.",
    )
    parser.add_argument(
        "--collection-name",
        default="pilot-docs",
        help="Chroma collection to query.",
    )
    parser.add_argument(
        "--embedding-model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="SentenceTransformer model used to embed query text.",
    )
    parser.add_argument(
        "--question",
        "-q",
        help="Single question to ask (omit for interactive mode).",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Top-K chunks to retrieve for context.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1000,
        help="Maximum tokens in LLM response.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="LLM temperature (0.0-1.0).",
    )
    parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Show retrieved source chunks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output response as JSON (single question mode only).",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive chat mode.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with API credentials.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Load environment variables
    env_path = Path(args.env_file)
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # Try default locations

    # Validate vectorstore exists
    vectorstore_path = Path(args.vectorstore_dir)
    if not vectorstore_path.exists():
        print(f"[error] Vector store path {vectorstore_path} not found.", file=sys.stderr)
        print("Run the indexing pipeline first:", file=sys.stderr)
        print("  python -m scripts.index_chunks --processed-dir data/processed", file=sys.stderr)
        return 1

    # Initialize LLM client
    try:
        llm_config = LLMConfig.from_env()
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        print("\nRequired environment variables:", file=sys.stderr)
        print("  API_KEY - Your API key", file=sys.stderr)
        print("  API_SECRET - Your API secret", file=sys.stderr)
        print("  BASE_URL - API base URL", file=sys.stderr)
        return 1

    llm_client = LLMClient(llm_config)

    # Initialize RAG chain
    rag_config = RAGConfig(
        vectorstore_dir=vectorstore_path,
        collection_name=args.collection_name,
        embedding_model=args.embedding_model,
        top_k=args.k,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    rag_chain = RAGChain(llm_client, rag_config)

    # Determine mode
    if args.interactive or (not args.question):
        # Interactive mode
        rag_chain.chat_loop(k=args.k, show_sources=args.show_sources)
        return 0

    # Single question mode
    try:
        response = rag_chain.query(
            args.question,
            k=args.k,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    if args.json:
        output = {
            "question": args.question,
            "answer": response.answer,
            "sources": [
                {
                    "text": chunk[:200] + "..." if len(chunk) > 200 else chunk,
                    "metadata": metadata,
                    "distance": distance,
                }
                for chunk, metadata, distance in zip(
                    response.retrieved_chunks,
                    response.metadatas,
                    response.distances,
                )
            ],
        }
        json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"Question: {args.question}\n")
        print(f"Answer: {response.answer}\n")

        if args.show_sources:
            print("--- Sources ---")
            for i, (chunk, metadata, distance) in enumerate(
                zip(response.retrieved_chunks, response.metadatas, response.distances),
                start=1,
            ):
                source = metadata.get("relative_path", "unknown")
                page = metadata.get("page", "")
                page_str = f" (page {page})" if page else ""
                snippet = chunk[:100].replace("\n", " ") + "..."
                print(f"  [{i}] {source}{page_str} (dist: {distance:.4f})")
                print(f"      {snippet}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
