"""
GDELT pipeline router for the Spinal Cracker / Panteon admin panel.

Exposes the GDELT DOC 2.0 pull -> transform -> OSv2 writeback pipeline as
endpoints under `/api/v1/spinal-cracker/gdelt/...`. These reuse the three
core modules (magritte_connector_gdelt, transform_gdelt_to_ontology,
action_writeback_service) and share the same auth as the rest of the
spinal-cracker router.

The pipeline is intentionally lightweight and runs in-process (the OSv2
manager / ontology graph are module-level singletons so snapshots persist
across requests in the same process).
"""

import logging
import os
import sys
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from panteon.core.auth import get_current_user

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from magritte_connector_gdelt import GDELTConfig, GDELTConnector, GDELTConnectorFactory, StagingDataset  # noqa: E402
from transform_gdelt_to_ontology import (  # noqa: E402
    GDELTTransformEngine,
    OntologyLayer,
    GDELTTransformPipeline,
)
from action_writeback_service import (  # noqa: E402
    OSv2Manager,
    GDELTWritebackPipeline,
    OntologyGraph,
)

logger = logging.getLogger("spinal_cracker.gdelt_router")

router = APIRouter(
    prefix="/spinal-cracker/gdelt",
    tags=["Spinal Cracker GDELT"],
)


class PipelineConfig(BaseModel):
    """User-overridable GDELT DOC 2.0 query parameters."""
    query: str = Field(
        default='("military" OR "defense" OR "security")',
        description="GDELT DOC 2.0 query string.",
    )
    mode: str = Field(default="artlist", description="DOC 2.0 mode (eg artlist).")
    timespan: str = Field(default="1m", description="GDELT timespan (eg 24h, 1m).")
    maxrecords: int = Field(default=250, ge=1, le=250)
    api_key: str = Field(default="", description="GDELT API key (empty: open/no-auth).")


def _build_pipeline() -> tuple[OSv2Manager, OntologyLayer, GDELTWritebackPipeline]:
    """Initialise the in-memory OSv2 store + ontology graph (module-level singletons)."""
    osv2 = getattr(_build_pipeline, "_osv2", None)
    if osv2 is None:
        osv2 = OSv2Manager()
        osv2.register_object_type("gdelt_article", {
            "name": "gdelt_article",
            "display_name": "GDELT Article",
            "description": "GDELT DOC 2.0 article object",
            "fields": ["url", "title", "seendate", "sourcecountry", "domain"],
            "required_fields": ["url"],
            "relationships": ["ARTICLE_PUBLISHED_IN_COUNTRY"],
        })
        osv2.register_object_type("geo_country", {
            "name": "geo_country",
            "display_name": "Geo Country",
            "description": "Geographic country node",
            "fields": ["country_code", "country_name"],
            "required_fields": ["country_code"],
            "relationships": [],
        })
        _build_pipeline._osv2 = osv2  # noqa: SLF001

    ontology = getattr(_build_pipeline, "_ontology", None)
    if ontology is None:
        ontology = OntologyLayer()
        _build_pipeline._ontology = ontology  # noqa: SLF001

    pipeline = GDELTWritebackPipeline(osv2=osv2, object_storage={}, ontology_graph=ontology)
    return osv2, ontology, pipeline


async def _run_pipeline(config: PipelineConfig) -> dict:
    """Execute pull -> transform -> writeback and return the report dict."""
    osv2, ontology, writeback_pipeline = _build_pipeline()

    gdconfig = GDELTConfig(
        query=config.query,
        mode=config.mode,
        timespan=config.timespan,
        maxrecords=config.maxrecords,
        api_key=config.api_key,
    )
    staging = StagingDataset(path="/tmp/spinal_cracker_staging.jsonl")

    session = await GDELTConnectorFactory.create_session()
    connector = GDELTConnector(config=gdconfig, staging=staging, aiohttp_session=session)

    report: dict = {"phase": "pending"}
    try:
        raw_records, total_count, total_pages = await connector.pull(page=1)

        ontology_layer = OntologyLayer()
        transform_engine = GDELTTransformEngine(object_types=ontology_layer.object_types)
        valid_records, poisoned_records = transform_engine.transform(raw_records)

        writeback_records = [
            {
                "url": r.url,
                "title": r.title,
                "seendate": r.seendate,
                "sourcecountry": r.sourcecountry,
                "domain": r.domain,
                "properties": r.payload,
                "type": "gdelt_article",
            }
            for r in valid_records
        ]

        result = await writeback_pipeline._writeback_batch(writeback_records, {})

        for record in raw_records:
            staging.append(record)

        report = {
            "phase": "complete",
            "gdelt": {
                "total_records": total_count,
                "pages": total_pages,
                "records_fetched": len(raw_records),
            },
            "transform": {
                "valid_count": len(valid_records),
                "poisoned_count": len(poisoned_records),
            },
            "writeback": {
                "success_count": result.success_count,
                "failure_count": result.failure_count,
                "transaction_id": result.transaction_id,
            },
            "ontology": {
                "object_type_count": len(ontology.object_types),
                "link_type_count": len(ontology.link_types),
            },
        }
        logger.info("GDELT pipeline run complete: %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed: %s", exc)
        report = {"phase": "failed", "error": str(exc)}
    finally:
        await GDELTConnectorFactory.reset_session()

    return report


@router.get("/health")
async def health_check():
    return {"status": "ok", "source": "panteon spinal-cracker gdelt"}


@router.post("/pipeline/run")
async def run_pipeline(payload: PipelineConfig = None, _bg: BackgroundTasks = None):
    """Run the GDELT DOC 2.0 -> transform -> writeback pipeline."""
    config = payload or PipelineConfig()
    report = await _run_pipeline(config)
    if report.get("phase") == "failed":
        raise HTTPException(status_code=502, detail=report.get("error", "pipeline failed"))
    return JSONResponse(content=report, status_code=200)


@router.get("/ontology/snapshot")
async def ontology_snapshot():
    _, _, pipeline = _build_pipeline()
    return JSONResponse(content=pipeline.get_ontology_snapshot(), status_code=200)


@router.get("/objects")
async def list_objects(limit: int = 100):
    osv2, _, _ = _build_pipeline()
    objs = osv2.get_all_objects()
    return JSONResponse(content={"objects": objs[-limit:], "count": len(objs)}, status_code=200)
