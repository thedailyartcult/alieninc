import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, ForeignKey,
    UniqueConstraint, Index, Integer
)
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class ObjectType(Base):
    __tablename__ = "sc_object_types"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    icon = Column(String(50))
    properties_schema = Column(JSONB, default=dict)
    is_abstract = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    objects = relationship("Object", back_populates="object_type", cascade="all, delete-orphan")
    link_types_as_source = relationship(
        "LinkType", foreign_keys="LinkType.source_type_id", back_populates="source_type"
    )
    link_types_as_target = relationship(
        "LinkType", foreign_keys="LinkType.target_type_id", back_populates="target_type"
    )
    actions = relationship("ActionType", back_populates="object_type")

    __table_args__ = (
        Index("ix_object_types_name", "name"),
    )


class Object(Base):
    __tablename__ = "sc_objects"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    object_type_id = Column(UUID_COL(), ForeignKey("sc_object_types.id"), nullable=False)
    primary_key_value = Column(String(500), nullable=False)
    properties = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255))
    updated_by = Column(String(255))

    object_type = relationship("ObjectType", back_populates="objects")
    outgoing_links = relationship(
        "Link", foreign_keys="Link.source_object_id", back_populates="source_object"
    )
    incoming_links = relationship(
        "Link", foreign_keys="Link.target_object_id", back_populates="target_object"
    )

    __table_args__ = (
        UniqueConstraint("object_type_id", "primary_key_value", name="uq_object_pk"),
        Index("ix_objects_type", "object_type_id"),
    )


class LinkType(Base):
    __tablename__ = "sc_link_types"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    source_type_id = Column(UUID_COL(), ForeignKey("sc_object_types.id"), nullable=False)
    target_type_id = Column(UUID_COL(), ForeignKey("sc_object_types.id"), nullable=False)
    cardinality = Column(String(20), default="many-to-many")
    is_required = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_type = relationship("ObjectType", foreign_keys=[source_type_id], back_populates="link_types_as_source")
    target_type = relationship("ObjectType", foreign_keys=[target_type_id], back_populates="link_types_as_target")
    links = relationship("Link", back_populates="link_type", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("name", "source_type_id", "target_type_id", name="uq_link_type"),
        Index("ix_link_types_source", "source_type_id"),
        Index("ix_link_types_target", "target_type_id"),
    )


class Link(Base):
    __tablename__ = "sc_links"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    link_type_id = Column(UUID_COL(), ForeignKey("sc_link_types.id"), nullable=False)
    source_object_id = Column(UUID_COL(), ForeignKey("sc_objects.id"), nullable=False)
    target_object_id = Column(UUID_COL(), ForeignKey("sc_objects.id"), nullable=False)
    properties = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    link_type = relationship("LinkType", back_populates="links")
    source_object = relationship("Object", foreign_keys=[source_object_id], back_populates="outgoing_links")
    target_object = relationship("Object", foreign_keys=[target_object_id], back_populates="incoming_links")

    __table_args__ = (
        UniqueConstraint("link_type_id", "source_object_id", "target_object_id", name="uq_link"),
        Index("ix_links_source", "source_object_id"),
        Index("ix_links_target", "target_object_id"),
        Index("ix_links_type", "link_type_id"),
    )


class ActionType(Base):
    __tablename__ = "sc_action_types"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    object_type_id = Column(UUID_COL(), ForeignKey("sc_object_types.id"), nullable=False)
    parameters_schema = Column(JSONB, default=dict)
    effects = Column(JSONB, default=list)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    object_type = relationship("ObjectType", back_populates="actions")
    executions = relationship("ActionExecution", back_populates="action_type")

    __table_args__ = (
        Index("ix_action_types_object_type", "object_type_id"),
    )


class ActionExecution(Base):
    __tablename__ = "sc_action_executions"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_type_id = Column(UUID_COL(), ForeignKey("sc_action_types.id"), nullable=False)
    object_id = Column(UUID_COL(), ForeignKey("sc_objects.id"))
    parameters = Column(JSONB, default=dict)
    status = Column(String(50), default="pending")
    result = Column(JSONB)
    error = Column(Text)
    executed_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    executed_by = Column(String(255))

    action_type = relationship("ActionType", back_populates="executions")

    __table_args__ = (
        Index("ix_action_executions_status", "status"),
        Index("ix_action_executions_executed_at", "executed_at"),
    )


class DataPipeline(Base):
    __tablename__ = "sc_pipelines"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    stages = Column(JSONB, default=list)
    connections = Column(JSONB, default=list)
    config = Column(JSONB, default=dict)
    is_draft = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs = relationship("DataPipelineRun", back_populates="pipeline", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pipelines_name", "name"),
    )


class DataPipelineRun(Base):
    __tablename__ = "sc_pipeline_runs"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(UUID_COL(), ForeignKey("sc_pipelines.id"), nullable=False)
    status = Column(String(50), default="pending")
    triggered_by = Column(String(255))
    stage_results = Column(JSONB, default=list)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    records_processed = Column(Integer, default=0)

    pipeline = relationship("DataPipeline", back_populates="runs")

    __table_args__ = (
        Index("ix_pipeline_runs_status", "status"),
        Index("ix_pipeline_runs_pipeline", "pipeline_id"),
    )
