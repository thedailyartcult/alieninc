"""
Spinal Cracker - Main Entry Point
Production-ready pipeline demonstrating all three modules in integration.
"""

import asyncio
import json
import logging
import sys
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from magritte_connector_gdelt import (
    GDELTConfig,
    GDELTConnector,
    GDELTConnectorFactory,
    StagingDataset,
    RawStagingRecord,
    StageRecord,
)
from transform_gdelt_to_ontology import (
    ObjectType,
    OntologyLayer,
    GDELTTransformEngine,
    GDELTTransformPipeline,
)
from action_writeback_service import (
    WritebackService,
    WritebackTransaction,
    WritebackResult,
    ObjectNode,
    GeoCountryNode,
    OntologyGraph,
    GDELTWritebackPipeline,
    OSv2Manager,
)


logger = logging.getLogger("spinal_cracker.main")


async def run_complete_pipeline(
    config: Dict[str, Any],
    test_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Full pipeline: Connect → Transform → Writeback.
    Returns aggregated results.
    """
    logger.info("=== Spinal Cracker Pipeline Init ===")

    # --- Phase 1: GDELT Connector ---
    logger.info("Phase 1: GDELT Connector - Initiating pull")

    staging = StagingDataset(path="/tmp/spinal_cracker_staging.jsonl")

    # Create a session via factory
    session = GDELTConnectorFactory.create_session()
    connector = GDELTConnector(
        config=GDELTConfig(**config),
        staging=staging,
        aiohttp_session=session,
    )

    try:
        raw_records, total_count, total_pages = await connector.pull(page=1)
        logger.info(f"GDELT pull complete: {total_count} records from {total_pages} pages")

        # Phase 2: Transform Pipeline
        logger.info("Phase 2: Transform Pipeline - Processing raw records")
        ontology = OntologyLayer()
        transform_engine = GDELTTransformEngine(
            object_types=ontology.object_types,
        )

        valid_records, poisoned_records = transform_engine.transform(raw_records)
        logger.info(
            f"Transform complete: {len(valid_records)} valid, {len(poisoned_records)} poisoned"
        )

        # Phase 3: Writeback Service
        logger.info("Phase 3: Writeback Service - Writing to OSv2")

        # Initialize OSv2 manager
        osv2 = OSv2Manager()
        # Register object types
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
            "relationships": [],
        })

        # Initialize writeback pipeline
        writeback_pipeline = GDELTWritebackPipeline(
            osv2=osv2,
            object_storage={},
            ontology_graph=ontology,
        )

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

        # Writeback the valid records
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


def main():
    """Standalone entry point for production deployment."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Production config — GDELT DOC 2.0 query parameters.
    # The API is open (no key) and rate-limited to ~1 req / 5s; the connector's
    # jittered backoff honours that. maxrecords is clamped to the 250 cap.
    config = {
        "query": "(\"military\" OR \"defense\" OR \"security\")",
        "mode": "artlist",
        "timespan": "1m",
        "maxrecords": 250,
        "api_key": "",
        "base_url": "https://api.gdeltproject.org/api/v2/doc",
        "request_timeout": 30,
        "max_retries": 5,
        "base_backoff_ms": 5000,
        "max_backoff_ms": 60000,
        "jitter_factor": 0.3,
    }

    # Run the pipeline
    result = asyncio.run(run_complete_pipeline(config))

    logger.info("=== Spinal Cracker Pipeline Complete ===")
    logger.info(f"Result: {json.dumps(result, indent=2, default=str)}")


if __name__ == "__main__":
    main()
