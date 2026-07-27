import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import structlog

from panteon.core.config import settings

logger = structlog.get_logger()

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 300


@dataclass
class YONOFunctionResult:
    request_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    model: Optional[str] = None


class PrincipalRateLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._principals: dict[str, list[float]] = {}

    def is_limited(self, principal_id: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        if principal_id not in self._principals:
            self._principals[principal_id] = []
        self._principals[principal_id] = [
            t for t in self._principals[principal_id] if t > cutoff
        ]
        if len(self._principals[principal_id]) >= self.max_requests:
            return True
        self._principals[principal_id].append(now)
        return False

    def remaining(self, principal_id: str) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        timestamps = self._principals.get(principal_id, [])
        active = [t for t in timestamps if t > cutoff]
        return max(0, self.max_requests - len(active))

    def cleanup(self) -> None:
        now = time.time()
        cutoff = now - self.window_seconds * 2
        stale = [
            k for k, v in self._principals.items() if all(t < cutoff for t in v)
        ]
        for k in stale:
            del self._principals[k]


principal_rate_limiter = PrincipalRateLimiter(
    max_requests=settings.ono_function_rate_limit,
    window_seconds=3600,
)


def _build_combined_prompt(task_prompt: str, scoped_context: Any = None) -> str:
    parts = []
    if scoped_context is not None:
        if isinstance(scoped_context, dict):
            parts.append("## Context (pre-scoped by Spinal Craker Ontology)\n")
            parts.append(json.dumps(scoped_context, indent=2, ensure_ascii=False))
        else:
            parts.append("## Context (pre-scoped by Spinal Craker Ontology)\n")
            parts.append(str(scoped_context))
        parts.append("\n\n---\n\n")
    parts.append("## Task\n")
    parts.append(task_prompt)
    return "".join(parts)


async def execute_subprocess(
    combined_prompt: str,
    request_id: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> YONOFunctionResult:
    model = settings.ono_function_model or "default"
    cmd = [
        settings.ono_function_executable,
        "run",
        combined_prompt,
        "--model",
        model,
    ]
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("yono_function_timeout", request_id=request_id, timeout_s=timeout)
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            elapsed = int((time.time() - start) * 1000)
            return YONOFunctionResult(
                request_id=request_id,
                status="error",
                error=f"Execution timed out after {timeout}s",
                execution_time_ms=elapsed,
                model=model,
            )
        elapsed = int((time.time() - start) * 1000)
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            return YONOFunctionResult(
                request_id=request_id,
                status="success",
                output=stdout_text,
                execution_time_ms=elapsed,
                model=model,
            )
        else:
            logger.warning(
                "yono_function_subprocess_error",
                request_id=request_id,
                returncode=proc.returncode,
                stderr=stderr_text[:500],
            )
            return YONOFunctionResult(
                request_id=request_id,
                status="error",
                error=f"Process exited with code {proc.returncode}: {stderr_text[:1000]}",
                execution_time_ms=elapsed,
                model=model,
            )
    except FileNotFoundError:
        elapsed = int((time.time() - start) * 1000)
        logger.error("yono_function_executable_not_found", path=settings.ono_function_executable)
        return YONOFunctionResult(
            request_id=request_id,
            status="error",
            error=f"Executable not found: {settings.ono_function_executable}",
            execution_time_ms=elapsed,
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        logger.error("yono_function_unexpected_error", request_id=request_id, error=str(e))
        return YONOFunctionResult(
            request_id=request_id,
            status="error",
            error=f"Unexpected error: {str(e)[:500]}",
            execution_time_ms=elapsed,
        )


async def execute_native(
    combined_prompt: str,
    request_id: str,
    db: Any,
) -> YONOFunctionResult:
    start = time.time()
    try:
        from panteon.yono.service import LLMOrchestrator
        orchestrator = LLMOrchestrator(db)
        models = await orchestrator.list_models()
        if not models:
            return YONOFunctionResult(
                request_id=request_id,
                status="error",
                error="No LLM models configured in YONO",
                execution_time_ms=int((time.time() - start) * 1000),
            )
        model = models[0]
        execution = await orchestrator.execute_llm(
            model_id=model.id,
            prompt=combined_prompt,
            system_prompt=(
                "You are an AI assistant executing tasks within the Panteon platform. "
                "The context provided has been pre-scoped by the Spinal Craker Ontology. "
                "Respond directly to the task without requesting additional permissions or data."
            ),
        )
        elapsed = int((time.time() - start) * 1000)
        if execution.status == "success":
            return YONOFunctionResult(
                request_id=request_id,
                status="success",
                output=execution.response,
                execution_time_ms=elapsed,
                model=model.display_name,
            )
        else:
            return YONOFunctionResult(
                request_id=request_id,
                status="error",
                error=execution.error or "LLM execution failed",
                execution_time_ms=elapsed,
                model=model.display_name,
            )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        logger.error("yono_function_native_error", request_id=request_id, error=str(e))
        return YONOFunctionResult(
            request_id=request_id,
            status="error",
            error=f"Native YONO execution error: {str(e)[:500]}",
            execution_time_ms=elapsed,
        )


async def execute_yono_function(
    task_prompt: str,
    request_id: str,
    scoped_context: Any = None,
    db: Any = None,
) -> YONOFunctionResult:
    combined_prompt = _build_combined_prompt(task_prompt, scoped_context)
    mode = settings.ono_function_exec_mode
    if mode == "native" and db is not None:
        return await execute_native(combined_prompt, request_id, db)
    else:
        return await execute_subprocess(
            combined_prompt,
            request_id,
            timeout=min(settings.ono_function_timeout, MAX_TIMEOUT),
        )
