import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer, Float, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


CLASSIFICATION_LEVELS = ("unclassified", "confidential", "secret", "top_secret")
INVESTIGATION_STATUSES = ("open", "in_progress", "pending_review", "closed", "archived")
FINDING_STATUSES = ("draft", "confirmed", "disputed", "retracted")
THREAT_LEVELS = ("low", "elevated", "high", "critical", "imminent")
EVENT_SEVERITY = ("informational", "minor", "moderate", "major", "critical")


class Investigation(Base):
    __tablename__ = "babel_investigations"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number = Column(String(50), nullable=False, unique=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    classification = Column(String(20), nullable=False, default="confidential")
    status = Column(String(20), nullable=False, default="open")
    priority = Column(String(20), nullable=False, default="medium")
    workspace_id = Column(String(36), index=True)
    assigned_analysts = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)
    scope = Column(JSONB, default=dict)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime)

    findings = relationship("Finding", back_populates="investigation", cascade="all, delete-orphan")
    timeline_events = relationship("TimelineEvent", back_populates="investigation", cascade="all, delete-orphan")
    alerts = relationship("PatternAlert", back_populates="investigation")

    __table_args__ = (
        Index("ix_babel_investigations_status", "status"),
        Index("ix_babel_investigations_workspace", "workspace_id"),
        Index("ix_babel_investigations_classification", "classification"),
    )


class Finding(Base):
    __tablename__ = "babel_findings"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id = Column(UUID_COL(), ForeignKey("babel_investigations.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text)
    analysis = Column(Text)
    confidence = Column(Float, default=0.0)
    status = Column(String(20), nullable=False, default="draft")
    finding_type = Column(String(50), default="observation")
    classification = Column(String(20), nullable=False, default="confidential")
    linked_entities = Column(JSONB, default=list)
    linked_objects = Column(JSONB, default=list)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    investigation = relationship("Investigation", back_populates="findings")
    evidence_items = relationship("Evidence", back_populates="finding", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_babel_findings_type", "finding_type"),
        Index("ix_babel_findings_status", "status"),
    )


class Evidence(Base):
    __tablename__ = "babel_evidence"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id = Column(UUID_COL(), ForeignKey("babel_findings.id"), nullable=False, index=True)
    evidence_type = Column(String(50), nullable=False)
    source = Column(String(500))
    content = Column(Text)
    content_hash = Column(String(64))
    classification = Column(String(20), nullable=False, default="confidential")
    metadata_json = Column("metadata_json", JSONB, default=dict)
    collected_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    finding = relationship("Finding", back_populates="evidence_items")

    __table_args__ = (
        Index("ix_babel_evidence_type", "evidence_type"),
    )


class ThreatEntity(Base):
    __tablename__ = "babel_threat_entities"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    name = Column(String(500), nullable=False, index=True)
    aliases = Column(JSONB, default=list)
    description = Column(Text)
    threat_level = Column(String(20), nullable=False, default="low")
    risk_score = Column(Float, default=0.0)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    workspace_id = Column(String(36), index=True)
    connections = Column(JSONB, default=list)
    attributes = Column(JSONB, default=dict)
    classification = Column(String(20), nullable=False, default="confidential")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    geo_events = relationship("GeoEvent", back_populates="threat_entity")

    __table_args__ = (
        Index("ix_babel_threat_entities_type", "entity_type"),
        Index("ix_babel_threat_entities_level", "threat_level"),
        Index("ix_babel_threat_entities_risk", "risk_score"),
        Index("ix_babel_threat_entities_workspace", "workspace_id"),
    )


class GeoEvent(Base):
    __tablename__ = "babel_geo_events"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="moderate")
    latitude = Column(Float)
    longitude = Column(Float)
    country = Column(String(100), index=True)
    region = Column(String(200))
    threat_entity_id = Column(UUID_COL(), ForeignKey("babel_threat_entities.id"), nullable=True, index=True)
    workspace_id = Column(String(36), index=True)
    investigation_id = Column(UUID_COL(), ForeignKey("babel_investigations.id"), nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    metadata_json = Column("metadata_json", JSONB, default=dict)
    classification = Column(String(20), nullable=False, default="confidential")
    created_at = Column(DateTime, default=datetime.utcnow)

    threat_entity = relationship("ThreatEntity", back_populates="geo_events")

    __table_args__ = (
        Index("ix_babel_geo_events_type", "event_type"),
        Index("ix_babel_geo_events_severity", "severity"),
        Index("ix_babel_geo_events_occurred", "occurred_at"),
        Index("ix_babel_geo_events_country", "country"),
        Index("ix_babel_geo_events_coords", "latitude", "longitude"),
    )


class PatternAlert(Base):
    __tablename__ = "babel_pattern_alerts"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    severity = Column(String(20), nullable=False, default="moderate")
    confidence = Column(Float, default=0.0)
    investigation_id = Column(UUID_COL(), ForeignKey("babel_investigations.id"), nullable=True, index=True)
    workspace_id = Column(String(36), index=True)
    triggered_by = Column(JSONB, default=dict)
    affected_entities = Column(JSONB, default=list)
    anomaly_details = Column(JSONB, default=dict)
    status = Column(String(20), nullable=False, default="active")
    classification = Column(String(20), nullable=False, default="confidential")
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(255))

    investigation = relationship("Investigation", back_populates="alerts")

    __table_args__ = (
        Index("ix_babel_alerts_type", "alert_type"),
        Index("ix_babel_alerts_severity", "severity"),
        Index("ix_babel_alerts_status", "status"),
    )


class TimelineEvent(Base):
    __tablename__ = "babel_timeline_events"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id = Column(UUID_COL(), ForeignKey("babel_investigations.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    event_type = Column(String(50), default="note")
    occurred_at = Column(DateTime, nullable=False)
    linked_entities = Column(JSONB, default=list)
    classification = Column(String(20), nullable=False, default="confidential")
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    investigation = relationship("Investigation", back_populates="timeline_events")

    __table_args__ = (
        Index("ix_babel_timeline_occurred", "occurred_at"),
    )


class CountryRiskProfile(Base):
    __tablename__ = "babel_country_risk_profiles"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    country = Column(String(100), nullable=False, unique=True, index=True)
    country_code = Column(String(3), index=True)
    overall_risk_score = Column(Float, default=0.0)
    political_risk = Column(Float, default=0.0)
    security_risk = Column(Float, default=0.0)
    health_risk = Column(Float, default=0.0)
    infrastructure_risk = Column(Float, default=0.0)
    natural_disaster_risk = Column(Float, default=0.0)
    travel_advisory_level = Column(Integer, default=1)
    last_updated = Column(DateTime, default=datetime.utcnow)
    risk_factors = Column(JSONB, default=list)
    recent_events = Column(JSONB, default=list)
    notes = Column(Text)

    __table_args__ = (
        Index("ix_babel_country_risk_score", "overall_risk_score"),
    )
