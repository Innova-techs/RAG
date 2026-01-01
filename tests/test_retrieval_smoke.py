"""Retrieval smoke test suite (Story #15).

This module provides end-to-end verification of the retrieval pipeline quality.
Tests use real embeddings and a temporary Chroma instance to verify that:
- Expected documents appear in top-k results for sample queries
- Relevance scores meet defined thresholds
- Diverse query types (factual, conceptual) work correctly

Run with: pytest tests/test_retrieval_smoke.py -v
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import chromadb
import pytest

from indexing.embeddings import EmbeddingService

logger = logging.getLogger(__name__)

# Relevance thresholds (cosine distance - lower is better)
# 0.0 = identical, 2.0 = completely different
MAX_ACCEPTABLE_DISTANCE = 1.0  # Maximum distance for "relevant" results
EXPECTED_TOP_DISTANCE = 0.6  # Expected distance for expected top result


@dataclass
class SampleDocument:
    """A sample document with known content for testing."""

    doc_id: str
    title: str
    content: str
    domain: str  # Domain category for organizing test docs


@dataclass
class SmokeTestQuery:
    """A smoke test query with expected results."""

    query: str
    expected_doc_id: str
    query_type: str  # "factual", "conceptual", "keyword"
    description: str


@dataclass
class RetrievalResult:
    """Result of a smoke test query verification."""

    query: str
    passed: bool
    expected_doc_id: str
    found_at_rank: Optional[int]  # Rank where expected doc was found (1-indexed)
    distance: Optional[float]  # Distance of expected doc
    top_results: List[dict] = field(default_factory=list)  # Top-k results for diagnostics
    error_message: str = ""


# Test corpus - diverse documents covering different domains
SAMPLE_DOCUMENTS = [
    SampleDocument(
        doc_id="python-intro",
        title="Introduction to Python Programming",
        content="""Python is a high-level, interpreted programming language known for its
        clear syntax and readability. Created by Guido van Rossum and first released in 1991,
        Python emphasizes code readability with its notable use of significant indentation.
        Python supports multiple programming paradigms including procedural, object-oriented,
        and functional programming. It has a comprehensive standard library and a large
        ecosystem of third-party packages available through PyPI.""",
        domain="programming",
    ),
    SampleDocument(
        doc_id="machine-learning-basics",
        title="Machine Learning Fundamentals",
        content="""Machine learning is a subset of artificial intelligence that enables
        systems to learn and improve from experience without being explicitly programmed.
        The three main types are supervised learning (using labeled data), unsupervised
        learning (finding patterns in unlabeled data), and reinforcement learning (learning
        through rewards and penalties). Common algorithms include decision trees, neural
        networks, support vector machines, and k-means clustering.""",
        domain="ai",
    ),
    SampleDocument(
        doc_id="database-design",
        title="Relational Database Design Principles",
        content="""Relational databases organize data into tables with rows and columns.
        Key concepts include primary keys (unique identifiers), foreign keys (relationships
        between tables), and normalization (reducing data redundancy). SQL (Structured Query
        Language) is the standard language for querying relational databases. Popular systems
        include PostgreSQL, MySQL, Oracle, and Microsoft SQL Server. ACID properties ensure
        transaction reliability.""",
        domain="databases",
    ),
    SampleDocument(
        doc_id="vector-databases",
        title="Vector Databases and Embeddings",
        content="""Vector databases are specialized systems for storing and querying
        high-dimensional vectors, commonly used in machine learning and AI applications.
        They enable similarity search using metrics like cosine similarity and Euclidean
        distance. Popular vector databases include Chroma, Pinecone, Weaviate, and Milvus.
        Embeddings convert text, images, or other data into dense vector representations
        that capture semantic meaning.""",
        domain="databases",
    ),
    SampleDocument(
        doc_id="rag-architecture",
        title="Retrieval Augmented Generation (RAG)",
        content="""RAG combines information retrieval with language model generation to
        provide accurate, grounded responses. The architecture has three main components:
        a document store with embeddings, a retrieval system for finding relevant chunks,
        and a language model that generates responses using retrieved context. This approach
        reduces hallucinations and enables access to domain-specific knowledge not in the
        model's training data.""",
        domain="ai",
    ),
    SampleDocument(
        doc_id="git-version-control",
        title="Git Version Control System",
        content="""Git is a distributed version control system for tracking changes in
        source code during software development. Key concepts include commits (snapshots),
        branches (parallel development lines), and merging. Git enables collaboration through
        remote repositories hosted on platforms like GitHub, GitLab, and Bitbucket. Common
        commands include git clone, git commit, git push, git pull, and git merge.""",
        domain="devops",
    ),
    SampleDocument(
        doc_id="docker-containers",
        title="Docker and Containerization",
        content="""Docker is a platform for developing, shipping, and running applications
        in containers. Containers package an application with its dependencies, ensuring
        consistent behavior across environments. Key concepts include Docker images (templates),
        containers (running instances), Dockerfiles (build instructions), and Docker Compose
        (multi-container applications). Containers are lighter than virtual machines and
        enable microservices architectures.""",
        domain="devops",
    ),
    SampleDocument(
        doc_id="rest-api-design",
        title="REST API Design Best Practices",
        content="""REST (Representational State Transfer) is an architectural style for
        designing networked applications. RESTful APIs use HTTP methods: GET for retrieval,
        POST for creation, PUT/PATCH for updates, and DELETE for removal. Best practices
        include using nouns for resource URLs, proper status codes (200, 201, 400, 404, 500),
        versioning, pagination, and authentication via tokens or OAuth. APIs should be
        stateless and return JSON responses.""",
        domain="web",
    ),
]

