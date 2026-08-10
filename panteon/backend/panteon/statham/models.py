import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class Environment(Base):
    __tablename__ = "statham_environments"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    env_type = Column(String(50), nullable=False)
    description = Column(Text)
    config = Column(JSONB, default=dict)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deployments = relationship("Deployment", back_populates="environment")
    agents = relationship("StathamAgent", back_populates="environment")

    __table_args__ = (
        Index("ix_env_type", "env_type"),
        Index("ix_env_status", "status"),
    )


class StathamAgent(Base):
    __tablename__ = "statham_agents"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    environment_id = Column(UUID_COL(), ForeignKey("statham_environments.id"), nullable=False)
    agent_type = Column(String(50), nullable=False)
    hostname = Column(String(255))
    ip_address = Column(String(50))
    version = Column(String(50))
    status = Column(String(50), default="online")
    last_heartbeat = Column(DateTime)
    agent_info = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    environment = relationship("Environment", back_populates="agents")

    __table_args__ = (
        Index("ix_agent_env", "environment_id"),
        Index("ix_agent_status", "status"),
    )


class Service(Base):
    __tablename__ = "statham_services"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    repo_url = Column(Text)
    language = Column(String(50))
    current_version = Column(String(100))
    health_endpoint = Column(String(500))
    config = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deployments = relationship("Deployment", back_populates="service")
    health_checks = relationship("HealthCheck", back_populates="service")

    __table_args__ = (Index("ix_service_name", "name"),)


class Deployment(Base):
    __tablename__ = "statham_deployments"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_id = Column(UUID_COL(), ForeignKey("statham_services.id"), nullable=False)
    environment_id = Column(UUID_COL(), ForeignKey("statham_environments.id"), nullable=False)
    version = Column(String(100), nullable=False)
    status = Column(String(50), default="pending")
    deploy_type = Column(String(50), default="rolling")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    triggered_by = Column(String(255))
    config = Column(JSONB, default=dict)
    logs = Column(JSONB, default=list)
    rollback_from = Column(UUID_COL())

    service = relationship("Service", back_populates="deployments")
    environment = relationship("Environment", back_populates="deployments")

    __table_args__ = (
        Index("ix_deploy_service", "service_id"),
        Index("ix_deploy_env", "environment_id"),
        Index("ix_deploy_status", "status"),
    )


class HealthCheck(Base):
    __tablename__ = "statham_health_checks"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_id = Column(UUID_COL(), ForeignKey("statham_services.id"), nullable=False)
    environment_id = Column(UUID_COL(), ForeignKey("statham_environments.id"))
    status = Column(String(50), nullable=False)
    latency_ms = Column(Integer)
    response_code = Column(Integer)
    checked_at = Column(DateTime, default=datetime.utcnow)
    details = Column(JSONB, default=dict)

    service = relationship("Service", back_populates="health_checks")

    __table_args__ = (
        Index("ix_health_service", "service_id"),
        Index("ix_health_checked", "checked_at"),
    )


class Pipeline(Base):
    __tablename__ = "statham_pipelines"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    service_id = Column(UUID_COL(), ForeignKey("statham_services.id"))
    stages = Column(JSONB, default=list)
    triggers = Column(JSONB, default=list)
    is_enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime)
    last_status = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("PipelineRun", back_populates="pipeline")

    __table_args__ = (
        Index("ix_pipeline_service", "service_id"),
    )


class PipelineRun(Base):
    __tablename__ = "statham_pipeline_runs"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(UUID_COL(), ForeignKey("statham_pipelines.id"), nullable=False)
    status = Column(String(50), default="pending")
    stages_completed = Column(Integer, default=0)
    stages_total = Column(Integer, default=0)
    triggered_by = Column(String(255))
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    logs = Column(JSONB, default=list)

    pipeline = relationship("Pipeline", back_populates="runs")

    __table_args__ = (
        Index("ix_piperun_pipeline", "pipeline_id"),
        Index("ix_piperun_status", "status"),
    )
