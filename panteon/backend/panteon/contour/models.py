import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer, Float, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class Dashboard(Base):
    __tablename__ = "contour_dashboards"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    workspace_id = Column(String(36), index=True)
    layout = Column(JSONB, default=dict)
    filters = Column(JSONB, default=list)
    is_public = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_viewed_at = Column(DateTime)
    view_count = Column(Integer, default=0)

    charts = relationship("Chart", back_populates="dashboard", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contour_dashboards_workspace", "workspace_id"),
        Index("ix_contour_dashboards_name", "name"),
    )


class Chart(Base):
    __tablename__ = "contour_charts"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id = Column(UUID_COL(), ForeignKey("contour_dashboards.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    chart_type = Column(String(50), nullable=False)
    data_source = Column(JSONB, nullable=False)
    config = Column(JSONB, default=dict)
    position = Column(JSONB, default=dict)
    refresh_interval_seconds = Column(Integer, default=300)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dashboard = relationship("Dashboard", back_populates="charts")

    __table_args__ = (
        Index("ix_contour_charts_type", "chart_type"),
        Index("ix_contour_charts_dashboard", "dashboard_id"),
    )


class PipelineSchedule(Base):
    __tablename__ = "contour_pipeline_schedules"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    timezone = Column(String(50), default="UTC")
    is_enabled = Column(Boolean, default=True)
    workspace_id = Column(String(36), index=True)
    last_run_at = Column(DateTime)
    last_run_status = Column(String(20))
    next_run_at = Column(DateTime)
    retry_count = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs = relationship("PipelineScheduleRun", back_populates="schedule", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contour_schedules_pipeline", "pipeline_id"),
        Index("ix_contour_schedules_next_run", "next_run_at"),
        Index("ix_contour_schedules_enabled", "is_enabled"),
    )


class PipelineScheduleRun(Base):
    __tablename__ = "contour_pipeline_schedule_runs"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id = Column(UUID_COL(), ForeignKey("contour_pipeline_schedules.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_ms = Column(Integer)
    records_processed = Column(Integer, default=0)
    error_message = Column(Text)
    retry_attempt = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    schedule = relationship("PipelineSchedule", back_populates="runs")

    __table_args__ = (
        Index("ix_contour_runs_status", "status"),
        Index("ix_contour_runs_schedule", "schedule_id"),
        Index("ix_contour_runs_created", "created_at"),
    )


class DataQualityRule(Base):
    __tablename__ = "contour_data_quality_rules"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    object_type_id = Column(String(36), nullable=False, index=True)
    rule_type = Column(String(50), nullable=False)
    config = Column(JSONB, nullable=False)
    severity = Column(String(20), default="warning")
    is_enabled = Column(Boolean, default=True)
    workspace_id = Column(String(36), index=True)
    last_checked_at = Column(DateTime)
    last_violation_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_contour_dq_rules_type", "rule_type"),
        Index("ix_contour_dq_rules_object_type", "object_type_id"),
    )


class DataQualityViolation(Base):
    __tablename__ = "contour_data_quality_violations"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(UUID_COL(), ForeignKey("contour_data_quality_rules.id"), nullable=False, index=True)
    object_id = Column(String(36))
    violation_type = Column(String(50), nullable=False)
    details = Column(JSONB, default=dict)
    detected_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    resolved_by = Column(String(255))
    status = Column(String(20), default="open")

    __table_args__ = (
        Index("ix_contour_dq_violations_status", "status"),
        Index("ix_contour_dq_violations_detected", "detected_at"),
    )


class SearchIndex(Base):
    __tablename__ = "contour_search_index"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    object_type = Column(String(50), nullable=False, index=True)
    object_id = Column(String(36), nullable=False)
    workspace_id = Column(String(36), index=True)
    title = Column(String(500))
    content = Column(Text)
    tags = Column(JSONB, default=list)
    metadata_json = Column("metadata_json", JSONB, default=dict)
    indexed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_contour_search_type_id", "object_type", "object_id", unique=True),
        Index("ix_contour_search_workspace", "workspace_id"),
        Index("ix_contour_search_title", "title"),
    )
