"""Ingestion pipeline package for transforming documents into retrievable chunks."""

from .pipeline import IngestionPipeline, PipelineConfig

__all__ = ["IngestionPipeline", "PipelineConfig"]
