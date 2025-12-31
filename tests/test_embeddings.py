"""Tests for embedding generation functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from indexing.embeddings import (
    DEFAULT_DIMENSIONS,
    DEFAULT_MODEL,
    EmbeddingConfig,
    EmbeddingError,
    EmbeddingService,
    build_embedding_function,
)


class TestBuildEmbeddingFunction:
    """Tests for the build_embedding_function helper."""

    def test_build_default_model(self):
        """Test building embedding function with default model."""
        with patch(
            "indexing.embeddings.embedding_functions.SentenceTransformerEmbeddingFunction"
        ) as mock_fn:
            build_embedding_function(DEFAULT_MODEL)
            mock_fn.assert_called_once_with(model_name=DEFAULT_MODEL)

    def test_build_custom_model(self):
        """Test building embedding function with custom model name."""
        custom_model = "sentence-transformers/paraphrase-MiniLM-L6-v2"
        with patch(
            "indexing.embeddings.embedding_functions.SentenceTransformerEmbeddingFunction"
        ) as mock_fn:
            build_embedding_function(custom_model)
            mock_fn.assert_called_once_with(model_name=custom_model)


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = EmbeddingConfig()
        assert config.model_name == DEFAULT_MODEL
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.retry_backoff == 2.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = EmbeddingConfig(
            model_name="custom-model",
            max_retries=5,
            retry_delay=0.5,
            retry_backoff=1.5,
        )
        assert config.model_name == "custom-model"
        assert config.max_retries == 5
        assert config.retry_delay == 0.5
        assert config.retry_backoff == 1.5


class TestEmbeddingService:
    """Tests for EmbeddingService class."""

    def test_dimensions_property_default_model(self):
        """Test dimensions property returns correct value for default model."""
        service = EmbeddingService()
        assert service.dimensions == DEFAULT_DIMENSIONS
        assert service.dimensions == 384

    def test_dimensions_property_unknown_model(self):
        """Test dimensions property returns default for unknown model."""
        config = EmbeddingConfig(model_name="unknown/model")
        service = EmbeddingService(config)
        assert service.dimensions == DEFAULT_DIMENSIONS

    def test_embed_batch_success(self):
        """Test successful batch embedding generation."""
        service = EmbeddingService()

        mock_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        with patch.object(
            service, "_embedding_fn", return_value=mock_embeddings
        ) as mock_fn:
            service._embedding_fn = mock_fn
            result = service.embed_batch(["text1", "text2"])
            assert result == mock_embeddings
            mock_fn.assert_called_once_with(["text1", "text2"])

    def test_embed_batch_empty_list(self):
        """Test embedding empty list returns empty list."""
        service = EmbeddingService()
        result = service.embed_batch([])
        assert result == []

    def test_embed_batch_retry_on_transient_failure(self):
        """Test retry logic on transient failures."""
        config = EmbeddingConfig(max_retries=3, retry_delay=0.01)
        service = EmbeddingService(config)

        mock_fn = MagicMock()
        mock_fn.side_effect = [
            Exception("Transient error"),
            [[0.1, 0.2, 0.3]],
        ]

        with patch.object(service, "_embedding_fn", mock_fn):
            service._embedding_fn = mock_fn
            result = service.embed_batch(["test"])
            assert result == [[0.1, 0.2, 0.3]]
            assert mock_fn.call_count == 2

    def test_embed_batch_max_retries_exceeded_raises(self):
        """Test EmbeddingError raised after max retries exceeded."""
        config = EmbeddingConfig(max_retries=2, retry_delay=0.01)
        service = EmbeddingService(config)

        mock_fn = MagicMock()
        mock_fn.side_effect = Exception("Persistent error")

        with patch.object(service, "_embedding_fn", mock_fn):
            service._embedding_fn = mock_fn
            with pytest.raises(EmbeddingError) as exc_info:
                service.embed_batch(["test"])

            assert "Failed to generate embeddings after 2 attempts" in str(
                exc_info.value
            )
            assert "Persistent error" in str(exc_info.value)
            assert mock_fn.call_count == 2

    def test_embedding_function_lazy_loading(self):
        """Test embedding function is lazily loaded."""
        service = EmbeddingService()
        assert service._embedding_fn is None
        assert service._model_loaded is False

        with patch(
            "indexing.embeddings.build_embedding_function"
        ) as mock_build:
            mock_build.return_value = MagicMock()
            _ = service.embedding_function
            mock_build.assert_called_once_with(DEFAULT_MODEL)
            assert service._model_loaded is True


class TestEmbeddingError:
    """Tests for EmbeddingError exception."""

    def test_error_message(self):
        """Test EmbeddingError stores message correctly."""
        error = EmbeddingError("Test error message")
        assert str(error) == "Test error message"

    def test_error_chaining(self):
        """Test EmbeddingError can chain from original exception."""
        original = ValueError("Original error")
        error = EmbeddingError("Wrapped error")
        error.__cause__ = original
        assert error.__cause__ is original
