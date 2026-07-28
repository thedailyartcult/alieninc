from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class LLMProviderCreate(BaseModel):
    name: str = Field(..., max_length=100)
    provider_type: str = Field(..., max_length=50)
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class LLMProviderResponse(BaseModel):
    id: UUID
    name: str
    provider_type: str
    base_url: Optional[str]
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LLMModelCreate(BaseModel):
    provider_id: UUID
    model_id: str = Field(..., max_length=200)
    display_name: str = Field(..., max_length=200)
    capabilities: Optional[list] = None
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


class LLMModelResponse(BaseModel):
    id: UUID
    provider_id: UUID
    model_id: str
    display_name: str
    capabilities: list
    max_tokens: int
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LLMExecutionRequest(BaseModel):
    model_id: UUID
    prompt: str
    system_prompt: Optional[str] = None
    parameters: Optional[dict] = None


class LLMExecutionResponse(BaseModel):
    id: UUID
    model_id: UUID
    prompt: str
    system_prompt: Optional[str]
    response: Optional[str]
    tokens_input: int
    tokens_output: int
    latency_ms: Optional[int]
    cost: float
    status: str
    error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    name: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=255)
    system_prompt: str
    model_id: Optional[UUID] = None
    description: Optional[str] = None
    tools: Optional[list] = None
    # ── AIP Governance Fields ─────────────────────────────────────────
    allowed_object_types: Optional[list] = None
    writable_object_types: Optional[list] = None
    allowed_actions: Optional[list] = None
    ontology_context_config: Optional[dict] = None


class AgentResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    description: Optional[str]
    system_prompt: str
    model_id: Optional[UUID]
    tools: list
    is_enabled: bool
    created_at: datetime
    # ── AIP Governance Fields ─────────────────────────────────────────
    allowed_object_types: list
    writable_object_types: list
    allowed_actions: list
    ontology_context_config: dict

    class Config:
        from_attributes = True


class AgentChatRequest(BaseModel):
    agent_id: UUID
    message: str
    session_id: Optional[UUID] = None


class AgentChatResponse(BaseModel):
    session_id: UUID
    response: str
    tokens_input: int
    tokens_output: int
    tool_calls: Optional[list] = None
    iterations: Optional[int] = None


class AutomationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=255)
    trigger_type: str = Field(..., max_length=50)
    trigger_config: dict
    effects: list
    description: Optional[str] = None
    conditions: Optional[list] = None


class AutomationResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    trigger_type: str
    trigger_config: dict
    conditions: list
    effects: list
    is_enabled: bool
    last_triggered_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
