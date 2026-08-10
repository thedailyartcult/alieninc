import asyncio
import uuid
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from panteon.core.database import async_session, init_db
from panteon.statham.models import Environment, StathamAgent, Service, Deployment, HealthCheck, Pipeline, PipelineRun


ENVS = [
    {"name": "prod-cloud-us", "display_name": "Production — US Cloud", "type": "cloud", "desc": "Primary production environment, AWS us-east-1", "config": {"region": "us-east-1", "provider": "aws"}},
    {"name": "prod-cloud-eu", "display_name": "Production — EU Cloud", "type": "cloud", "desc": "EU production, AWS eu-west-1, GDPR-compliant", "config": {"region": "eu-west-1", "provider": "aws", "compliance": "gdpr"}},
    {"name": "staging", "display_name": "Staging", "type": "cloud", "desc": "Pre-production staging environment", "config": {"region": "us-east-1", "provider": "aws"}},
    {"name": "edge-tactical", "display_name": "Tactical Edge", "type": "edge", "desc": "Forward-deployed edge devices, intermittent connectivity", "config": {"connectivity": "intermittent", "classification": "IL5"}},
    {"name": "edge-industrial", "display_name": "Industrial Edge", "type": "edge", "desc": "Factory floor controllers and SCADA systems", "config": {"connectivity": "lan-only", "protocol": "modbus"}},
    {"name": "onprem-hq", "display_name": "HQ On-Premise", "type": "on-prem", "desc": "Corporate headquarters data center", "config": {"location": "Denver, CO", "rack_units": 42}},
    {"name": "airgap-defense", "display_name": "Air-Gapped Defense", "type": "air-gapped", "desc": "Classified network with no external connectivity", "config": {"classification": "IL6", "connectivity": "none"}},
]

SERVICES = [
    {"name": "panteon-api", "display_name": "Panteon API", "desc": "Core platform API server", "lang": "python", "version": "0.14.2"},
    {"name": "spinal-craker-engine", "display_name": "Spinal Craker Engine", "desc": "Ontology engine and query processor", "lang": "python", "version": "0.11.0"},
    {"name": "yono-orchestrator", "display_name": "YONO Orchestrator", "desc": "LLM routing and agent execution engine", "lang": "python", "version": "0.9.3"},
    {"name": "statham-agent", "display_name": "Statham Agent", "desc": "Deployment agent for fleet management", "lang": "go", "version": "2.4.1"},
    {"name": "tdac-bridge", "display_name": "TDAC Bridge", "desc": "The Daily Art Cult integration connector", "lang": "python", "version": "0.3.0"},
    {"name": "admin-ui", "display_name": "Admin Dashboard", "desc": "Platform administration interface", "lang": "typescript", "version": "0.8.1"},
    {"name": "yono-forge", "display_name": "YONO Forge", "desc": "No-code agent builder UI", "lang": "typescript", "version": "0.2.0"},
]


