from sqlalchemy import Column, Float, String, DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from panteon.core.config import settings

is_sqlite = settings.database_url.startswith("sqlite")

if is_sqlite:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_routers(db: AsyncSession) -> List[dict]:
    """Get all router status records with enrichment fields."""
    from sqlalchemy import select
    result = await db.execute(select(Router).order_by(Router.callsign.asc()))
    routers = result.scalars().all()
    return [
        {
            "id": r.id,
            "callsign": r.callsign,
            "barangay": r.barangay,
            "municipality": r.municipality,
            "lat": float(r.lat),
            "lng": float(r.lng),
            "model": r.model,
            "firmware": r.firmware,
            "status": r.status,
            "signal_strength": float(r.signal_strength) if r.signal_strength else None,
            "connected_clients": r.connected_clients,
            "last_heartbeat": r.last_heartbeat.isoformat() if r.last_heartbeat else None,
            "error": r.error,
            "vendor_name": r.vendor_name,
            "device_type": r.device_type,
            "city": r.city,
            "country": r.country,
            "latitude": float(r.latitude) if r.latitude else None,
            "longitude": float(r.longitude) if r.longitude else None,
            "last_seen_ip": r.last_seen_ip,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
        }
        for r in routers
    ]


async def get_router(db: AsyncSession, router_id: str) -> Optional[dict]:
    """Get a specific router by ID."""
    from sqlalchemy import select
    result = await db.execute(select(Router).where(Router.id == router_id))
    router = result.scalar_one_or_none()
    if not router:
        return None
    return {
        "id": router.id,
        "callsign": router.callsign,
        "barangay": router.barangay,
        "municipality": router.municipality,
        "lat": float(router.lat),
        "lng": float(router.lng),
        "model": router.model,
        "firmware": router.firmware,
        "status": router.status,
        "signal_strength": float(router.signal_strength) if router.signal_strength else None,
        "connected_clients": router.connected_clients,
        "last_heartbeat": router.last_heartbeat.isoformat() if router.last_heartbeat else None,
        "error": router.error,
        "vendor_name": router.vendor_name,
        "device_type": router.device_type,
        "city": router.city,
        "country": router.country,
        "latitude": float(router.latitude) if router.latitude else None,
        "longitude": float(router.longitude) if router.longitude else None,
        "last_seen_ip": router.last_seen_ip,
        "first_seen": router.first_seen.isoformat() if router.first_seen else None,
    }


async def upsert_router(db: AsyncSession, router_id: str, data: dict):
    """Insert or update a router status record."""
    from sqlalchemy import select, update as sa_update
    
    # Try to find existing
    result = await db.execute(select(Router).where(Router.id == router_id))
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update existing
        await db.execute(
            sa_update(Router)
            .where(Router.id == router_id)
            .values(
                callsign=data.get("callsign", existing.callsign),
                barangay=data.get("barangay", existing.barangay),
                municipality=data.get("municipality", existing.municipality),
                lat=float(data.get("lat", existing.lat)),
                lng=float(data.get("lng", existing.lng)),
                model=data.get("model", existing.model),
                firmware=data.get("firmware", existing.firmware),
                status=data.get("status", existing.status),
                signal_strength=float(data.get("signal_strength", existing.signal_strength)) if data.get("signal_strength") else existing.signal_strength,
                connected_clients=data.get("connected_clients", existing.connected_clients),
                last_heartbeat=data.get("last_heartbeat", existing.last_heartbeat),
                error=data.get("error", existing.error),
                vendor_name=data.get("vendor_name", existing.vendor_name),
                device_type=data.get("device_type", existing.device_type),
                city=data.get("city", existing.city),
                country=data.get("country", existing.country),
                latitude=float(data.get("latitude", existing.latitude)) if data.get("latitude") else existing.latitude,
                longitude=float(data.get("longitude", existing.longitude)) if data.get("longitude") else existing.longitude,
                last_seen_ip=data.get("last_seen_ip", existing.last_seen_ip),
                first_seen=data.get("first_seen", existing.first_seen),
                updated_at=func.now(),
            )
        )
    else:
        # Insert new
        db.add(Router(
            id=router_id,
            callsign=data.get("callsign", router_id),
            barangay=data.get("barangay", ""),
            municipality=data.get("municipality", ""),
            lat=float(data.get("lat", 0)),
            lng=float(data.get("lng", 0)),
            model=data.get("model", "Unknown"),
            firmware=data.get("firmware", "0.0.0"),
            status=data.get("status", "offline"),
            signal_strength=float(data.get("signal_strength")) if data.get("signal_strength") else None,
            connected_clients=data.get("connected_clients", 0),
            last_heartbeat=data.get("last_heartbeat"),
            error=data.get("error"),
            vendor_name=data.get("vendor_name"),
            device_type=data.get("device_type"),
            city=data.get("city"),
            country=data.get("country"),
            latitude=float(data.get("latitude")) if data.get("latitude") else None,
            longitude=float(data.get("longitude")) if data.get("longitude") else None,
            last_seen_ip=data.get("last_seen_ip"),
            first_seen=data.get("first_seen"),
        ))



