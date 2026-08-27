"""
Spinal Cracker API Endpoints
Integrates the three backend modules (magritte_connector_gdelt, transform_gdelt_to_ontology, action_writeback_service)
into the panteon admin panel's Spinal Cracker feature.

Provides REST endpoints for:
1. GDELT DOC 2.0 ingestion pull
2. Raw → Ontology transformation
3. OSv2 writeback with ACID guarantees
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from magritte_connector_gdelt import (
    GDELTConfig,
    GDELTConnector,
    GDELTConnectorFactory,
    StagingDataset,
    RawStagingRecord,
)
from transform_gdelt_to_ontology import (
    GDELTTransformEngine,
    OntologyLayer,
    GDELTTransformPipeline,
    ObjectType,
)
from action_writeback_service import (
    WritebackService,
    WritebackResult,
    OSv2Manager,
    GDELTWritebackPipeline,
)

from feed_budget import feed_budget

logger = logging.getLogger("spinal_cracker.api")

# Create FastAPI app
app = FastAPI(
    title="Spinal Cracker API",
    description="Enterprise data operating system — GDELT DOC 2.0 integration",
    version="2.0.0",
)


# ---- Startup: initialize OSv2 manager & ontology graph ----

osv2 = OSv2Manager()
object_storage = {}

# Register object types and link types at startup
osv2.register_object_type("gdelt_article", {
    "name": "gdelt_article",
    "display_name": "GDELT Article",
    "description": "GDELt DOC 2.0 article object",
    "fields": ["url", "title", "seendate", "sourcecountry", "domain"],
    "required_fields": ["url"],
    "relationships": ["ARTICLE_PUBLISHED_IN_COUNTRY"],
})
osv2.register_object_type("geo_country", {
    "name": "geo_country",
    "display_name": "Geo Country",
    "description": "Geographic country node",
    "fields": ["country_code", "country_name"],
    "relationships": [],
})
osv2.register_link_type("ARTICLE_PUBLISHED_IN_COUNTRY", {
    "name": "ARTICLE_PUBLISHED_IN_COUNTRY",
    "description": "Link from article to geo_country via sourcecountry",
    "target_type": "geo_country",
})

writeback_pipeline = GDELTWritebackPipeline(
    osv2=osv2,
    object_storage=object_storage,
    ontology_graph=OntologyLayer(),
)


# ---- Helper: run pipeline in event loop ----

async def run_complete_pipeline(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full pipeline: Connect → Transform → Writeback."""
    logger.info("=== Spinal Cracker Pipeline Init ===")

    # --- Phase 1: GDELT Connector ---
    logger.info("Phase 1: GDELT Connector - Initiating pull")
    staging = StagingDataset(path="/tmp/spinal_cracker_staging.jsonl")

    session = await GDELTConnectorFactory.create_session()
    connector = GDELTConnector(
        config=GDELTConfig(**config),
        staging=staging,
    )

    try:
        raw_records, total_count, total_pages = await connector.pull(page=1)
        logger.info(
            f"GDELT pull complete: {total_count} records from {total_pages} pages"
        )

        # Phase 2: Transform Pipeline
        logger.info("Phase 2: Transform Pipeline - Processing raw records")
        ontology = OntologyLayer()
        transform_engine = GDELTTransformEngine(
            object_types=ontology.object_types,
        )

        valid_records, poisoned_records = transform_engine.transform(raw_records)
        logger.info(
            f"Transform complete: {len(valid_records)} valid, "
            f"{len(poisoned_records)} poisoned"
        )

        # Phase 3: Writeback Service
        logger.info("Phase 3: Writeback Service - Writing to OSv2")

        # Convert ProcessedRecord primitives into OSv2 writeback payloads
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

        # Persist raw records to staging dataset
        for record in raw_records:
            staging.append(record)

        # Build final report
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return report

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        raise


# ---- API Endpoints ----

@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint returning API status."""
    return {"status": "Spinal Cracker API is running"}


@app.post("/pipeline/run")
async def run_pipeline(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the full Spinal Cracker pipeline:
    GDELT pull → Transform → Writeback to OSv2.

    Expected config fields:
    - query: str
    - mode: str ("summary" or "doc")
    - timespan: str (e.g., "P1Y")
    - maxrecords: int
    - api_key: str
    - base_url: str (default: https://api.gdeltproject.org/api/gdeltv2)
    - request_timeout: int (default: 30)
    - max_retries: int (default: 5)
    - base_backoff_ms: int (default: 1000)
    - max_backoff_ms: int (default: 60000)
    - jitter_factor: float (default: 0.3)
    """
    try:
        result = await run_complete_pipeline(config)
        return JSONResponse(content=result, status_code=200)
    except Exception as exc:
        logger.exception("Pipeline endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ontology/snapshot")
async def ontology_snapshot() -> Dict[str, Any]:
    """Return a snapshot of the current ontology graph state."""
    snapshot = writeback_pipeline.get_ontology_snapshot()
    return JSONResponse(content=snapshot, status_code=200)


@app.get("/api/v1/feed-budget")
async def feed_budget_endpoint() -> Dict[str, Any]:
    """Return budget status for all registered feeds."""
    feeds = [
        {"name": "opensky", "max_per_day": 10},
        {"name": "gdelt", "max_per_day": 20},
        {"name": "firms", "max_per_day": 50},
        {"name": "vessels", "max_per_day": 10},
    ]
    result = {}
    for f in feeds:
        result[f["name"]] = feed_budget.status(f["name"], f["max_per_day"])
    return result


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ---- Development entry point ----

def main() -> None:
    """CLI entry point for running the API server."""
    import uvicorn

    uvicorn.run("spinal_cracker_api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()