import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Float, ForeignKey, Index
from sqlalchemy.orm import relationship
from panteon.core.database import Base
from panteon.core.types import JSONB, UUID_COL


class LLMProvider(Base):
    __tablename__ = "yono_llm_providers"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True)
    provider_type = Column(String(50), nullable=False)
    api_key_encrypted = Column(Text)
    base_url = Column(String(500))
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    models = relationship("LLMModel", back_populates="provider", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_yono_llm_providers_type", "provider_type"),)


class LLMModel(Base):
    __tablename__ = "yono_llm_models"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(UUID_COL(), ForeignKey("yono_llm_providers.id"), nullable=False)
    model_id = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=False)
    capabilities = Column(JSONB, default=list)
    max_tokens = Column(Integer, default=4096)
    cost_per_1k_input = Column(Float, default=0.0)
    cost_per_1k_output = Column(Float, default=0.0)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    provider = relationship("LLMProvider", back_populates="models")
    executions = relationship("LLMExecution", back_populates="model")

    __table_args__ = (
        Index("ix_yono_llm_models_provider", "provider_id"),
        Index("ix_yono_llm_models_model_id", "model_id"),
    )


class LLMExecution(Base):
    __tablename__ = "yono_llm_executions"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_id = Column(UUID_COL(), ForeignKey("yono_llm_models.id"), nullable=False)
    prompt = Column(Text, nullable=False)
    system_prompt = Column(Text)
    response = Column(Text)
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    latency_ms = Column(Integer)
    cost = Column(Float, default=0.0)
    status = Column(String(50), default="pending")
    error = Column(Text)
    parameters = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255))

    model = relationship("LLMModel", back_populates="executions")

    __table_args__ = (
        Index("ix_yono_llm_executions_model", "model_id"),
        Index("ix_yono_llm_executions_status", "status"),
        Index("ix_yono_llm_executions_created", "created_at"),
    )


class Agent(Base):
    __tablename__ = "yono_agents"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    system_prompt = Column(Text, nullable=False)
    model_id = Column(UUID_COL(), ForeignKey("yono_llm_models.id"))
    tools = Column(JSONB, default=list)
    memory_config = Column(JSONB, default=dict)
    max_iterations = Column(Integer, default=10)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("AgentSession", back_populates="agent")

    __table_args__ = (Index("ix_yono_agents_model", "model_id"),)


class AgentSession(Base):
    __tablename__ = "yono_agent_sessions"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(UUID_COL(), ForeignKey("yono_agents.id"), nullable=False)
    user_id = Column(String(255))
    messages = Column(JSONB, default=list)
    context = Column(JSONB, default=dict)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="sessions")

    __table_args__ = (
        Index("ix_yono_agent_sessions_agent", "agent_id"),
        Index("ix_yono_agent_sessions_status", "status"),
    )


class Automation(Base):
    __tablename__ = "yono_automations"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    trigger_type = Column(String(50), nullable=False)
    trigger_config = Column(JSONB, default=dict)
    conditions = Column(JSONB, default=list)
    effects = Column(JSONB, default=list)
    is_enabled = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    executions = relationship("AutomationExecution", back_populates="automation")

    __table_args__ = (
        Index("ix_yono_automations_trigger", "trigger_type"),
        Index("ix_yono_automations_enabled", "is_enabled"),
    )


class AutomationExecution(Base):
    __tablename__ = "yono_automation_executions"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    automation_id = Column(UUID_COL(), ForeignKey("yono_automations.id"), nullable=False)
    trigger_data = Column(JSONB, default=dict)
    status = Column(String(50), default="pending")
    result = Column(JSONB)
    error = Column(Text)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    automation = relationship("Automation", back_populates="executions")

    __table_args__ = (
        Index("ix_yono_automation_executions_automation", "automation_id"),
        Index("ix_yono_automation_executions_status", "status"),
    )


class Evaluation(Base):
    __tablename__ = "yono_evaluations"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    eval_type = Column(String(50), nullable=False)
    test_cases = Column(JSONB, default=list)
    metrics = Column(JSONB, default=list)
    last_run_at = Column(DateTime)
    last_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("EvaluationRun", back_populates="evaluation")


class EvaluationRun(Base):
    __tablename__ = "yono_evaluation_runs"

    id = Column(UUID_COL(), primary_key=True, default=lambda: str(uuid.uuid4()))
    evaluation_id = Column(UUID_COL(), ForeignKey("yono_evaluations.id"), nullable=False)
    results = Column(JSONB, default=dict)
    overall_score = Column(Float)
    status = Column(String(50), default="pending")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    evaluation = relationship("Evaluation", back_populates="runs")

    __table_args__ = (Index("ix_yono_eval_runs_evaluation", "evaluation_id"),)
