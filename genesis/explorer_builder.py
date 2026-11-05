#!/usr/bin/env python3
"""Genesis Core — Compact Explorer Graph Builder (v2)
For the 3D browser explorer, keep edges ONLY where BOTH endpoints are hub
neurons, and cap the total edge count to keep the payload renderable.
Produces a small, gzippable JSON.
"""
import json
import time
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path("/home/alieninc/genesis/dataset")
CONNECTIONS = OUTPUT_DIR / "connections.parquet"
NEURONS = OUTPUT_DIR / "neurons.parquet"
EXPLORER_JSON = OUTPUT_DIR / "explorer.json"

TOP_HUBS = 2500      # hub neurons to include
MAX_EDGES_TOTAL = 120000  # overall edge budget for rendering


def log(msg):
    print(msg, flush=True)


def main():
    log("=" * 60)
    log("GENESIS CORE — Explorer Graph Builder (v2)")
    log("=" * 60)
    t0 = time.time()

    log("[1/4] Loading Parquet...")
    conn = pd.read_parquet(CONNECTIONS)
    neurons = pd.read_parquet(NEURONS)
    conn = conn.copy()
    conn["pre"] = conn["pre_root_id"].astype(str)
    conn["post"] = conn["post_root_id"].astype(str)
    neurons = neurons.copy()
    neurons["id"] = neurons["root_id"].astype(str)

    log("[2/4] Node metadata index...")
    node_index = {
        r["id"]: {
            "t": str(r["type"]), "h": str(r["hemisphere"]),
            "x": float(r["x"]), "y": float(r["y"]),
            "p": float(r["p"]), "q": float(r["q"]),
        }
        for r in neurons.to_dict("records")
    }

    log("[3/4] Hubs by degree...")
    out_deg = conn.groupby("pre")["syn_count"].sum()
    in_deg = conn.groupby("post")["syn_count"].sum()
    degree = out_deg.add(in_deg, fill_value=0).sort_values(ascending=False)
    hubs = list(degree.index[:TOP_HUBS])
    hub_set = set(hubs)

    log("[4/4] Edges between hubs (budget-limited)...")
    between = conn[conn["pre"].isin(hub_set) & conn["post"].isin(hub_set)]
    between = between.sort_values("syn_count", ascending=False)
    n_edges = min(len(between), MAX_EDGES_TOTAL)
    between = between.head(n_edges)

    edges = [
        [r["pre"], r["post"], int(r["syn_count"]), str(r["nt_type"]), str(r["neuropil"])]
        for r in between.to_dict("records")
    ]

    nodes = []
    for nid in hubs:
        meta = node_index.get(nid, {})
        nodes.append({
            "id": nid, "t": meta.get("t", "?"), "h": meta.get("h", "?"),
            "x": meta.get("x", 0.0), "y": meta.get("y", 0.0),
            "p": meta.get("p", 0.0), "q": meta.get("q", 0.0),
        })

    payload = {
        "meta": {
            "total_neurons": int(len(neurons)),
            "total_connections": int(len(conn)),
            "total_synapses": int(conn["syn_count"].sum()),
            "hubs": len(hubs),
            "edges": len(edges),
            "neuropils": int(conn["neuropil"].nunique()),
            "neurotransmitters": sorted(conn["nt_type"].unique().tolist()),
        },
        "nodes": nodes,
        "edges": edges,
    }

    with open(EXPLORER_JSON, "w") as f:
        json.dump(payload, f)
    size_mb = EXPLORER_JSON.stat().st_size / 1e6
    log(f"    → {len(nodes):,} nodes, {len(edges):,} edges, {size_mb:.1f} MB in {time.time()-t0:.1f}s")
    log("=" * 60)


if __name__ == "__main__":
    main()
