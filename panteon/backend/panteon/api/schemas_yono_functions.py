from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class YONOFunctionRequest(BaseModel):
    task_prompt: str = Field(..., min_length=1, max_length=50000)
    scoped_context: Optional[Union[str, dict[str, Any]]] = None
    principal_id: str = Field(..., min_length=1, max_length=255)
    request_id: str = Field(..., min_length=1, max_length=255)


class YONOFunctionResponse(BaseModel):
    request_id: str
    output: Optional[str] = None
    status: str
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    model: Optional[str] = None

    class Config:
        from_attributes = True


class YONOFunctionHealthResponse(BaseModel):
    status: str
    exec_mode: str
    model: Optional[str] = None
    audit_log_path: Optional[str] = None
