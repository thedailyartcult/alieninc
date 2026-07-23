import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Integer
from panteon.core.database import Base
from panteon.core.types import UUID_COL, JSONB


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_email = Column(String(255), index=True)
    user_id = Column(String(255))
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    status_code = Column(Integer, nullable=False)
    client_ip = Column(String(50))
    user_agent = Column(String(500))
    request_body_hash = Column(String(64))
    response_summary = Column(Text)
    duration_ms = Column(Integer)
    metadata_json = Column("metadata_json", JSONB, default=dict)
