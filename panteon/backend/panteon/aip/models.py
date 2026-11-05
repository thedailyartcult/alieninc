import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer, Float, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


# ================================================================
# AIP LOGIC — AI Workflow Engine
# ================================================================

WORKFLOW_STATUSES = ("draft", "active", "paused", "archived")
NODE_TYPES = ("input", "llm_call", "condition", "transform", "rag_query", "api_call", "output", "loop", "parallel", "human_review")
RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


class Workflow(Base):
    __tablename__ = "aip_workflows"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    workspace_id = Column(String(36), index=True)
    status = Column(String(20), nullable=False, default="draft")
    nodes = Column(JSONB, default=list)
    edges = Column(JSONB, default=list)
    variables = Column(JSONB, default=dict)
    config = Column(JSONB, default=dict)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_aip_workflows_status", "status"),
        Index("ix_aip_workflows_workspace", "workspace_id"),
    )


class WorkflowRun(Base):
    __tablename__ = "aip_workflow_runs"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(UUID_COL(), ForeignKey("aip_workflows.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    input_data = Column(JSONB, default=dict)
    output_data = Column(JSONB, default=dict)
    node_results = Column(JSONB, default=dict)
    error = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_ms = Column(Integer)
    triggered_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="runs")

    __table_args__ = (
        Index("ix_aip_workflow_runs_status", "status"),
        Index("ix_aip_workflow_runs_created", "created_at"),
    )


# ================================================================
# RAG — Retrieval-Augmented Generation
# ================================================================

DOC_STATUSES = ("pending", "processed", "failed", "archived")
CHUNK_STATUSES = ("pending", "embedded", "failed")


class RagDocument(Base):
    __tablename__ = "aip_rag_documents"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), index=True)
    source_type = Column(String(50), default="text")
    source_url = Column(String(2000))
    workspace_id = Column(String(36), index=True)
    collection = Column(String(255), index=True)
    status = Column(String(20), nullable=False, default="pending")
    metadata_json = Column("metadata_json", JSONB, default=dict)
    chunk_count = Column(Integer, default=0)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    chunks = relationship("RagChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_aip_rag_docs_workspace", "workspace_id"),
        Index("ix_aip_rag_docs_status", "status"),
        Index("ix_aip_rag_docs_collection", "collection"),
    )


class RagChunk(Base):
    __tablename__ = "aip_rag_chunks"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(UUID_COL(), ForeignKey("aip_rag_documents.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer, default=0)
    embedding_text = Column(Text)
    status = Column(String(20), nullable=False, default="pending")
    metadata_json = Column("metadata_json", JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("RagDocument", back_populates="chunks")

    __table_args__ = (
        Index("ix_aip_rag_chunks_document", "document_id"),
        Index("ix_aip_rag_chunks_index", "chunk_index"),
    )


class KnowledgeEntity(Base):
    __tablename__ = "aip_knowledge_entities"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(500), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    workspace_id = Column(String(36), index=True)
    description = Column(Text)
    attributes = Column(JSONB, default=dict)
    source_document_ids = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_aip_knowledge_entities_type", "entity_type"),
        Index("ix_aip_knowledge_entities_workspace", "workspace_id"),
    )


class KnowledgeRelation(Base):
    __tablename__ = "aip_knowledge_relations"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_entity_id = Column(UUID_COL(), ForeignKey("aip_knowledge_entities.id"), nullable=False, index=True)
    target_entity_id = Column(UUID_COL(), ForeignKey("aip_knowledge_entities.id"), nullable=False, index=True)
    relation_type = Column(String(100), nullable=False)
    confidence = Column(Float, default=1.0)
    source_document_ids = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_aip_knowledge_relations_source", "source_entity_id"),
        Index("ix_aip_knowledge_relations_target", "target_entity_id"),
        Index("ix_aip_knowledge_relations_type", "relation_type"),
    )


# ================================================================
# AIP GUARD — AI Safety & Governance
# ================================================================

GUARD_POLICY_TYPES = ("pii_detection", "toxicity_filter", "output_validation", "topic_restriction", "rate_limit", "custom")
GUARD_SEVERITY = ("info", "warning", "blocked", "critical")


class GuardPolicy(Base):
    __tablename__ = "aip_guard_policies"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    policy_type = Column(String(50), nullable=False)
    config = Column(JSONB, nullable=False)
    severity = Column(String(20), nullable=False, default="warning")
    is_enabled = Column(Boolean, default=True)
    workspace_id = Column(String(36), index=True)
    applies_to = Column(JSONB, default=list)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_aip_guard_policies_type", "policy_type"),
        Index("ix_aip_guard_policies_workspace", "workspace_id"),
    )


class GuardEvent(Base):
    __tablename__ = "aip_guard_events"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(UUID_COL(), ForeignKey("aip_guard_policies.id"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="info")
    input_text = Column(Text)
    output_text = Column(Text)
    details = Column(JSONB, default=dict)
    action_taken = Column(String(50))
    user_email = Column(String(255))
    workspace_id = Column(String(36), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_aip_guard_events_type", "event_type"),
        Index("ix_aip_guard_events_severity", "severity"),
        Index("ix_aip_guard_events_created", "created_at"),
    )


# ================================================================
# PROMPT STUDIO — Versioned Prompts & Evaluation
# ================================================================


class Prompt(Base):
    __tablename__ = "aip_prompts"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    workspace_id = Column(String(36), index=True)
    current_version = Column(Integer, default=1)
    tags = Column(JSONB, default=list)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions = relationship("PromptVersion", back_populates="prompt", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_aip_prompts_workspace", "workspace_id"),
    )


class PromptVersion(Base):
    __tablename__ = "aip_prompt_versions"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt_id = Column(UUID_COL(), ForeignKey("aip_prompts.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    template = Column(Text, nullable=False)
    model_id = Column(String(200))
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=1000)
    variables = Column(JSONB, default=list)
    changelog = Column(Text)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    prompt = relationship("Prompt", back_populates="versions")
    evaluations = relationship("PromptEvaluation", back_populates="version", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_aip_prompt_versions_prompt", "prompt_id"),
        Index("ix_aip_prompt_versions_version", "version"),
    )


class PromptEvaluation(Base):
    __tablename__ = "aip_prompt_evaluations"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(UUID_COL(), ForeignKey("aip_prompt_versions.id"), nullable=False, index=True)
    test_input = Column(Text, nullable=False)
    expected_output = Column(Text)
    actual_output = Column(Text)
    score = Column(Float)
    latency_ms = Column(Integer)
    tokens_used = Column(Integer)
    evaluation_type = Column(String(50), default="manual")
    notes = Column(Text)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    version = relationship("PromptVersion", back_populates="evaluations")

    __table_args__ = (
        Index("ix_aip_prompt_evals_version", "version_id"),
        Index("ix_aip_prompt_evals_created", "created_at"),
    )
