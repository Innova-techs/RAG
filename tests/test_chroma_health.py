"""Unit tests for Chroma health check functionality (Story #11)."""
from __future__ import annotations

from pathlib import Path

import pytest

from indexing.chroma_store import health_check, get_collection, HealthCheckResult


class TestHealthCheck:
    """Tests for Chroma health check."""

    def test_health_check_path_not_exists(self, tmp_path: Path):
        """Test health check returns unhealthy for non-existent path."""
        non_existent = tmp_path / "does_not_exist"

        result = health_check(non_existent)

        assert result.healthy is False
        assert "does not exist" in result.message

    def test_health_check_empty_chroma(self, tmp_path: Path):
        """Test health check succeeds on empty Chroma directory."""
        chroma_path = tmp_path / "chroma"
        chroma_path.mkdir()

        result = health_check(chroma_path)

        assert result.healthy is True
        assert result.collection_count == 0

    def test_health_check_with_collection(self, tmp_path: Path):
        """Test health check returns collection info."""
        chroma_path = tmp_path / "chroma"

        # Create a collection
        collection = get_collection(chroma_path, "test-collection")
        collection.add(
            ids=["doc1"],
            documents=["Test document content"],
        )

        result = health_check(chroma_path, collection_name="test-collection")

        assert result.healthy is True
        assert result.collection_count >= 1
        assert result.document_count == 1
        assert "test-collection" in result.message

    def test_health_check_collection_not_found(self, tmp_path: Path):
        """Test health check returns unhealthy for missing collection."""
        chroma_path = tmp_path / "chroma"
        chroma_path.mkdir()

        result = health_check(chroma_path, collection_name="nonexistent")

        assert result.healthy is False
        assert "not found" in result.message

    def test_health_check_multiple_collections(self, tmp_path: Path):
        """Test health check counts multiple collections."""
        chroma_path = tmp_path / "chroma"

        # Create multiple collections
        get_collection(chroma_path, "collection-1")
        get_collection(chroma_path, "collection-2")
        get_collection(chroma_path, "collection-3")

        result = health_check(chroma_path)

        assert result.healthy is True
        assert result.collection_count == 3


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_healthy_result(self):
        """Test creating a healthy result."""
        result = HealthCheckResult(
            healthy=True,
            message="All good",
            collection_count=5,
            document_count=100,
        )

        assert result.healthy is True
        assert result.message == "All good"
        assert result.collection_count == 5
        assert result.document_count == 100

    def test_unhealthy_result(self):
        """Test creating an unhealthy result."""
        result = HealthCheckResult(
            healthy=False,
            message="Connection failed",
        )

        assert result.healthy is False
        assert result.collection_count == 0
        assert result.document_count == 0
