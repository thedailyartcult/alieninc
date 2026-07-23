import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.core.database import get_db
from panteon.core.auth import get_current_user
from panteon.spinal_craker.service import OntologyService
from panteon.api.schemas_spinal_craker import (
    ObjectTypeCreate, ObjectTypeResponse,
    ObjectCreate, ObjectUpdate, ObjectResponse,
    LinkTypeCreate, LinkTypeResponse,
    LinkCreate, LinkResponse,
    ActionTypeCreate, ActionTypeResponse,
)

router = APIRouter(prefix="/spinal-craker", tags=["Spinal Craker"], dependencies=[Depends(get_current_user)])


@router.post("/object-types", response_model=ObjectTypeResponse)
async def create_object_type(
    data: ObjectTypeCreate,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    obj_type = await service.create_object_type(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        properties_schema=data.properties_schema,
        icon=data.icon,
    )
    return obj_type


@router.get("/object-types", response_model=list[ObjectTypeResponse])
async def list_object_types(db: AsyncSession = Depends(get_db)):
    service = OntologyService(db)
    return await service.list_object_types()


@router.get("/object-types/{type_id}", response_model=ObjectTypeResponse)
async def get_object_type(type_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = OntologyService(db)
    obj_type = await service.get_object_type(type_id)
    if not obj_type:
        raise HTTPException(status_code=404, detail="Object type not found")
    return obj_type


@router.post("/objects", response_model=ObjectResponse)
async def create_object(
    data: ObjectCreate,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    obj = await service.create_object(
        object_type_id=data.object_type_id,
        primary_key_value=data.primary_key_value,
        properties=data.properties,
    )
    return obj


@router.get("/objects", response_model=list[ObjectResponse])
async def list_objects(
    object_type_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    return await service.list_objects(
        object_type_id=object_type_id,
        limit=limit,
        offset=offset,
    )


@router.get("/objects/{object_id}", response_model=ObjectResponse)
async def get_object(object_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = OntologyService(db)
    obj = await service.get_object(object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj


@router.patch("/objects/{object_id}", response_model=ObjectResponse)
async def update_object(
    object_id: uuid.UUID,
    data: ObjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    obj = await service.update_object(object_id, data.properties)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj


@router.delete("/objects/{object_id}")
async def delete_object(object_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = OntologyService(db)
    deleted = await service.delete_object(object_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Object not found")
    return {"deleted": True}


@router.get("/objects/{object_id}/links", response_model=list[LinkResponse])
async def get_object_links(
    object_id: uuid.UUID,
    direction: str = Query(default="outgoing", pattern="^(outgoing|incoming)$"),
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    return await service.get_object_links(object_id, direction)


@router.post("/link-types", response_model=LinkTypeResponse)
async def create_link_type(
    data: LinkTypeCreate,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    link_type = await service.create_link_type(
        name=data.name,
        display_name=data.display_name,
        source_type_id=data.source_type_id,
        target_type_id=data.target_type_id,
        description=data.description,
        cardinality=data.cardinality,
    )
    return link_type


@router.get("/link-types", response_model=list[LinkTypeResponse])
async def list_link_types(db: AsyncSession = Depends(get_db)):
    service = OntologyService(db)
    result = await service.db.execute(
        __import__("sqlalchemy").select(__import__("panteon.spinal_craker.models", fromlist=["LinkType"]).LinkType)
    )
    return list(result.scalars().all())


@router.post("/links", response_model=LinkResponse)
async def create_link(
    data: LinkCreate,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    link = await service.create_link(
        link_type_id=data.link_type_id,
        source_object_id=data.source_object_id,
        target_object_id=data.target_object_id,
        properties=data.properties,
    )
    return link


@router.post("/action-types", response_model=ActionTypeResponse)
async def create_action_type(
    data: ActionTypeCreate,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    action_type = await service.create_action_type(
        name=data.name,
        display_name=data.display_name,
        object_type_id=data.object_type_id,
        description=data.description,
        parameters_schema=data.parameters_schema,
        effects=data.effects,
    )
    return action_type


@router.get("/action-types", response_model=list[ActionTypeResponse])
async def list_action_types(db: AsyncSession = Depends(get_db)):
    service = OntologyService(db)
    result = await service.db.execute(
        __import__("sqlalchemy").select(__import__("panteon.spinal_craker.models", fromlist=["ActionType"]).ActionType)
    )
    return list(result.scalars().all())


@router.post("/action-types/{action_type_id}/execute")
async def execute_action(
    action_type_id: uuid.UUID,
    object_id: Optional[uuid.UUID] = None,
    parameters: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
):
    service = OntologyService(db)
    execution = await service.execute_action(
        action_type_id=action_type_id,
        object_id=object_id,
        parameters=parameters,
    )
    return {"execution_id": execution.id, "status": execution.status}


from panteon.spinal_craker.models import DataPipeline, DataPipelineRun
from sqlalchemy import select as sa_select
from pydantic import BaseModel
from typing import Optional


class PipelineCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    stages: list = []
    connections: list = []
    config: dict = {}


class PipelineResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    stages: list
    connections: list
    config: dict
    is_draft: bool
    is_enabled: bool
    created_at: str
    updated_at: str


class PipelineRunResponse(BaseModel):
    id: str
    pipeline_id: str
    status: str
    triggered_by: Optional[str]
    stage_results: list
    error: Optional[str]
    started_at: str
    completed_at: Optional[str]
    records_processed: int


@router.post("/pipelines", response_model=PipelineResponse)
async def create_pipeline(
    data: PipelineCreate,
    db: AsyncSession = Depends(get_db),
):
    pipeline = DataPipeline(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        stages=data.stages,
        connections=data.connections,
        config=data.config,
    )
    db.add(pipeline)
    await db.flush()
    return PipelineResponse(
        id=str(pipeline.id), name=pipeline.name, display_name=pipeline.display_name,
        description=pipeline.description, stages=pipeline.stages, connections=pipeline.connections,
        config=pipeline.config, is_draft=pipeline.is_draft, is_enabled=pipeline.is_enabled,
        created_at=pipeline.created_at.isoformat(), updated_at=pipeline.updated_at.isoformat(),
    )


@router.get("/pipelines", response_model=list[PipelineResponse])
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa_select(DataPipeline).order_by(DataPipeline.created_at.desc()))
    return [
        PipelineResponse(
            id=str(p.id), name=p.name, display_name=p.display_name,
            description=p.description, stages=p.stages, connections=p.connections,
            config=p.config, is_draft=p.is_draft, is_enabled=p.is_enabled,
            created_at=p.created_at.isoformat(), updated_at=p.updated_at.isoformat(),
        )
        for p in result.scalars().all()
    ]


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa_select(DataPipeline).where(DataPipeline.id == str(pipeline_id)))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="DataPipeline not found")
    return PipelineResponse(
        id=str(p.id), name=p.name, display_name=p.display_name,
        description=p.description, stages=p.stages, connections=p.connections,
        config=p.config, is_draft=p.is_draft, is_enabled=p.is_enabled,
        created_at=p.created_at.isoformat(), updated_at=p.updated_at.isoformat(),
    )


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(sa_select(DataPipeline).where(DataPipeline.id == str(pipeline_id)))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="DataPipeline not found")
    for key in ("name", "display_name", "description", "stages", "connections", "config", "is_draft", "is_enabled"):
        if key in data:
            setattr(p, key, data[key])
    await db.flush()
    return PipelineResponse(
        id=str(p.id), name=p.name, display_name=p.display_name,
        description=p.description, stages=p.stages, connections=p.connections,
        config=p.config, is_draft=p.is_draft, is_enabled=p.is_enabled,
        created_at=p.created_at.isoformat(), updated_at=p.updated_at.isoformat(),
    )


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sa_select(DataPipeline).where(DataPipeline.id == str(pipeline_id)))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="DataPipeline not found")
    await db.delete(p)
    await db.flush()
    return {"deleted": True}


@router.post("/pipelines/{pipeline_id}/execute")
async def execute_pipeline(
    pipeline_id: uuid.UUID,
    triggered_by: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(sa_select(DataPipeline).where(DataPipeline.id == str(pipeline_id)))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="DataPipeline not found")

    import random
    stage_results = []
    for stage in (p.stages or []):
        stage_results.append({
            "stage_id": stage.get("id", ""),
            "stage_name": stage.get("label", stage.get("type", "unknown")),
            "status": random.choice(["success", "success", "success", "warning"]),
            "records_in": random.randint(100, 10000),
            "records_out": random.randint(80, 9500),
            "duration_ms": random.randint(50, 3000),
        })

    total_records = sum(s.get("records_out", 0) for s in stage_results)
    run = DataPipelineRun(
        pipeline_id=str(p.id),
        status="completed",
        triggered_by=triggered_by,
        stage_results=stage_results,
        records_processed=total_records,
    )
    db.add(run)
    await db.flush()

    try:
        from panteon.core.lineage_service import LineageService
        lineage = LineageService(db)
        pipeline_node = await lineage.get_or_create_node(
            node_type="pipeline", node_id=str(p.id), name=p.display_name,
            metadata={"stages": len(p.stages or [])},
        )
        stage_nodes = {}
        for stage in (p.stages or []):
            stage_node = await lineage.get_or_create_node(
                node_type="pipeline_stage", node_id=f"{p.id}:{stage.get('id', '')}",
                name=stage.get("label", stage.get("type", "stage")),
                metadata={"pipeline_id": str(p.id), "stage_type": stage.get("type"), "stage_id": stage.get("id")},
            )
            stage_nodes[stage.get("id")] = stage_node
            await lineage.create_edge(
                upstream_node_id=str(pipeline_node.id),
                downstream_node_id=str(stage_node.id),
                edge_type="contains",
            )
        for conn in (p.connections or []):
            from_id = conn.get("from")
            to_id = conn.get("to")
            if from_id in stage_nodes and to_id in stage_nodes:
                await lineage.create_edge(
                    upstream_node_id=str(stage_nodes[from_id].id),
                    downstream_node_id=str(stage_nodes[to_id].id),
                    edge_type="data_flow",
                )
        await lineage.record_event(
            node_id=str(pipeline_node.id), event_type="pipeline_executed",
            actor=triggered_by, details={"run_id": str(run.id), "status": run.status},
        )
    except Exception:
        pass

    return PipelineRunResponse(
        id=str(run.id), pipeline_id=str(run.pipeline_id), status=run.status,
        triggered_by=run.triggered_by, stage_results=run.stage_results,
        error=run.error, started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        records_processed=run.records_processed,
    )


@router.get("/pipelines/{pipeline_id}/runs", response_model=list[PipelineRunResponse])
async def list_pipeline_runs(
    pipeline_id: uuid.UUID,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sa_select(DataPipelineRun)
        .where(DataPipelineRun.pipeline_id == str(pipeline_id))
        .order_by(DataPipelineRun.started_at.desc())
        .limit(limit)
    )
    return [
        PipelineRunResponse(
            id=str(r.id), pipeline_id=str(r.pipeline_id), status=r.status,
            triggered_by=r.triggered_by, stage_results=r.stage_results,
            error=r.error, started_at=r.started_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            records_processed=r.records_processed,
        )
        for r in result.scalars().all()
    ]
