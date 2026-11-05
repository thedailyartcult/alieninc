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
        self._cmb = None
        try:
            from cmb import (
                cmb_retrieve, cmb_list, cmb_store, cmb_delete, cmb_search,
            )
            self._cmb = {
                "retrieve": cmb_retrieve,
                "list": cmb_list,
                "store": cmb_store,
                "delete": cmb_delete,
                "search": cmb_search,
            }
            self._load_from_cmb()
        except Exception:
            self._cmb = None

    def _cmb_key(self, learning_id: str) -> str:
        return f"learning_{learning_id}"

    def _load_from_cmb(self) -> None:
        """Hydrate in-memory store from the CMB file store on startup."""
        entries = self._cmb["list"](self.workspace, repo="alphazero")
        for entry in entries:
            key = entry.get("key", "")
            if not key.startswith("learning_"):
                continue
            learned = self._cmb["retrieve"](self.workspace, key)
            if not isinstance(learned, dict) or not learned.get("id"):
                continue
            self.memory_store[learned["id"]] = learned
            self._update_knowledge_graph(learned)
            self._apply_retention_policy(learned)

        self._load_sessions_from_cmb()

    def _cmb_session_key(self, session_id: str) -> str:
        return f"session_{session_id}"

    def _load_sessions_from_cmb(self) -> None:
        """Hydrate session contexts from the CMB file store on startup."""
        if self._cmb is None:
            return
        entries = self._cmb["list"](self.workspace, repo="alphazero")
        for entry in entries:
            key = entry.get("key", "")
            if not key.startswith("session_"):
                continue
            session_data = self._cmb["retrieve"](self.workspace, key)
            if not isinstance(session_data, dict) or not session_data.get("start_time"):
                continue
            session_id = key[len("session_"):]
            self.session_memories[session_id] = session_data

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

        if self._cmb is not None:
            self._cmb["store"](self.workspace, self._cmb_key(learning_id), learning_entry,
                               repo="alphazero")

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

        if self._cmb is not None:
            self._cmb["delete"](self.workspace, self._cmb_key(learning_id))

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
        if self._cmb is not None:
            self._cmb["store"](self.workspace, self._cmb_session_key(session_id),
                               session_data, repo="alphazero")
        return True

    def end_session(self, session_id: str, final_insights: List[str] = None) -> bool:
        """End a session and record final insights."""
        if session_id not in self.session_memories:
            return False

        self.session_memories[session_id]["end_time"] = datetime.now().isoformat()

        if final_insights:
            self.session_memories[session_id]["key_insights"] = final_insights

        if self._cmb is not None:
            self._cmb["store"](self.workspace, self._cmb_session_key(session_id),
                               self.session_memories[session_id], repo="alphazero")

        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_learning_id(self, learning_data: Dict[str, Any]) -> str:
        """Generate a deterministic unique id from the learning payload."""
        explicit = learning_data.get("learning_id")
        if explicit:
            return str(explicit)
        key = json.dumps(learning_data, sort_keys=True, default=str)
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def _extract_tags(self, learning_data: Dict[str, Any]) -> List[str]:
        """Extract tags from learning data, deriving from content if absent."""
        tags = [t for t in learning_data.get("tags", []) if t]
        if tags:
            return tags[:10]
        text = json.dumps(learning_data, default=str).lower()
        keywords = [
            "career", "health", "finance", "relationship", "education",
            "happiness", "wealth", "growth", "risk", "mindset",
        ]
        return [kw for kw in keywords if kw in text]

    def _calculate_importance(self, learning_data: Dict[str, Any]) -> int:
        """Importance score 0-10 from explicit value or heuristics."""
        explicit = learning_data.get("importance")
        if isinstance(explicit, (int, float)):
            return max(0, min(10, int(explicit)))
        text = json.dumps(learning_data, default=str).lower()
        score = 5
        for signal in ("critical", "breakthrough", "failure", "lesson"):
            if signal in text:
                score += 1
        for signal in ("minor", "note", "remark"):
            if signal in text:
                score -= 1
        return max(0, min(10, score))

    def _match_tags(self, learning: Dict[str, Any], tags: List[str]) -> bool:
        """True if learning shares any of the requested tags."""
        learning_tags = set(learning.get("tags", []))
        return bool(learning_tags.intersection(tags))

    def _match_query(self, learning: Dict[str, Any], query: str) -> bool:
        """True if query appears in learning content or tags."""
        haystack = json.dumps(learning, default=str).lower()
        return query.lower() in haystack

    def _update_knowledge_graph(self, learning: Dict[str, Any]) -> None:
        """Link learning id to each of its tags in the knowledge graph."""
        for tag in learning.get("tags", []):
            self.knowledge_graph.setdefault(tag, set()).add(learning["id"])

    def _apply_retention_policy(self, learning: Dict[str, Any]) -> None:
        """Record a lightweight retention policy for the learning."""
        importance = learning.get("importance", 5)
        policy = "long_term" if importance >= 8 else "short_term" if importance <= 3 else "normal"
        learning["retention_policy"] = policy
        self.retention_policies[learning["id"]] = {
            "policy": policy,
            "importance": importance,
        }

    def _analyze_source_distribution(self, learnings: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count learnings by source."""
        distribution: Dict[str, int] = {}
        for learning in learnings:
            source = learning.get("source", "ai_agent")
            distribution[source] = distribution.get(source, 0) + 1
        return distribution

    def _analyze_temporal_pattern(self, learnings: List[Dict[str, Any]]) -> str:
        """Coarse temporal pattern: clustered, steady, or sparse."""
        if len(learnings) < 2:
            return "single"
        timestamps = sorted(
            datetime.fromisoformat(l["timestamp"]) for l in learnings
        )
        span_days = (timestamps[-1] - timestamps[0]).total_seconds() / 86400.0
        rate = len(learnings) / max(1.0, span_days)
        return "steady" if rate >= 0.5 else "sparse"

    def _calculate_character_relevance(
        self, learning: Dict[str, Any], character: Character
    ) -> float:
        """0.0-1.0 relevance of a learning to a character."""
        if learning.get("source") == "interview":
            return 0.9
        overlap = 0
        text = json.dumps(learning.get("data", {}), default=str).lower()
        for attr in ("happiness", "health", "smarts", "money", "career", "family"):
            if attr in text:
                overlap += 1
        return min(1.0, overlap * 0.15 + 0.1)

    def _is_relevant_to_character(
        self, learning: Dict[str, Any], character: Character
    ) -> bool:
        """True if a learning plausibly matters for this character."""
        return self._calculate_character_relevance(learning, character) >= 0.3

    def _identify_strength_patterns(
        self, learnings: List[Dict[str, Any]], character: Character
    ) -> List[str]:
        """Patterns of strength derived from the character's attributes."""
        strengths = []
        if character.smarts >= 70:
            strengths.append("High cognitive ability / learning capacity")
        if character.health >= 70:
            strengths.append("Strong physical health")
        if character.happiness >= 70:
            strengths.append("Emotionally resilient mindset")
        if character.net_worth >= 100000:
            strengths.append("Financial security and wealth building")
        relevant = [
            l for l in learnings
            if any(t in ("mindset", "growth", "wealth") for t in l.get("tags", []))
        ]
        if relevant:
            strengths.append("Applies accumulated life lessons deliberately")
        return strengths

    def _identify_improvement_opportunities(
        self, learnings: List[Dict[str, Any]], character: Character
    ) -> List[str]:
        """Areas where the character has room to grow."""
        opportunities = []
        if character.smarts < 50:
            opportunities.append("Invest in learning and skill development")
        if character.health < 50:
            opportunities.append("Prioritize health and wellness routines")
        if character.happiness < 50:
            opportunities.append("Cultivate habits that build sustainable happiness")
        if character.net_worth < 0:
            opportunities.append("Restructure finances and reduce debt")
        return opportunities

    def _analyze_decision_patterns(
        self, learnings: List[Dict[str, Any]], character: Character
    ) -> Dict[str, Any]:
        """Summarize how prior recorded decisions shaped outcomes."""
        high = [l for l in learnings if l.get("importance", 0) >= 7]
        return {
            "decisive_learnings": len(high),
            "recurring_topics": sorted(
                set(t for l in high for t in l.get("tags", []))
            )[:5],
            "balance": "balanced" if len(high) else "unknown",
        }

    def _determine_growth_trajectory(
        self, learnings: List[Dict[str, Any]], character: Character
    ) -> str:
        """Classify growth trajectory from attributes and learning history."""
        rising = (
            character.happiness > 50
            and character.smarts > 50
            and len(learnings) >= 2
        )
        if character.net_worth > 100000 and rising:
            return "accelerating"
        if rising:
            return "steady"
        if character.net_worth < 0 and character.happiness < 50:
            return "at_risk"
        return "developing"

    def _generate_character_recommendations(
        self, learnings: List[Dict[str, Any]], character: Character
    ) -> List[str]:
        """Concrete, actionable recommendations for the character."""
        recommendations = []
        trajectory = self._determine_growth_trajectory(learnings, character)
        if trajectory == "at_risk":
            recommendations.append("Address health and finances before growth")
        elif trajectory == "accelerating":
            recommendations.append("Capitalize on momentum; double down on strengths")
        else:
            recommendations.append("Build consistent habits across health, finance, and skills")
        if any(t == "health" for l in learnings for t in l.get("tags", [])):
            recommendations.append("Continue the health practices that have worked")
        if not learnings:
            recommendations.append("Record learnings regularly to unlock cross-session memory")
        return recommendations


def main() -> None:
    """CLI entry point: read JSON on stdin, write JSON on stdout.

    Protocol (used by the Rust MCP client and Go core integration):
      input:  {"operation": "store|retrieve|update|delete|create_session|end_session",
               "data": {...}, "query": str, "session_id": str, "workspace": str}
      output: {"status": "success", "result": {...}}
    """
    import sys
    import json as _json

    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
    except Exception:
        raw = ""

    request = {}
    if raw:
        try:
            request = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            request = {}

    operation = request.get("operation", "store")
    data = request.get("data", {})
    query = request.get("query")
    session_id = request.get("session_id")
    workspace = request.get("workspace", "alphazero")

    agent = MemorySystemAgent(workspace=workspace)

    if operation == "store":
        learning_id = agent.store_learning(data, session_id=session_id)
        result = {"learning_id": learning_id, "stored": True}
    elif operation == "retrieve":
        learnings = agent.retrieve_learnings(query=query)
        result = {"results": learnings, "count": len(learnings)}
    elif operation == "update":
        learning_id = data.get("learning_id")
        updates = data.get("updates", {})
        updated = agent.update_learning(learning_id, updates) if learning_id else False
        result = {"updated": updated}
    elif operation == "delete":
        learning_id = data.get("learning_id")
        deleted = agent.delete_learning(learning_id) if learning_id else False
        result = {"deleted": deleted}
    elif operation == "create_session":
        session_id = session_id or data.get("session_id", "default")
        created = agent.create_session(session_id, data.get("context", {}))
        result = {"session_id": session_id, "created": created}
    elif operation == "end_session":
        session_id = session_id or data.get("session_id", "default")
        ended = agent.end_session(session_id, data.get("insights"))
        result = {"session_id": session_id, "ended": ended}
    else:
        result = {"error": f"Unknown operation: {operation}"}

    print(_json.dumps({"status": "success", "result": result}, default=str))


if __name__ == "__main__":
    main()
