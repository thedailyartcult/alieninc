from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class Event(BaseModel):
    id: str
    timestamp: datetime
    actor: str
    action: str
    target: Optional[str] = None
    goal_hint: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class IngestRequest(BaseModel):
    events: list[Event]


class ReconstructRequest(BaseModel):
    scope: Optional[str] = None
    time_window: Optional[tuple[datetime, datetime]] = None


class RootCauseRequest(BaseModel):
    target_id: str
    depth: int = Field(default=10, ge=1, le=50)


class CounterfactualRequest(BaseModel):
    event_ids: list[str]
    intervention: str = Field(default="remove", pattern="^(remove|modify)$")


class InferPurposesRequest(BaseModel):
    actor_scope: Optional[list[str]] = None
    evidence_window: Optional[tuple[datetime, datetime]] = None


class ProjectTrajectoryRequest(BaseModel):
    purpose_ids: Optional[list[str]] = None
    horizon: int = Field(default=10, ge=1, le=100)


class LeveragePointsRequest(BaseModel):
    trajectory_id: Optional[str] = None
    objective: str
