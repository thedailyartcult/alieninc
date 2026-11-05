"""
Spinal Cracker - Enterprise Data Operating System
Main entry point for the Palantir-style architecture.

This package provides:
- magritte_connector_gdelt: GDELT DOC 2.0 API ingestion sync job
- transform_gdelt_to_ontology: Pure pipeline for raw→structural transformation
- action_writeback_service: High-rigor OSv2 sync engine with ACID guarantees
"""

from .magritte_connector_gdelt import (
    GDELTConnector,
    GDELTConnectorFactory,
    GDELTConfig,
    StagingDataset,
    RawStagingRecord,
    StageRecord,
)
from .transform_gdelt_to_ontology import (
    GDELTTransformEngine,
    OntologyLayer,
    ProcessedRecord,
    PipelineState,
    ObjectType,
    GDELTTransformPipeline,
)
from .action_writeback_service import (
    WritebackService,
    WritebackTransaction,
    WritebackResult,
    ObjectNode,
    GeoCountryNode,
    OntologyGraph,
    GDELTWritebackPipeline,
    OSv2Manager,
)

from .api import app, run_complete_pipeline, writeback_pipeline, osv2, object_storage

__all__ = [
    # magritte_connector_gdelt
    "GDELTConfig",
    "GDELTConnector",
    "GDELTConnectorFactory",
    "StagingDataset",
    "RawStagingRecord",
    "StageRecord",
    # transform_gdelt_to_ontology
    "GDELTTransformEngine",
    "OntologyLayer",
    "ProcessedRecord",
    "PipelineState",
    "ObjectType",
    "GDELTTransformPipeline",
    # action_writeback_service
    "WritebackService",
    "WritebackTransaction",
    "WritebackResult",
    "ObjectNode",
    "GeoCountryNode",
    "OntologyGraph",
    "GDELTWritebackPipeline",
    "OSv2Manager",
]


def get_version() -> str:
    """Return the current Spinal Cracker package version."""
    try:
        import pkgutil
        import importlib.metadata
        return importlib.metadata.version("spinal-cracker") or "0.1.0"
    except Exception:
        return "0.1.0"