# Smoke test queries - diverse types covering different domains
SMOKE_TEST_QUERIES = [
    # Factual queries - specific facts
    SmokeTestQuery(
        query="Who created Python programming language?",
        expected_doc_id="python-intro",
        query_type="factual",
        description="Factual query about Python creator",
    ),
    SmokeTestQuery(
        query="What are the three types of machine learning?",
        expected_doc_id="machine-learning-basics",
        query_type="factual",
        description="Factual query about ML types",
    ),
    SmokeTestQuery(
        query="What does ACID stand for in databases?",
        expected_doc_id="database-design",
        query_type="factual",
        description="Factual query about database concepts",
    ),
    # Conceptual queries - broader understanding
    SmokeTestQuery(
        query="How does RAG help reduce AI hallucinations?",
        expected_doc_id="rag-architecture",
        query_type="conceptual",
        description="Conceptual query about RAG benefits",
    ),
    SmokeTestQuery(
        query="What is the difference between containers and VMs?",
        expected_doc_id="docker-containers",
        query_type="conceptual",
        description="Conceptual query about containerization",
    ),
    SmokeTestQuery(
        query="How do embeddings enable semantic search?",
        expected_doc_id="vector-databases",
        query_type="conceptual",
        description="Conceptual query about embeddings",
    ),
    # Keyword-focused queries
    SmokeTestQuery(
        query="git branching and merging",
        expected_doc_id="git-version-control",
        query_type="keyword",
        description="Keyword query about git operations",
    ),
    SmokeTestQuery(
        query="REST API HTTP methods",
        expected_doc_id="rest-api-design",
        query_type="keyword",
        description="Keyword query about REST methods",
    ),
]


@pytest.fixture(scope="module")
def chroma_client(tmp_path_factory) -> chromadb.PersistentClient:
    """Create a Chroma client for the test module."""
    persist_path = tmp_path_factory.mktemp("chroma")
    return chromadb.PersistentClient(path=str(persist_path))


@pytest.fixture(scope="module")
def embedding_service() -> EmbeddingService:
    """Create an embedding service for tests."""
    return EmbeddingService()


@pytest.fixture(scope="module")
def indexed_collection(chroma_client, embedding_service):
    """Create and populate a test collection with sample documents."""
    collection = chroma_client.create_collection(
        name="smoke-test-collection",
        metadata={"hnsw:space": "cosine"},
    )

    # Index all test documents
    ids = []
    documents = []
    metadatas = []

    for doc in SAMPLE_DOCUMENTS:
        ids.append(doc.doc_id)
        documents.append(doc.content)
        metadatas.append({
            "doc_id": doc.doc_id,
            "title": doc.title,
            "domain": doc.domain,
        })

    # Generate embeddings
    embeddings = embedding_service.embed_batch(documents)

    # Upsert to collection
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    logger.info("Indexed %d test documents for smoke tests", len(ids))
    return collection


