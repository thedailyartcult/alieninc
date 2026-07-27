import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import structlog

from panteon.core.config import settings

logger = structlog.get_logger()


class ONOFunctionAuditLog:
    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = Path(log_dir or settings.ono_function_audit_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "ono-functions-audit.jsonl"

    def log_request(
        self,
        request_id: str,
        principal_id: str,
        task_prompt: str,
        scoped_context: Any = None,
    ) -> None:
        entry = {
            "event": "function_request",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "principal_id": principal_id,
            "task_prompt_length": len(task_prompt),
            "has_scoped_context": scoped_context is not None,
        }
        self._append(entry)

    def log_response(
        self,
        request_id: str,
        principal_id: str,
        status: str,
        output: Optional[str] = None,
        error: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        model: Optional[str] = None,
    ) -> None:
        entry = {
            "event": "function_response",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "principal_id": principal_id,
            "status": status,
            "execution_time_ms": execution_time_ms,
            "model": model,
            "output_length": len(output) if output else 0,
        }
        if error:
            entry["error"] = error[:500]
        self._append(entry)

    def log_rejection(
        self,
        request_id: Optional[str],
        principal_id: Optional[str],
        reason: str,
        client_ip: Optional[str] = None,
    ) -> None:
        entry = {
            "event": "function_rejected",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "principal_id": principal_id,
            "reason": reason,
            "client_ip": client_ip,
        }
        self._append(entry)

    def _append(self, entry: dict) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("ono_function_audit_write_failed", error=str(e), path=str(self.log_path))
