import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    slug = Column(String(100), nullable=False, unique=True)
    config = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    metrics = relationship("TenantMetric", back_populates="tenant", cascade="all, delete-orphan")
    webhooks = relationship("TenantWebhook", back_populates="tenant", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tenants_slug", "slug"),
        Index("ix_tenants_active", "is_active"),
    )


class TenantMetric(Base):
    __tablename__ = "tenant_metrics"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID_COL(), ForeignKey("tenants.id"), nullable=False)
    metric_type = Column(String(100), nullable=False)
    value = Column(JSONB, nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow)
    period_start = Column(DateTime)
    period_end = Column(DateTime)

    tenant = relationship("Tenant", back_populates="metrics")

    __table_args__ = (
        Index("ix_tenant_metrics_tenant", "tenant_id"),
        Index("ix_tenant_metrics_type", "metric_type"),
        Index("ix_tenant_metrics_computed", "computed_at"),
    )


class TenantWebhook(Base):
    __tablename__ = "tenant_webhooks"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID_COL(), ForeignKey("tenants.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    url = Column(Text, nullable=False)
    secret = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="webhooks")

    __table_args__ = (
        Index("ix_tenant_webhooks_tenant", "tenant_id"),
        Index("ix_tenant_webhooks_event", "event_type"),
    )
