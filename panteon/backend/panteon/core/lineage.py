import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class LineageNode(Base):
    __tablename__ = "lineage_nodes"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    node_type = Column(String(50), nullable=False, index=True)
    node_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    workspace_id = Column(String(36), index=True)
    metadata_json = Column("metadata_json", JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    upstream_edges = relationship(
        "LineageEdge",
        foreign_keys="LineageEdge.downstream_node_id",
        back_populates="downstream_node",
        cascade="all, delete-orphan",
    )
    downstream_edges = relationship(
        "LineageEdge",
        foreign_keys="LineageEdge.upstream_node_id",
        back_populates="upstream_node",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_lineage_nodes_type_id", "node_type", "node_id", unique=True),
    )


class LineageEdge(Base):
    __tablename__ = "lineage_edges"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    upstream_node_id = Column(UUID_COL(), ForeignKey("lineage_nodes.id"), nullable=False, index=True)
    downstream_node_id = Column(UUID_COL(), ForeignKey("lineage_nodes.id"), nullable=False, index=True)
    edge_type = Column(String(50), nullable=False)
    description = Column(Text)
    metadata_json = Column("metadata_json", JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    upstream_node = relationship(
        "LineageNode",
        foreign_keys=[upstream_node_id],
        back_populates="downstream_edges",
    )
    downstream_node = relationship(
        "LineageNode",
        foreign_keys=[downstream_node_id],
        back_populates="upstream_edges",
    )

    __table_args__ = (
        Index("ix_lineage_edges_upstream", "upstream_node_id"),
        Index("ix_lineage_edges_downstream", "downstream_node_id"),
        Index("ix_lineage_edges_type", "edge_type"),
    )


class LineageEvent(Base):
    __tablename__ = "lineage_events"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    node_id = Column(UUID_COL(), ForeignKey("lineage_nodes.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    actor = Column(String(255))
    details = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    node = relationship("LineageNode")

    __table_args__ = (
        Index("ix_lineage_events_node", "node_id"),
        Index("ix_lineage_events_type", "event_type"),
        Index("ix_lineage_events_created", "created_at"),
    )
