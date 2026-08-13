"""
Module C: Ngram API router for Spinal Cracker / Panteon.

Exposes GDELT Context Ngrams and Web Ngrams analysis as endpoints under
/api/v1/spinal-craker/ngram/. Provides keyword co-occurrence analysis,
trend data, and multi-language translingual search capabilities.

The ngram analysis is useful for:
- Keyword trend analysis over time
- Co-occurrence sentiment analysis
- Web content volume indexing
- Multi-language search aggregation
"""

import logging
import os
import sys
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from panteon.core.auth import get_current_user

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ngram_connector import NgramConnector, NgramConfig, NgramType, NgramResult  # noqa: E402
from panteon.core.database import get_db

logger = logging.getLogger("spinal_cracker.ngram_router")

router = APIRouter(
    prefix="/ngram",
    tags=["Spinal Cracker Ngram"],
)


class NgramQuery(BaseModel):
    """Query parameters for ngram analysis."""
    keyword: str = Field(
        default="military",
        description="Keyword or phrase to analyze ngrams for.",
    )
    ngram_type: str = Field(
        default="context",
        description="Type of ngram analysis: context or web.",
    )
    start_date: str = Field(
        default="",
        description="Start date for analysis YYYYMMDD (optional).",
    )
    end_date: str = Field(
        default="",
        description="End date for analysis YYYYMMDD (optional).",
    )
    timespan: str = Field(
        default="1m",
        description="GDELT timespan (e.g. 1m, 24h, 1h).",
    )
    maxrecords: int = Field(
        default=250,
        ge=1,
        le=250,
        description="Maximum records to return.",
    )
    api_key: str = Field(
        default="",
        description="GDELT API key (empty: open/no-auth).",
    )


@router.get("/health")
async def health_check():
    return {"status": "ok", "source": "panteon spinal-cracker ngram"}


@router.post("/analyze")
async def analyze_ngram(payload: NgramQuery = None):
    """Run ngram analysis and return structured results."""
    config = payload or NgramQuery()
    try:
        # Validate ngram_type
        ngram_type_map = {"context": NgramType.CONTEXT, "web": NgramType.WEB}
        ngram_type = ngram_type_map.get(payload.ngram_type, NgramType.CONTEXT)

        gdconfig = NgramConfig(
            keyword=payload.keyword,
            ngram_type=ngram_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            timespan=payload.timespan,
            maxrecords=payload.maxrecords,
            api_key=payload.api_key,
        )

        connector = NgramConnector(config=gdconfig)
        result = await connector.analyze()

        return JSONResponse(content={
            "keyword": result.keyword,
            "ngram_type": payload.ngram_type,
            "start_date": result.start_date,
            "end_date": result.end_date,
            "timespan": result.timespan,
            "frequency": result.frequency,
            "date_partitioned": result.date_partitioned,
            "correlation_keywords": result.correlation_keywords,
            "confidence": result.confidence,
        }, status_code=200)

    except Exception as exc:
        logger.exception("Ngram analysis failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/trends")
async def get_trends(
    keyword: str = "military",
    timespan: str = "30d",
    start_date: str = "",
    end_date: str = "",
):
    """Quick trends endpoint for dashboard widgets."""
    config = NgramQuery(
        keyword=keyword,
        ngram_type="context",
        start_date=start_date,
        end_date=end_date,
        timespan=timespan,
    )
    try:
        gdconfig = NgramConfig(
            keyword=keyword,
            ngram_type=NgramType.CONTEXT,
            start_date=start_date,
            end_date=end_date,
            timespan=timespan,
        )
        connector = NgramConnector(config=gdconfig)
        result = await connector.analyze()

        return JSONResponse(content={
            "keyword": keyword,
            "frequency": result.frequency,
            "date_partitioned": result.date_partitioned,
            "correlation_keywords": result.correlation_keywords,
        }, status_code=200)

    except Exception as exc:
        logger.exception("Trends endpoint failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
