"""AI Memory System - Stores learnings across sessions.

This agent manages persistent learning across sessions, using CMB for durable memory
storage and retrieval to enable cross-session knowledge accumulation and growth.
"""

from __future__ import annotations

import json
import hashlib
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta

from engine.character import Character


class MemorySystemAgent:
    """Manages persistent learning across sessions using durable memory storage."""

    def __init__(self, workspace: str = "alphazero"):
        self.workspace = workspace
        self.memory_store: Dict[str, Dict[str, Any]] = {}
        self.learning_patterns: List[Dict[str, Any]] = []
        self.knowledge_graph: Dict[str, Set[str]] = {}
        self.session_memories: Dict[str, Dict[str, Any]] = {}
        self.retention_policies: Dict[str, Dict[str, Any]] = {}

    def store_learning(self, learning_data: Dict[str, Any], session_id: str = None) -> str:
        """Store a learning across sessions with retention policy."""
        learning_id = self._generate_learning_id(learning_data)

        learning_entry = {
            "id": learning_id,
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "data": learning_data,
            "tags": self._extract_tags(learning_data),
            "importance": self._calculate_importance(learning_data),
            "source": learning_data.get("source", "ai_agent"),
            "access_count": 0,
            "last_accessed": None,
        }

        self.memory_store[learning_id] = learning_entry
        self._update_knowledge_graph(learning_entry)
        self._apply_retention_policy(learning_entry)

        return learning_id

    def retrieve_learnings(
        self,
        query: str = None,
        tags: List[str] = None,
        importance_threshold: int = 0,
        session_id: str = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve learnings based on criteria."""
        results = []

        for learning_id, learning in self.memory_store.items():
            if learning["importance"] < importance_threshold:
                continue

            if session_id and learning.get("session_id") != session_id:
                continue

            if tags and not self._match_tags(learning, tags):
                continue

            if query and not self._match_query(learning, query):
                continue

            learning["access_count"] += 1
            learning["last_accessed"] = datetime.now().isoformat()
            results.append(learning)

        results.sort(key=lambda x: x["importance"], reverse=True)
        return results[:limit]

    def retrieve_by_character(self, character: Character, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve learnings relevant to a specific character."""
        relevant_learnings = []

        for learning_id, learning in self.memory_store.items():
            if self._is_relevant_to_character(learning, character):
                relevant_learnings.append(learning)

        relevant_learnings.sort(
            key=lambda x: x["importance"] * self._calculate_character_relevance(x, character), reverse=True
        )

        return relevant_learnings[:limit]

    def update_learning(self, learning_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing learning."""
        if learning_id not in self.memory_store:
            return False

        for key, value in updates.items():
            self.memory_store[learning_id][key] = value

        self._update_knowledge_graph(self.memory_store[learning_id])
        return True

    def delete_learning(self, learning_id: str) -> bool:
        """Delete a learning."""
        if learning_id not in self.memory_store:
            return False

        learning = self.memory_store[learning_id]

        for concept in learning["tags"]:
            if concept in self.knowledge_graph:
                self.knowledge_graph[concept].discard(learning_id)

        del self.memory_store[learning_id]
        return True

    def get_learning_patterns(self, time_window_days: int = 30) -> List[Dict[str, Any]]:
        """Identify learning patterns over time."""
        cutoff_date = datetime.now() - timedelta(days=time_window_days)

        recent_learnings = [
            learning for learning in self.memory_store.values()
            if datetime.fromisoformat(learning["timestamp"]) > cutoff_date
        ]

        patterns = []

        for tag in set(tag for learning in recent_learnings for tag in learning["tags"]):
            tag_learnings = [
                learning for learning in recent_learnings if tag in learning["tags"]
            ]

            if len(tag_learnings) >= 3:
                pattern = {
                    "tag": tag,
                    "frequency": len(tag_learnings),
                    "importance_average": sum(l["importance"] for l in tag_learnings)
                    / len(tag_learnings),
                    "source_distribution": self._analyze_source_distribution(tag_learnings),
                    "temporal_pattern": self._analyze_temporal_pattern(tag_learnings),
                }
                patterns.append(pattern)

        patterns.sort(key=lambda x: x["frequency"], reverse=True)
        return patterns

    def get_character_insights(self, character: Character) -> Dict[str, Any]:
        """Generate insights about character based on learned knowledge."""
        relevant_learnings = self.retrieve_by_character(character)

        insights = {
            "strength_patterns": self._identify_strength_patterns(relevant_learnings, character),
            "improvement_opportunities": self._identify_improvement_opportunities(
                relevant_learnings, character
            ),
            "decision_patterns": self._analyze_decision_patterns(relevant_learnings, character),
            "growth_trajectory": self._determine_growth_trajectory(relevant_learnings, character),
            "recommendations": self._generate_character_recommendations(relevant_learnings, character),
        }

        return insights

    def export_knowledge(self, format: str = "json") -> str:
        """Export knowledge in specified format."""
        data = {
            "memories": list(self.memory_store.values()),
            "patterns": self.learning_patterns,
            "knowledge_graph": self.knowledge_graph,
            "export_timestamp": datetime.now().isoformat(),
        }

        if format == "json":
            return json.dumps(data, indent=2)
        else:
            return json.dumps(data, indent=2)

    def import_knowledge(self, data: Dict[str, Any], merge: bool = True) -> bool:
        """Import knowledge from data."""
        try:
            imported_memories = data.get("memories", [])

            for memory in imported_memories:
                memory_id = memory["id"]
                if not merge or memory_id not in self.memory_store:
                    self.memory_store[memory_id] = memory
                    self._update_knowledge_graph(memory)

            return True
        except Exception:
            return False

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary of a session's memories."""
        if session_id not in self.session_memories:
            return {"error": "Session not found"}

        session_data = self.session_memories[session_id]

        return {
            "session_id": session_id,
            "start_time": session_data.get("start_time"),
            "end_time": session_data.get("end_time"),
            "learnings_count": len(session_data.get("learnings", [])),
            "characters_visited": session_data.get("characters_visited", []),
            "topics_covered": session_data.get("topics_covered", []),
            "key_insights": session_data.get("key_insights", []),
        }

    def create_session(self, session_id: str, initial_context: Dict[str, Any] = None) -> bool:
        """Create a new session context."""
        if session_id in self.session_memories:
            return False

        session_data = {
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "learnings": [],
            "characters_visited": [],
            "topics_covered": [],
            "key_insights": [],
        }

        if initial_context:
            session_data.update(initial_context)

        self.session_memories[session_id] = session_data
        return True

    def end_session(self, session_id: str, final_insights: List[str] = None) -> bool:
        """End a session and record final insights."""
        if session_id not in self.session_memories:
            return False

        self.session_memories[session_id]["end_time"] = datetime.now().isoformat()

        if final_insights:
            self.session_memories[session_id]["key_insights"] = final_insights

        return True
