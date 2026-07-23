import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.core.database import get_db
from panteon.spinal_craker.service import OntologyService
from panteon.api.schemas_spinal_craker import (
    ObjectTypeCreate, ObjectTypeResponse,
    ObjectCreate, ObjectUpdate, ObjectResponse,
    LinkTypeCreate, LinkTypeResponse,
    LinkCreate, LinkResponse,
    ActionTypeCreate, ActionTypeResponse,
)

router = APIRouter(prefix="/spinal-craker", tags=["Spinal Craker"])


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
