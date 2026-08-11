import uuid
from collections import Counter
from typing import Any
from store import store
from models import Event
import etiology


def infer_purposes(actor_scope: list[str] | None = None) -> list[dict]:
    events = store.get_events()
    if actor_scope:
        events = [e for e in events if e.actor in actor_scope]

    by_actor: dict[str, list[Event]] = {}
    for e in events:
        by_actor.setdefault(e.actor, []).append(e)

    purposes = []
    for actor, actor_events in by_actor.items():
        goal_hints = [e.goal_hint for e in actor_events if e.goal_hint]
        action_counts = Counter(e.action for e in actor_events)
        target_counts = Counter(e.target for e in actor_events if e.target)

        inferred_goal = goal_hints[0] if goal_hints else f"{actor}_primary_objective"

        purpose = {
            "id": str(uuid.uuid4())[:8],
            "actor": actor,
            "inferred_goal": inferred_goal,
            "confidence": min(0.95, 0.5 + len(actor_events) * 0.05),
            "action_patterns": dict(action_counts.most_common(5)),
            "target_focus": dict(target_counts.most_common(3)),
            "evidence_count": len(actor_events),
        }
        purposes.append(purpose)
        store.purposes[purpose["id"]] = purpose

    return purposes


def get_purposes() -> list[dict]:
    return list(store.purposes.values())


def project_trajectory(purpose_ids: list[str] | None = None, horizon: int = 10) -> list[dict]:
    purposes = list(store.purposes.values())
    if purpose_ids:
        purposes = [p for p in purposes if p["id"] in purpose_ids]

    trajectories = []
    for p in purposes:
        actor = p["actor"]
        events = [e for e in store.get_events() if e.actor == actor]

        if not events:
            continue

        states = []
        for i in range(1, horizon + 1):
            momentum = p["confidence"] * (1 - 0.02 * i)
            state = {
                "step": i,
                "projected_action": _predict_next_action(events, i),
                "confidence": round(max(0.1, momentum), 3),
                "actor": actor,
            }
            states.append(state)

        traj = {
            "id": str(uuid.uuid4())[:8],
            "purpose_id": p["id"],
            "actor": actor,
            "horizon": horizon,
            "trajectory": states,
        }
        trajectories.append(traj)
        store.trajectories[traj["id"]] = traj

    return trajectories


def find_leverage_points(trajectory_id: str | None, objective: str) -> list[dict]:
    G = etiology.build_causal_graph()
    trajectories = list(store.trajectories.values())
    if trajectory_id:
        trajectories = [t for t in trajectories if t["id"] == trajectory_id]

    points = []
    for node in G.nodes:
        in_deg = G.in_degree(node)
        out_deg = G.out_degree(node)
        betweenness = nx.betweenness_centrality(G).get(node, 0)

        score = betweenness * 2 + out_deg * 0.3 + (1.0 / max(1, in_deg)) * 0.5
        points.append({
            "node_id": node,
            "score": round(score, 4),
            "betweenness": round(betweenness, 4),
            "in_degree": in_deg,
            "out_degree": out_deg,
            "objective": objective,
            **G.nodes[node],
        })

    return sorted(points, key=lambda x: x["score"], reverse=True)[:20]


def _predict_next_action(events: list[Event], step: int) -> str:
    if not events:
        return "unknown"
    actions = [e.action for e in events]
    idx = (len(actions) - 1 + step) % len(actions)
    return actions[idx]


import networkx as nx
