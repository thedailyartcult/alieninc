import networkx as nx
from typing import Any
from store import store
from models import Event


def build_causal_graph(events: list[Event] | None = None) -> nx.DiGraph:
    events = events or store.get_events()
    G = nx.DiGraph()

    for e in events:
        G.add_node(e.id, **_node_attrs(e))

    for i, e in enumerate(events):
        for prev in events[:i]:
            if _is_causal(prev, e):
                G.add_edge(prev.id, e.id, weight=_edge_weight(prev, e), confidence=_confidence(prev, e))

    store.causal_graph = G
    return G


def get_graph() -> dict:
    G = store.causal_graph
    if G is None:
        G = build_causal_graph()
    return {
        "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
        "edges": [{"source": u, "target": v, **G.edges[u, v]} for u, v in G.edges],
    }


def find_root_causes(target_id: str, depth: int = 10) -> list[dict]:
    G = store.causal_graph or build_causal_graph()
    if target_id not in G:
        return []

    ancestors = nx.ancestors(G, target_id)
    roots = [n for n in ancestors if G.in_degree(n) == 0]

    ranked = []
    for r in roots:
        paths = list(nx.all_simple_paths(G, r, target_id, cutoff=depth))
        score = len(paths) * (1.0 / max(1, nx.shortest_path_length(G, r, target_id)))
        ranked.append({"node_id": r, "score": round(score, 4), "paths_found": len(paths), **G.nodes[r]})

    return sorted(ranked, key=lambda x: x["score"], reverse=True)


def counterfactual(event_ids: list[str], intervention: str = "remove") -> dict:
    G = store.causal_graph or build_causal_graph()
    G2 = G.copy()

    removed = []
    for eid in event_ids:
        if eid in G2:
            G2.remove_node(eid)
            removed.append(eid)

    affected = set()
    for eid in removed:
        if eid in G:
            affected.update(nx.descendants(G, eid))

    return {
        "intervention": intervention,
        "events_removed": removed,
        "downstream_affected": len(affected),
        "affected_nodes": list(affected),
        "graph_intact": nx.is_directed_acyclic_graph(G2),
    }


def _node_attrs(e: Event) -> dict:
    return {"actor": e.actor, "action": e.action, "target": e.target, "timestamp": e.timestamp.isoformat()}


def _is_causal(prev: Event, curr: Event) -> bool:
    if prev.actor == curr.actor:
        return True
    if prev.target and prev.target == curr.actor:
        return True
    if prev.target and prev.target == curr.target:
        return True
    return False


def _edge_weight(prev: Event, curr: Event) -> float:
    if prev.actor == curr.actor:
        return 0.9
    if prev.target == curr.actor:
        return 0.7
    return 0.5


def _confidence(prev: Event, curr: Event) -> float:
    return 0.8 if prev.actor == curr.actor else 0.6