def run_smoke_query(
    collection,
    embedding_service: EmbeddingService,
    test_query: SmokeTestQuery,
    k: int = 3,
) -> RetrievalResult:
    """Execute a smoke test query and verify results.

    Args:
        collection: Chroma collection to query.
        embedding_service: Service for generating query embeddings.
        test_query: The smoke test query to execute.
        k: Number of results to retrieve.

    Returns:
        RetrievalResult with pass/fail status and diagnostics.
    """
    # Generate query embedding
    query_embedding = embedding_service.embed_batch([test_query.query])[0]

    # Query collection
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # Build top results for diagnostics
    top_results = []
    for i, (doc_id, doc_text, metadata, distance) in enumerate(
        zip(ids, documents, metadatas, distances)
    ):
        top_results.append({
            "rank": i + 1,
            "doc_id": doc_id,
            "title": metadata.get("title", ""),
            "distance": round(distance, 4),
            "snippet": doc_text[:100] + "..." if len(doc_text) > 100 else doc_text,
        })

    # Check if expected doc is in top-k
    found_at_rank = None
    expected_distance = None

    for i, doc_id in enumerate(ids):
        if doc_id == test_query.expected_doc_id:
            found_at_rank = i + 1
            expected_distance = distances[i]
            break

    # Determine pass/fail
    passed = found_at_rank is not None

    error_message = ""
    if not passed:
        error_message = (
            f"Expected doc '{test_query.expected_doc_id}' not found in top-{k} results. "
            f"Got: {[r['doc_id'] for r in top_results]}"
        )
    elif expected_distance and expected_distance > MAX_ACCEPTABLE_DISTANCE:
        passed = False
        error_message = (
            f"Expected doc found at rank {found_at_rank} but distance {expected_distance:.4f} "
            f"exceeds threshold {MAX_ACCEPTABLE_DISTANCE}"
        )

    return RetrievalResult(
        query=test_query.query,
        passed=passed,
        expected_doc_id=test_query.expected_doc_id,
        found_at_rank=found_at_rank,
        distance=expected_distance,
        top_results=top_results,
        error_message=error_message,
    )


class TestRetrievalSmokeTests:
    """Smoke tests for retrieval quality verification."""

    @pytest.mark.parametrize("test_query", SMOKE_TEST_QUERIES, ids=lambda q: q.description)
    def test_query_finds_expected_document(
        self,
        indexed_collection,
        embedding_service,
        test_query: SmokeTestQuery,
    ):
        """Verify that expected document appears in top-3 results for each query."""
        result = run_smoke_query(
            indexed_collection,
            embedding_service,
            test_query,
            k=3,
        )

        # Log diagnostics on failure
        if not result.passed:
            logger.error(
                "\n=== SMOKE TEST FAILURE ===\n"
                "Query: %s\n"
                "Type: %s\n"
                "Expected: %s\n"
                "Error: %s\n"
                "Top results:\n%s",
                result.query,
                test_query.query_type,
                result.expected_doc_id,
                result.error_message,
                "\n".join(
                    f"  {r['rank']}. {r['doc_id']} (distance={r['distance']}) - {r['title']}"
                    for r in result.top_results
                ),
            )

        assert result.passed, result.error_message

    def test_all_smoke_queries_pass(self, indexed_collection, embedding_service):
        """Summary test: verify all smoke queries pass."""
        results = []
        for test_query in SMOKE_TEST_QUERIES:
            result = run_smoke_query(
                indexed_collection,
                embedding_service,
                test_query,
                k=3,
            )
            results.append(result)

        # Count passes and failures
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]

        # Log summary
        logger.info(
            "\n=== SMOKE TEST SUMMARY ===\n"
            "Passed: %d/%d\n"
            "Failed: %d/%d",
            len(passed),
            len(results),
            len(failed),
            len(results),
        )

        if failed:
            failure_details = "\n".join(
                f"  - {r.query}: {r.error_message}"
                for r in failed
            )
            logger.error("Failed queries:\n%s", failure_details)

        # All queries should pass
        assert len(failed) == 0, f"{len(failed)} smoke test(s) failed"


