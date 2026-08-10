import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.statham.models import (
    Environment, StathamAgent, Service, Deployment, HealthCheck, Pipeline, PipelineRun
)
from panteon.core.database import is_sqlite


def _uid(val):
    if is_sqlite and val is not None:
        return str(val)
    return val


class StathamService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_environment(
        self, name: str, display_name: str, env_type: str,
        description: Optional[str] = None, config: Optional[dict] = None,
    ) -> Environment:
        env = Environment(
            name=name, display_name=display_name, env_type=env_type,
            description=description, config=config or {},
        )
        self.db.add(env)
        await self.db.flush()
        return env

    async def list_environments(self) -> list[Environment]:
        result = await self.db.execute(select(Environment).order_by(Environment.name))
        return list(result.scalars().all())

    async def get_environment(self, env_id: str) -> Optional[Environment]:
        result = await self.db.execute(
            select(Environment).where(Environment.id == _uid(env_id))
        )
        return result.scalar_one_or_none()

    async def create_service(
        self, name: str, display_name: str,
        description: Optional[str] = None, repo_url: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Service:
        svc = Service(
            name=name, display_name=display_name,
            description=description, repo_url=repo_url, language=language,
        )
        self.db.add(svc)
        await self.db.flush()
        return svc

    async def list_services(self) -> list[Service]:
        result = await self.db.execute(select(Service).order_by(Service.name))
        return list(result.scalars().all())

    async def get_service(self, service_id: str) -> Optional[Service]:
        result = await self.db.execute(
            select(Service).where(Service.id == _uid(service_id))
        )
        return result.scalar_one_or_none()

    async def deploy(
        self, service_id: str, environment_id: str, version: str,
        deploy_type: str = "rolling", triggered_by: Optional[str] = None,
    ) -> Deployment:
        deployment = Deployment(
            service_id=_uid(service_id),
            environment_id=_uid(environment_id),
            version=version, deploy_type=deploy_type,
            triggered_by=triggered_by, status="running",
        )
        self.db.add(deployment)
        await self.db.flush()
        return deployment

    async def list_deployments(
        self, service_id: Optional[str] = None, environment_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Deployment]:
        query = select(Deployment).options(
            selectinload(Deployment.service),
            selectinload(Deployment.environment),
        )
        if service_id:
            query = query.where(Deployment.service_id == _uid(service_id))
        if environment_id:
            query = query.where(Deployment.environment_id == _uid(environment_id))
        query = query.order_by(Deployment.started_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def register_agent(
        self, name: str, environment_id: str, agent_type: str,
        hostname: Optional[str] = None, version: Optional[str] = None,
    ) -> StathamAgent:
        agent = StathamAgent(
            name=name, environment_id=_uid(environment_id),
            agent_type=agent_type, hostname=hostname, version=version,
            last_heartbeat=datetime.utcnow(),
        )
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def list_agents(self, environment_id: Optional[str] = None) -> list[StathamAgent]:
        query = select(StathamAgent).options(selectinload(StathamAgent.environment))
        if environment_id:
            query = query.where(StathamAgent.environment_id == _uid(environment_id))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def heartbeat(self, agent_id: str) -> Optional[StathamAgent]:
        result = await self.db.execute(
            select(StathamAgent).where(StathamAgent.id == _uid(agent_id))
        )
        agent = result.scalar_one_or_none()
        if agent:
            agent.last_heartbeat = datetime.utcnow()
            agent.status = "online"
            await self.db.flush()
        return agent

    async def record_health_check(
        self, service_id: str, status: str,
        latency_ms: Optional[int] = None, response_code: Optional[int] = None,
        environment_id: Optional[str] = None, details: Optional[dict] = None,
    ) -> HealthCheck:
        hc = HealthCheck(
            service_id=_uid(service_id),
            environment_id=_uid(environment_id) if environment_id else None,
            status=status, latency_ms=latency_ms,
            response_code=response_code, details=details or {},
        )
        self.db.add(hc)
        await self.db.flush()
        return hc

    async def get_service_health(self, service_id: str, limit: int = 20) -> list[HealthCheck]:
        result = await self.db.execute(
            select(HealthCheck)
            .where(HealthCheck.service_id == _uid(service_id))
            .order_by(HealthCheck.checked_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_pipeline(
        self, name: str, display_name: str,
        service_id: Optional[str] = None,
        stages: Optional[list] = None, triggers: Optional[list] = None,
        description: Optional[str] = None,
    ) -> Pipeline:
        pipeline = Pipeline(
            name=name, display_name=display_name,
            service_id=_uid(service_id) if service_id else None,
            stages=stages or [], triggers=triggers or [],
            description=description,
        )
        self.db.add(pipeline)
        await self.db.flush()
        return pipeline

    async def list_pipelines(self) -> list[Pipeline]:
        result = await self.db.execute(
            select(Pipeline).options(selectinload(Pipeline.runs)).order_by(Pipeline.name)
        )
        return list(result.scalars().all())

    async def trigger_pipeline(
        self, pipeline_id: str, triggered_by: Optional[str] = None,
    ) -> PipelineRun:
        result = await self.db.execute(
            select(Pipeline).where(Pipeline.id == _uid(pipeline_id))
        )
        pipeline = result.scalar_one_or_none()
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        run = PipelineRun(
            pipeline_id=_uid(pipeline_id),
            stages_total=len(pipeline.stages),
            triggered_by=triggered_by, status="running",
        )
        self.db.add(run)
        pipeline.last_run_at = run.started_at
        pipeline.last_status = "running"
        await self.db.flush()
        return run

    async def get_fleet_status(self) -> dict:
        envs = await self.list_environments()
        agents = await self.list_agents()
        services = await self.list_services()

        online = sum(1 for a in agents if a.status == "online")
        deployments = await self.list_deployments(limit=100)
        active_deploys = sum(1 for d in deployments if d.status == "running")
        healthy_services = 0
        for svc in services:
            checks = await self.get_service_health(svc.id, limit=1)
            if checks and checks[0].status == "healthy":
                healthy_services += 1

        return {
            "environments": len(envs),
            "agents_total": len(agents),
            "agents_online": online,
            "services_total": len(services),
            "services_healthy": healthy_services,
            "active_deployments": active_deploys,
            "total_deployments": len(deployments),
        }
