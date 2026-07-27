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


async def init_db():
    from panteon.spinal_craker.models import ObjectType, Object, LinkType, Link, ActionType, ActionExecution, DataPipeline, DataPipelineRun
    from panteon.yono.models import LLMProvider, LLMModel, LLMExecution, Agent, AgentSession, Automation, AutomationExecution, Evaluation, EvaluationRun
    from panteon.core.tenant import Tenant, TenantMetric, TenantWebhook
    from panteon.apollo.models import Environment, ApolloAgent, Service, Deployment, HealthCheck, Pipeline, PipelineRun
    from panteon.core.audit import AuditLog
    from panteon.core.apikeys import APIKey
    from panteon.core.lineage import LineageNode, LineageEdge, LineageEvent
    from panteon.core.workspace import Workspace, WorkspaceMembership
    from panteon.babel.models import Investigation, Finding, Evidence, ThreatEntity, GeoEvent, PatternAlert, TimelineEvent, CountryRiskProfile
    from panteon.contour.models import Dashboard, Chart, PipelineSchedule, PipelineScheduleRun, DataQualityRule, DataQualityViolation, SearchIndex
    from panteon.aip.models import Workflow, WorkflowRun, RagDocument, RagChunk, KnowledgeEntity, KnowledgeRelation, GuardPolicy, GuardEvent, Prompt, PromptVersion, PromptEvaluation
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
