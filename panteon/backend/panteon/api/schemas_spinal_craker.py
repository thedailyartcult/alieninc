from pydantic import BaseModel, Field
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class ObjectTypeCreate(BaseModel):
    name: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    properties_schema: Optional[dict] = None
    icon: Optional[str] = None


class ObjectTypeResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    description: Optional[str]
    icon: Optional[str]
    properties_schema: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ObjectCreate(BaseModel):
    object_type_id: UUID
    primary_key_value: str = Field(..., max_length=500)
    properties: Optional[dict] = None


class ObjectUpdate(BaseModel):
    properties: dict


class ObjectResponse(BaseModel):
    id: UUID
    object_type_id: UUID
    primary_key_value: str
    properties: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class LinkTypeCreate(BaseModel):
    name: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=255)
    source_type_id: UUID
    target_type_id: UUID
    description: Optional[str] = None
    cardinality: str = "many-to-many"


class LinkTypeResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    source_type_id: UUID
    target_type_id: UUID
    cardinality: str
    created_at: datetime

    class Config:
        from_attributes = True


class LinkCreate(BaseModel):
    link_type_id: UUID
    source_object_id: UUID
    target_object_id: UUID
    properties: Optional[dict] = None


class LinkResponse(BaseModel):
    id: UUID
    link_type_id: UUID
    source_object_id: UUID
    target_object_id: UUID
    properties: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ActionTypeCreate(BaseModel):
    name: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=255)
    object_type_id: UUID
    description: Optional[str] = None
    parameters_schema: Optional[dict] = None
    effects: Optional[list] = None


class ActionTypeResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    object_type_id: UUID
    parameters_schema: dict
    effects: list
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True