class Router(Base):
    """Router status model for Pisonet/Maven Smart System integration with enrichment fields."""
    __tablename__ = "routers"
    
    id = Column(String, primary_key=True)
    callsign = Column(String, nullable=False, unique=True)
    barangay = Column(String, nullable=False)
    municipality = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    model = Column(String, nullable=False)
    firmware = Column(String, nullable=False)
    status = Column(String, nullable=False, default="offline")
    signal_strength = Column(Float, nullable=True)  # 0-100 percentage
    connected_clients = Column(Integer, nullable=True, default=0)
    last_heartbeat = Column(Float, nullable=True)  # Unix timestamp
    error = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)  # From OUI lookup
    device_type = Column(String, nullable=True)  # From fingerprint database
    city = Column(String, nullable=True)        # From IP geolocation
    country = Column(String, nullable=True)     # From IP geolocation
    latitude = Column(Float, nullable=True)     # From IP geolocation
    longitude = Column(Float, nullable=True)    # From IP geolocation
    last_seen_ip = Column(String, nullable=True) # Router's current public IP
    first_seen = Column(DateTime, nullable=True) # Deployment date
    created_at = Column(DateTime, nullable=True, default=func.now())
    updated_at = Column(DateTime, nullable=True, default=func.now(), onupdate=func.now())


async def init_db():
    from panteon.spinal_craker.models import ObjectType, Object, LinkType, Link, ActionType, ActionExecution, DataPipeline, DataPipelineRun
    from panteon.yono.models import LLMProvider, LLMModel, LLMExecution, Agent, AgentSession, Automation, AutomationExecution, Evaluation, EvaluationRun
    from panteon.core.tenant import Tenant, TenantMetric, TenantWebhook
    from panteon.statham.models import Environment, StathamAgent, Service, Deployment, HealthCheck, Pipeline, PipelineRun, SmmLink, SmmOrder
    from panteon.core.audit import AuditLog
    from panteon.core.apikeys import APIKey
    from panteon.core.lineage import LineageNode, LineageEdge, LineageEvent
    from panteon.core.workspace import Workspace, WorkspaceMembership
    from panteon.crackerbox.models import Investigation, Finding, Evidence, ThreatEntity, GeoEvent, PatternAlert, TimelineEvent, CountryRiskProfile
    from panteon.contour.models import Dashboard, Chart, PipelineSchedule, PipelineScheduleRun, DataQualityRule, DataQualityViolation, SearchIndex
    from panteon.aip.models import Workflow, WorkflowRun, RagDocument, RagChunk, KnowledgeEntity, KnowledgeRelation, GuardPolicy, GuardEvent, Prompt, PromptVersion, PromptEvaluation
    from panteon.arsenal_store import ArsCategory, ArsItem, ArsSnapshot, ArsOntologyLink
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
