import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    domain = Column(String(255))
    parent_workspace_id = Column(UUID_COL(), ForeignKey("workspaces.id"), nullable=True)
    workspace_type = Column(String(50), default="company")
    config = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = relationship("Workspace", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_workspaces_slug", "slug"),
        Index("ix_workspaces_parent", "parent_workspace_id"),
    )


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(UUID_COL(), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False, default="viewer")
    created_at = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace")

    __table_args__ = (
        Index("ix_ws_memberships_workspace", "workspace_id"),
        Index("ix_ws_memberships_user", "user_email"),
    )