async def seed_statham():
    await init_db()
    async with async_session() as db:
        from panteon.statham.service import StathamService
        svc = StathamService(db)

        env_ids = {}
        for e in ENVS:
            existing = await db.execute(select(Environment).where(Environment.name == e["name"]))
            if not existing.scalar_one_or_none():
                env = await svc.create_environment(
                    name=e["name"], display_name=e["display_name"],
                    env_type=e["type"], description=e["desc"], config=e["config"],
                )
                env_ids[e["name"]] = str(env.id)
            else:
                env_ids[e["name"]] = str(existing.scalar_one().id)
        print(f"Environments: {len(ENVS)}")

        svc_ids = {}
        for s in SERVICES:
            existing = await db.execute(select(Service).where(Service.name == s["name"]))
            if not existing.scalar_one_or_none():
                service = await svc.create_service(
                    name=s["name"], display_name=s["display_name"],
                    description=s["desc"], language=s["lang"],
                )
                service.current_version = s["version"]
                svc_ids[s["name"]] = str(service.id)
            else:
                svc_ids[s["name"]] = str(existing.scalar_one().id)
        print(f"Services: {len(SERVICES)}")

        agent_count = 0
        agent_configs = [
            ("agent-us-east-1a", "prod-cloud-us", "server", "ip-10-0-1-42.ec2.internal"),
            ("agent-us-east-1b", "prod-cloud-us", "server", "ip-10-0-2-88.ec2.internal"),
            ("agent-us-east-1c", "prod-cloud-us", "server", "ip-10-0-3-15.ec2.internal"),
            ("agent-eu-west-1a", "prod-cloud-eu", "server", "ip-10-1-1-22.eu.internal"),
            ("agent-eu-west-1b", "prod-cloud-eu", "server", "ip-10-1-2-67.eu.internal"),
            ("agent-staging-1", "staging", "server", "staging-001.internal"),
            ("agent-staging-2", "staging", "server", "staging-002.internal"),
            ("edge-unit-alpha", "edge-tactical", "edge", "tactical-alpha"),
            ("edge-unit-bravo", "edge-tactical", "edge", "tactical-bravo"),
            ("edge-unit-charlie", "edge-tactical", "edge", "tactical-charlie"),
            ("edge-unit-delta", "edge-tactical", "edge", "tactical-delta"),
            ("plc-line-1", "edge-industrial", "edge", "plc-line-1.factory"),
            ("plc-line-2", "edge-industrial", "edge", "plc-line-2.factory"),
            ("plc-line-3", "edge-industrial", "edge", "plc-line-3.factory"),
            ("gateway-hq", "onprem-hq", "gateway", "hq-gw-01.corp"),
            ("server-hq-1", "onprem-hq", "server", "hq-srv-01.corp"),
            ("server-hq-2", "onprem-hq", "server", "hq-srv-02.corp"),
            ("agent-airgap-1", "airgap-defense", "server", "classified-node-01"),
            ("agent-airgap-2", "airgap-defense", "server", "classified-node-02"),
        ]
        now = datetime.utcnow()
        for name, env_name, atype, hostname in agent_configs:
            existing = await db.execute(select(StathamAgent).where(StathamAgent.name == name))
            if not existing.scalar_one_or_none():
                agent = StathamAgent(
                    name=name, environment_id=env_ids[env_name],
                    agent_type=atype, hostname=hostname,
                    version="2.4.1",
                    status="online" if random.random() > 0.1 else "degraded",
                    last_heartbeat=now - timedelta(minutes=random.randint(0, 5)),
                    agent_info={"os": "ubuntu-22.04" if atype == "server" else "custom-rtos"},
                )
                db.add(agent)
                agent_count += 1
        print(f"Agents: {agent_count}")

        deploy_count = 0
        for svc_name, svc_id in svc_ids.items():
            n_deploys = random.randint(5, 20)
            for i in range(n_deploys):
                env_name = random.choice(list(env_ids.keys()))
                ver = f"0.{random.randint(1, 15)}.{random.randint(0, 20)}"
                days_ago = random.randint(0, 30)
                started = now - timedelta(days=days_ago, hours=random.randint(0, 12))
                status = random.choice(["completed", "completed", "completed", "completed", "rolled_back", "running"])
                existing = await db.execute(
                    select(Deployment).where(
                        Deployment.service_id == svc_id,
                        Deployment.started_at == started,
                    )
                )
                if not existing.scalar_one_or_none():
                    d = Deployment(
                        service_id=svc_id, environment_id=env_ids[env_name],
                        version=ver, status=status,
                        deploy_type=random.choice(["rolling", "blue-green", "canary"]),
                        started_at=started,
                        completed_at=started + timedelta(minutes=random.randint(2, 15)) if status == "completed" else None,
                        triggered_by=random.choice(["ci-pipeline", "admin@panteon", "auto-rollback"]),
                        logs=[
                            {"ts": started.isoformat(), "msg": "Deployment started"},
                            {"ts": (started + timedelta(minutes=1)).isoformat(), "msg": "Health checks passing"},
                            {"ts": (started + timedelta(minutes=random.randint(3, 12))).isoformat(), "msg": "Deployment completed" if status == "completed" else "Rollback triggered"},
                        ],
                    )
                    db.add(d)
                    deploy_count += 1
        print(f"Deployments: {deploy_count}")

        hc_count = 0
        for svc_name, svc_id in svc_ids.items():
            for i in range(30):
                checked = now - timedelta(minutes=i * 5)
                status = "healthy" if random.random() > 0.08 else random.choice(["degraded", "unhealthy"])
                existing = await db.execute(
                    select(HealthCheck).where(
                        HealthCheck.service_id == svc_id,
                        HealthCheck.checked_at == checked,
                    )
                )
                if not existing.scalar_one_or_none():
                    hc = HealthCheck(
                        service_id=svc_id,
                        environment_id=env_ids[random.choice(list(env_ids.keys()))],
                        status=status,
                        latency_ms=random.randint(2, 180) if status == "healthy" else random.randint(200, 5000),
                        response_code=200 if status == "healthy" else random.choice([500, 502, 503]),
                        checked_at=checked,
                    )
                    db.add(hc)
                    hc_count += 1
        print(f"Health Checks: {hc_count}")

        pipelines_data = [
            {"name": "ci-main", "display_name": "CI — Main Branch", "stages": ["lint", "test", "build", "deploy-staging", "smoke-test", "deploy-prod"], "triggers": [{"type": "git_push", "branch": "main"}]},
            {"name": "ci-release", "display_name": "Release Pipeline", "stages": ["build", "integration-test", "security-scan", "stage", "approval-gate", "deploy-prod", "verify"], "triggers": [{"type": "tag", "pattern": "v*"}]},
            {"name": "edge-update", "display_name": "Edge Fleet Update", "stages": ["build-edge", "sign-binary", "stage-to-cdn", "push-to-edge-agents", "verify-heartbeats"], "triggers": [{"type": "manual"}]},
            {"name": "tdac-daily", "display_name": "TDAC Daily Reflection", "stages": ["fetch-patrons", "compose-reflections", "synthesize-audio", "deliver", "notify"], "triggers": [{"type": "cron", "schedule": "0 6 * * *"}]},
            {"name": "db-migration", "display_name": "Database Migration", "stages": ["backup", "migrate", "validate", "notify"], "triggers": [{"type": "manual"}]},
        ]
        pipe_count = 0
        for p in pipelines_data:
            existing = await db.execute(select(Pipeline).where(Pipeline.name == p["name"]))
            if not existing.scalar_one_or_none():
                pipeline = Pipeline(
                    name=p["name"], display_name=p["display_name"],
                    stages=p["stages"], triggers=p["triggers"],
                    is_enabled=True,
                    last_status=random.choice(["success", "success", "failed"]),
                    last_run_at=now - timedelta(hours=random.randint(1, 48)),
                )
                db.add(pipeline)
                await db.flush()
                for i in range(random.randint(3, 10)):
                    run = PipelineRun(
                        pipeline_id=str(pipeline.id),
                        status=random.choice(["success", "success", "success", "failed"]),
                        stages_completed=random.randint(3, len(p["stages"])),
                        stages_total=len(p["stages"]),
                        triggered_by=random.choice(["ci-pipeline", "admin@panteon"]),
                        started_at=now - timedelta(days=random.randint(0, 14), hours=random.randint(0, 23)),
                        completed_at=now - timedelta(days=random.randint(0, 14)),
                    )
                    db.add(run)
                pipe_count += 1
        print(f"Pipelines: {pipe_count}")

        await db.commit()
        print("\n=== STATHAM SEED COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(seed_statham())
