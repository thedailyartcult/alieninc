import uuid
from typing import Any, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.spinal_craker.models import (
    ObjectType, Object, LinkType, Link, ActionType, ActionExecution
)
from panteon.core.database import is_sqlite


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class OntologyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_object_type(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        properties_schema: Optional[dict] = None,
        icon: Optional[str] = None,
    ) -> ObjectType:
        obj_type = ObjectType(
            name=name,
            display_name=display_name,
            description=description,
            properties_schema=properties_schema or {},
            icon=icon,
        )
        self.db.add(obj_type)
        await self.db.flush()
        return obj_type

    async def get_object_type(self, type_id: uuid.UUID) -> Optional[ObjectType]:
        result = await self.db.execute(
            select(ObjectType).where(ObjectType.id == _uid(type_id))
        )
        return result.scalar_one_or_none()

    async def get_object_type_by_name(self, name: str) -> Optional[ObjectType]:
        result = await self.db.execute(
            select(ObjectType).where(ObjectType.name == name)
        )
        return result.scalar_one_or_none()

    async def list_object_types(self) -> list[ObjectType]:
        result = await self.db.execute(select(ObjectType).order_by(ObjectType.name))
        return list(result.scalars().all())

    async def create_object(
        self,
        object_type_id: uuid.UUID,
        primary_key_value: str,
        properties: Optional[dict] = None,
        created_by: Optional[str] = None,
    ) -> Object:
        obj = Object(
            object_type_id=_uid(object_type_id),
            primary_key_value=primary_key_value,
            properties=properties or {},
            created_by=created_by,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def get_object(self, object_id: uuid.UUID) -> Optional[Object]:
        result = await self.db.execute(
            select(Object)
            .options(selectinload(Object.object_type))
            .where(Object.id == _uid(object_id))
        )
        return result.scalar_one_or_none()

    async def get_object_by_pk(
        self, object_type_id: uuid.UUID, primary_key_value: str
    ) -> Optional[Object]:
        result = await self.db.execute(
            select(Object)
            .options(selectinload(Object.object_type))
            .where(
                and_(
                    Object.object_type_id == _uid(object_type_id),
                    Object.primary_key_value == primary_key_value,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_objects(
        self,
        object_type_id: Optional[uuid.UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Object]:
        query = select(Object).options(selectinload(Object.object_type))
        if object_type_id:
            query = query.where(Object.object_type_id == _uid(object_type_id))
        query = query.order_by(Object.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_object(
        self,
        object_id: uuid.UUID,
        properties: dict,
        updated_by: Optional[str] = None,
    ) -> Optional[Object]:
        obj = await self.get_object(object_id)
        if not obj:
            return None
        obj.properties = {**obj.properties, **properties}
        obj.updated_by = updated_by
        await self.db.flush()
        return obj

    async def delete_object(self, object_id: uuid.UUID) -> bool:
        obj = await self.get_object(object_id)
        if not obj:
            return False
        await self.db.delete(obj)
        await self.db.flush()
        return True

    async def create_link_type(
        self,
        name: str,
        display_name: str,
        source_type_id: uuid.UUID,
        target_type_id: uuid.UUID,
        description: Optional[str] = None,
        cardinality: str = "many-to-many",
    ) -> LinkType:
        link_type = LinkType(
            name=name,
            display_name=display_name,
            source_type_id=_uid(source_type_id),
            target_type_id=_uid(target_type_id),
            description=description,
            cardinality=cardinality,
        )
        self.db.add(link_type)
        await self.db.flush()
        return link_type

    async def create_link(
        self,
        link_type_id: uuid.UUID,
        source_object_id: uuid.UUID,
        target_object_id: uuid.UUID,
        properties: Optional[dict] = None,
    ) -> Link:
        link = Link(
            link_type_id=_uid(link_type_id),
            source_object_id=_uid(source_object_id),
            target_object_id=_uid(target_object_id),
            properties=properties or {},
        )
        self.db.add(link)
        await self.db.flush()
        return link

    async def get_object_links(
        self,
        object_id: uuid.UUID,
        direction: str = "outgoing",
    ) -> list[Link]:
        if direction == "outgoing":
            query = select(Link).where(Link.source_object_id == _uid(object_id))
        else:
            query = select(Link).where(Link.target_object_id == _uid(object_id))
        query = query.options(
            selectinload(Link.link_type),
            selectinload(Link.source_object),
            selectinload(Link.target_object),
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_action_type(
        self,
        name: str,
        display_name: str,
        object_type_id: uuid.UUID,
        description: Optional[str] = None,
        parameters_schema: Optional[dict] = None,
        effects: Optional[list] = None,
    ) -> ActionType:
        action_type = ActionType(
            name=name,
            display_name=display_name,
            object_type_id=object_type_id,
            description=description,
            parameters_schema=parameters_schema or {},
            effects=effects or [],
        )
        self.db.add(action_type)
        await self.db.flush()
        return action_type

    async def execute_action(
        self,
        action_type_id: uuid.UUID,
        object_id: Optional[uuid.UUID] = None,
        parameters: Optional[dict] = None,
        executed_by: Optional[str] = None,
    ) -> ActionExecution:
        execution = ActionExecution(
            action_type_id=_uid(action_type_id),
            object_id=_uid(object_id),
            parameters=parameters or {},
            executed_by=executed_by,
            status="pending",
        )
        self.db.add(execution)
        await self.db.flush()
        return execution

    async def search_objects(
        self,
        object_type_id: Optional[uuid.UUID] = None,
        property_filters: Optional[dict] = None,
        limit: int = 100,
    ) -> list[Object]:
        query = select(Object).options(selectinload(Object.object_type))
        if object_type_id:
            query = query.where(Object.object_type_id == _uid(object_type_id))
        query = query.order_by(Object.created_at.desc()).limit(limit * 5 if property_filters else limit)
        result = await self.db.execute(query)
        objects = list(result.scalars().all())
        if property_filters:
            filtered = []
            for obj in objects:
                props = obj.properties or {}
                match = all(str(props.get(k)) == str(v) for k, v in property_filters.items())
                if match:
                    filtered.append(obj)
            return filtered[:limit]
        return objects
