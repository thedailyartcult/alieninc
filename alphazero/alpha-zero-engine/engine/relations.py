"""Relationship graph — deterministic relation data driving character events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RelationType(Enum):
    PARENT = "parent"
    SIBLING = "sibling"
    PARTNER = "partner"
    CHILD = "child"
    FRIEND = "friend"
    COLLEAGUE = "colleague"
    MENTOR = "mentor"
    RIVAL = "rival"


class RelationStatus(Enum):
    NEUTRAL = 0
    CLOSE = 1
    DISTANT = 2
    CONFLICT = 3
    ROMANTIC = 4
    MARRIED = 5
    DIVORCED = 6
    ESTRANGED = 7


@dataclass
class Relation:
    """A single relationship node in the character's social graph."""

    relation_id: str
    name: str
    relation_type: RelationType
    status: RelationStatus = RelationStatus.NEUTRAL
    closeness: int = 50  # 0-100
    influence: float = 1.0  # How much this relation affects character rolls

    # Dynamic state
    age: int = 0
    is_alive: bool = True
    occupation: str = "Unknown"

    # History
    events: list = field(default_factory=list)

    def modify_closeness(self, delta: int) -> int:
        self.closeness = max(0, min(100, self.closeness + delta))
        return self.closeness

    def add_event(self, year: int, description: str):
        self.events.append({"year": year, "description": description})

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "name": self.name,
            "type": self.relation_type.value,
            "status": self.status.value,
            "closeness": self.closeness,
            "influence": self.influence,
            "age": self.age,
            "is_alive": self.is_alive,
            "occupation": self.occupation,
        }


class RelationGraph:
    """Manages all relationships for a character."""

    def __init__(self):
        self.relations: dict[str, Relation] = {}

    def add(self, relation: Relation):
        self.relations[relation.relation_id] = relation

    def get(self, relation_id: str) -> Optional[Relation]:
        return self.relations.get(relation_id)

    def get_by_type(self, rtype: RelationType) -> list[Relation]:
        return [r for r in self.relations.values() if r.relation_type == rtype]

    def get_active(self) -> list[Relation]:
        return [r for r in self.relations.values() if r.is_alive]

    def get_influential(self, threshold: float = 0.5) -> list[Relation]:
        return [r for r in self.relations.values() if r.influence >= threshold and r.is_alive]

    def modify_all(self, delta: int, rtype: RelationType = None):
        """Modify closeness for all (or filtered) relations."""
        targets = self.get_by_type(rtype) if rtype else self.relations.values()
        for r in targets:
            r.modify_closeness(delta)

    def to_dict(self) -> dict:
        return {rid: r.to_dict() for rid, r in self.relations.items()}
