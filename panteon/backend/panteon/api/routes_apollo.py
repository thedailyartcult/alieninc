import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.core.database import get_db
from panteon.apollo.service import ApolloService
from panteon.api.schemas_apollo import (
    EnvironmentCreate, EnvironmentResponse,
    ServiceCreate, ServiceResponse,
    DeployRequest, DeploymentResponse,
    AgentRegisterRequest, AgentResponse,
    HealthCheckRequest,
    PipelineCreate, PipelineResponse,
    FleetStatusResponse,
)

router = APIRouter(prefix="/apollo", tags=["Apollo"])


@router.get("/fleet-status", response_model=FleetStatusResponse)
async def get_fleet_status(db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.get_fleet_status()


@router.post("/environments", response_model=EnvironmentResponse)
async def create_environment(data: EnvironmentCreate, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.create_environment(
        name=data.name, display_name=data.display_name,
        env_type=data.env_type, description=data.description, config=data.config,
    )


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.list_environments()


@router.post("/services", response_model=ServiceResponse)
async def create_service(data: ServiceCreate, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.create_service(
        name=data.name, display_name=data.display_name,
        description=data.description, repo_url=data.repo_url, language=data.language,
    )


@router.get("/services", response_model=list[ServiceResponse])
async def list_services(db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.list_services()


@router.post("/deploy", response_model=DeploymentResponse)
async def deploy(data: DeployRequest, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    try:
        return await service.deploy(
            service_id=data.service_id, environment_id=data.environment_id,
            version=data.version, deploy_type=data.deploy_type, triggered_by=data.triggered_by,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/deployments", response_model=list[DeploymentResponse])
async def list_deployments(
    service_id: Optional[str] = None,
    environment_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    service = ApolloService(db)
    return await service.list_deployments(service_id, environment_id, limit)


@router.post("/agents", response_model=AgentResponse)
async def register_agent(data: AgentRegisterRequest, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.register_agent(
        name=data.name, environment_id=data.environment_id,
        agent_type=data.agent_type, hostname=data.hostname, version=data.version,
    )


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    environment_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    service = ApolloService(db)
    return await service.list_agents(environment_id)


@router.post("/agents/{agent_id}/heartbeat", response_model=AgentResponse)
async def agent_heartbeat(agent_id: str, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    agent = await service.heartbeat(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/health-checks")
async def record_health_check(data: HealthCheckRequest, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    hc = await service.record_health_check(
        service_id=data.service_id, status=data.status,
        latency_ms=data.latency_ms, response_code=data.response_code,
        environment_id=data.environment_id, details=data.details,
    )
    return {"id": str(hc.id), "status": hc.status}


@router.get("/services/{service_id}/health")
async def get_service_health(
    service_id: str, limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = ApolloService(db)
    checks = await service.get_service_health(service_id, limit)
    return [{"status": c.status, "latency_ms": c.latency_ms, "checked_at": c.checked_at.isoformat()} for c in checks]


@router.post("/pipelines", response_model=PipelineResponse)
async def create_pipeline(data: PipelineCreate, db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.create_pipeline(
        name=data.name, display_name=data.display_name,
        service_id=data.service_id, stages=data.stages,
        triggers=data.triggers, description=data.description,
    )


@router.get("/pipelines", response_model=list[PipelineResponse])
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    service = ApolloService(db)
    return await service.list_pipelines()


@router.post("/pipelines/{pipeline_id}/trigger")
async def trigger_pipeline(
    pipeline_id: str, triggered_by: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    service = ApolloService(db)
    try:
        run = await service.trigger_pipeline(pipeline_id, triggered_by)
        return {"run_id": str(run.id), "status": run.status, "stages_total": run.stages_total}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
