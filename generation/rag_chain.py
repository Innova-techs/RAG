"""RAG chain combining retrieval and generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from .base import BaseLLMClient
from indexing.embeddings import get_model_path


DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.

Instructions:
- Answer the question using ONLY the information from the context below
- If the context doesn't contain enough information to answer, say so clearly
- Be concise and direct in your responses
- Cite specific details from the context when relevant

Context:
{context}"""


@dataclass
class RetrievalResult:
    """Result from retrieval step."""

    chunks: list[str]
    metadatas: list[dict]
    distances: list[float]
    ids: list[str]


@dataclass
class RAGResponse:
    """Response from RAG chain."""

    answer: str
    retrieved_chunks: list[str]
    metadatas: list[dict]
    distances: list[float]


@dataclass
class RAGConfig:
    """Configuration for RAG chain."""

    vectorstore_dir: Path = field(default_factory=lambda: Path("data/vectorstore"))
    collection_name: str = "pilot-docs"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 5
    max_tokens: int = 1000
    temperature: float = 0.7
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


class RAGChain:
    """RAG chain that retrieves context and generates responses."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        config: Optional[RAGConfig] = None,
    ):
        """Initialize the RAG chain.

        Args:
            llm_client: LLM client for generation. Can be any client
                       implementing the BaseLLMClient protocol.
            config: RAG configuration.
        """
        self.llm_client = llm_client
        self.config = config or RAGConfig()
        self._collection = None
        self._chroma_client = None

    def _get_collection(self):
        """Get or initialize the Chroma collection."""
        if self._collection is None:
            self._chroma_client = chromadb.PersistentClient(
                path=str(self.config.vectorstore_dir)
            )
            # Resolve model path (prefers local model if available)
            resolved_model = get_model_path(self.config.embedding_model)
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=resolved_model,
            )
            self._collection = self._chroma_client.get_collection(
                self.config.collection_name,
                embedding_function=embedding_fn,
            )
        return self._collection

    def retrieve(self, query: str, k: Optional[int] = None) -> RetrievalResult:
        """Retrieve relevant chunks for a query.

        Args:
            query: User query.
            k: Number of results to retrieve (overrides config).

        Returns:
            Retrieved chunks with metadata.
        """
        collection = self._get_collection()
        n_results = k or self.config.top_k

        result = collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0] if result.get("distances") else []

        return RetrievalResult(
            chunks=documents,
            metadatas=metadatas,
            distances=distances,
            ids=ids,
        )

    def _format_context(self, retrieval: RetrievalResult) -> str:
        """Format retrieved chunks as context string.

        Args:
            retrieval: Retrieved chunks.

        Returns:
            Formatted context string.
        """
        context_parts = []
        for i, (chunk, metadata) in enumerate(
            zip(retrieval.chunks, retrieval.metadatas), start=1
        ):
            # Build source info
            source_parts = []
            if "relative_path" in metadata:
                source_parts.append(metadata["relative_path"])
            if "page" in metadata:
                source_parts.append(f"page {metadata['page']}")
            if "section" in metadata:
                source_parts.append(f"section: {metadata['section']}")

            source_info = " | ".join(source_parts) if source_parts else "unknown source"
            context_parts.append(f"[{i}] ({source_info})\n{chunk}")

        return "\n\n---\n\n".join(context_parts)

    def query(
        self,
        question: str,
        k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> RAGResponse:
        """Query the RAG system.

        Args:
            question: User question.
            k: Number of chunks to retrieve.
            max_tokens: Override default max tokens.
            temperature: Override default temperature.

        Returns:
            RAG response with answer and retrieved context.
        """
        # Retrieve relevant chunks
        retrieval = self.retrieve(question, k=k)

        if not retrieval.chunks:
            return RAGResponse(
                answer="I couldn't find any relevant information in the knowledge base.",
                retrieved_chunks=[],
                metadatas=[],
                distances=[],
            )

        # Format context and build prompt
        context = self._format_context(retrieval)
        system_prompt = self.config.system_prompt.format(context=context)

        # Generate response
        answer = self.llm_client.generate(
            prompt=question,
            system_prompt=system_prompt,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
        )

        return RAGResponse(
            answer=answer,
            retrieved_chunks=retrieval.chunks,
            metadatas=retrieval.metadatas,
            distances=retrieval.distances,
        )

    def chat_loop(self, k: Optional[int] = None, show_sources: bool = False):
        """Run an interactive chat loop.

        Args:
            k: Number of chunks to retrieve per query.
            show_sources: Whether to show retrieved sources.
        """
        print("=== RAG Chat ===")
        print("Type 'exit' or 'quit' to end the conversation\n")

        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if question.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            if not question:
                continue

            try:
                response = self.query(question, k=k)
                print(f"\nAssistant: {response.answer}\n")

                if show_sources and response.retrieved_chunks:
                    print("--- Sources ---")
                    for i, (chunk, metadata) in enumerate(
                        zip(response.retrieved_chunks, response.metadatas), start=1
                    ):
                        source = metadata.get("relative_path", "unknown")
                        page = metadata.get("page", "")
                        page_str = f" (page {page})" if page else ""
                        snippet = chunk[:100].replace("\n", " ") + "..."
                        print(f"  [{i}] {source}{page_str}: {snippet}")
                    print()

            except Exception as e:
                print(f"\nError: {e}\n")
