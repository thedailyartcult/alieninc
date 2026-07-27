from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from panteon.core.database import get_db
from panteon.core.hmac_auth import require_spinal_craker_auth, SIGNATURE_HEADER, TIMESTAMP_HEADER
from panteon.core.auth import get_current_user
from panteon.api.schemas_yono_functions import (
    YONOFunctionRequest,
    YONOFunctionResponse,
    YONOFunctionHealthResponse,
)
from panteon.yono.functions import (
    execute_yono_function,
    principal_rate_limiter,
)
from panteon.yono.audit import YONOFunctionAuditLog
from panteon.core.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/yono/functions", tags=["YONO Functions"])

audit_log = YONOFunctionAuditLog()


@router.post(
    "/execute",
    response_model=YONOFunctionResponse,
)
async def execute_function(
    data: YONOFunctionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    if principal_rate_limiter.is_limited(data.principal_id):
        audit_log.log_rejection(
            request_id=data.request_id,
            principal_id=data.principal_id,
            reason="rate_limit_exceeded",
            client_ip=request.client.host if request.client else "unknown",
        )
        remaining = principal_rate_limiter.remaining(data.principal_id)
        logger.warning(
            "yono_function_rate_limited",
            principal_id=data.principal_id,
            request_id=data.request_id,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for principal {data.principal_id}. "
            f"Max {settings.ono_function_rate_limit} requests/hour.",
            headers={
                "X-RateLimit-Limit": str(settings.ono_function_rate_limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Window": "3600",
            },
        )

    audit_log.log_request(
        request_id=data.request_id,
        principal_id=data.principal_id,
        task_prompt=data.task_prompt,
        scoped_context=data.scoped_context,
    )

    logger.info(
        "yono_function_execute",
        request_id=data.request_id,
        principal_id=data.principal_id,
        exec_mode=settings.ono_function_exec_mode,
    )

    result = await execute_yono_function(
        task_prompt=data.task_prompt,
        request_id=data.request_id,
        scoped_context=data.scoped_context,
        db=db,
    )

    audit_log.log_response(
        request_id=data.request_id,
        principal_id=data.principal_id,
        status=result.status,
        output=result.output,
        error=result.error,
        execution_time_ms=result.execution_time_ms,
        model=result.model,
    )

    logger.info(
        "yono_function_completed",
        request_id=data.request_id,
        status=result.status,
        execution_time_ms=result.execution_time_ms,
    )

    return YONOFunctionResponse(
        request_id=result.request_id,
        output=result.output,
        status=result.status,
        error=result.error,
        execution_time_ms=result.execution_time_ms,
        model=result.model,
    )


@router.get("/health", response_model=YONOFunctionHealthResponse)
async def function_health():
    return YONOFunctionHealthResponse(
        status="healthy",
        exec_mode=settings.ono_function_exec_mode,
        model=settings.ono_function_model,
        audit_log_path=str(audit_log.log_path),
    )