class TestRelevanceThresholds:
    """Test relevance score thresholds."""

    def test_exact_match_has_low_distance(self, indexed_collection, embedding_service):
        """Querying with exact document content should have very low distance."""
        # Use the first few words of a document as query
        doc = SAMPLE_DOCUMENTS[0]
        query_text = doc.content[:100]

        query_embedding = embedding_service.embed_batch([query_text])[0]
        results = indexed_collection.query(
            query_embeddings=[query_embedding],
            n_results=1,
            include=["distances"],
        )

        distance = results.get("distances", [[]])[0][0]

        # Very similar text should have low distance
        assert distance < EXPECTED_TOP_DISTANCE, (
            f"Exact match query should have distance < {EXPECTED_TOP_DISTANCE}, "
            f"got {distance:.4f}"
        )

    def test_unrelated_query_has_high_distance(self, indexed_collection, embedding_service):
        """Completely unrelated query should have high distance from all docs."""
        # Query about something not in the corpus
        query_text = "Medieval castle architecture and fortification techniques"

        query_embedding = embedding_service.embed_batch([query_text])[0]
        results = indexed_collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            include=["distances"],
        )

        distances = results.get("distances", [[]])[0]

        # All results should have relatively high distances
        avg_distance = sum(distances) / len(distances) if distances else 0

        logger.info(
            "Unrelated query distances: %s (avg=%.4f)",
            [round(d, 4) for d in distances],
            avg_distance,
        )

        # Unrelated query should have higher average distance
        assert avg_distance > 0.5, (
            f"Unrelated query should have avg distance > 0.5, got {avg_distance:.4f}"
        )


class TestQueryDiversity:
    """Test that diverse query types work correctly."""

    def test_factual_queries_accuracy(self, indexed_collection, embedding_service):
        """All factual queries should find expected documents."""
        factual_queries = [q for q in SMOKE_TEST_QUERIES if q.query_type == "factual"]
        results = [
            run_smoke_query(indexed_collection, embedding_service, q, k=3)
            for q in factual_queries
        ]

        passed = sum(1 for r in results if r.passed)
        assert passed == len(factual_queries), (
            f"Only {passed}/{len(factual_queries)} factual queries passed"
        )

    def test_conceptual_queries_accuracy(self, indexed_collection, embedding_service):
        """All conceptual queries should find expected documents."""
        conceptual_queries = [q for q in SMOKE_TEST_QUERIES if q.query_type == "conceptual"]
        results = [
            run_smoke_query(indexed_collection, embedding_service, q, k=3)
            for q in conceptual_queries
        ]

        passed = sum(1 for r in results if r.passed)
        assert passed == len(conceptual_queries), (
            f"Only {passed}/{len(conceptual_queries)} conceptual queries passed"
        )

    def test_keyword_queries_accuracy(self, indexed_collection, embedding_service):
        """All keyword queries should find expected documents."""
        keyword_queries = [q for q in SMOKE_TEST_QUERIES if q.query_type == "keyword"]
        results = [
            run_smoke_query(indexed_collection, embedding_service, q, k=3)
            for q in keyword_queries
        ]

        passed = sum(1 for r in results if r.passed)
        assert passed == len(keyword_queries), (
            f"Only {passed}/{len(keyword_queries)} keyword queries passed"
        )


class TestDiagnosticInfo:
    """Test that diagnostic information is properly generated."""

    def test_result_contains_top_results(self, indexed_collection, embedding_service):
        """Retrieval result should include top-k results for diagnostics."""
        test_query = SMOKE_TEST_QUERIES[0]
        result = run_smoke_query(indexed_collection, embedding_service, test_query, k=3)

        assert len(result.top_results) == 3
        for r in result.top_results:
            assert "rank" in r
            assert "doc_id" in r
            assert "distance" in r
            assert "snippet" in r

    def test_failure_result_contains_error_message(self, indexed_collection, embedding_service):
        """Failed retrieval should include descriptive error message."""
        # Create a query that will fail (expected doc doesn't exist)
        fake_query = SmokeTestQuery(
            query="Random query text",
            expected_doc_id="non-existent-doc",
            query_type="test",
            description="Test failure diagnostics",
        )

        result = run_smoke_query(indexed_collection, embedding_service, fake_query, k=3)

        assert not result.passed
        assert result.error_message
        assert "non-existent-doc" in result.error_message
        assert result.found_at_rank is None

    def test_result_includes_rank_and_distance(self, indexed_collection, embedding_service):
        """Successful retrieval should include rank and distance of expected doc."""
        test_query = SMOKE_TEST_QUERIES[0]
        result = run_smoke_query(indexed_collection, embedding_service, test_query, k=3)

        if result.passed:
            assert result.found_at_rank is not None
            assert 1 <= result.found_at_rank <= 3
            assert result.distance is not None
            assert result.distance >= 0
