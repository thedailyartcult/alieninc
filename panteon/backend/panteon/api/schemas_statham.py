from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class EnvironmentCreate(BaseModel):
    name: str
    display_name: str
    env_type: str = Field(..., pattern="^(cloud|edge|on-prem|air-gapped|hybrid)$")
    description: Optional[str] = None
    config: Optional[dict] = None


class EnvironmentResponse(BaseModel):
    id: str
    name: str
    display_name: str
    env_type: str
    description: Optional[str]
    config: dict
    status: str
    created_at: datetime
    class Config:
        from_attributes = True


class ServiceCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    repo_url: Optional[str] = None
    language: Optional[str] = None


class ServiceResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    repo_url: Optional[str]
    language: Optional[str]
    current_version: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


class DeployRequest(BaseModel):
    service_id: str
    environment_id: str
    version: str
    deploy_type: str = "rolling"
    triggered_by: Optional[str] = None


class DeploymentResponse(BaseModel):
    id: str
    service_id: str
    environment_id: str
    version: str
    status: str
    deploy_type: str
    started_at: datetime
    completed_at: Optional[datetime]
    triggered_by: Optional[str]
    class Config:
        from_attributes = True


class AgentRegisterRequest(BaseModel):
    name: str
    environment_id: str
    agent_type: str = Field(..., pattern="^(server|edge|gateway)$")
    hostname: Optional[str] = None
    version: Optional[str] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    environment_id: str
    agent_type: str
    hostname: Optional[str]
    version: Optional[str]
    status: str
    last_heartbeat: Optional[datetime]
    class Config:
        from_attributes = True


class HealthCheckRequest(BaseModel):
    service_id: str
    status: str
    latency_ms: Optional[int] = None
    response_code: Optional[int] = None
    environment_id: Optional[str] = None
    details: Optional[dict] = None


class PipelineCreate(BaseModel):
    name: str
    display_name: str
    service_id: Optional[str] = None
    stages: Optional[list] = None
    triggers: Optional[list] = None
    description: Optional[str] = None


class PipelineResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    stages: list
    triggers: list
    is_enabled: bool
    last_run_at: Optional[datetime]
    last_status: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


class FleetStatusResponse(BaseModel):
    environments: int
    agents_total: int
    agents_online: int
    services_total: int
    services_healthy: int
    active_deployments: int
    total_deployments: int
