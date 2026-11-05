#!/usr/bin/env python3
"""Genesis Core — Parquet Conversion + Graph Builder (v4, vectorized)
Fast groupby-based graph construction (no row iteration).
"""
import json
import time
from pathlib import Path

import pandas as pd

DATASET_DIR = Path("/home/alieninc/dataset")
OUTPUT_DIR = Path("/home/alieninc/genesis/dataset")

CONNECTIONS_CSV = DATASET_DIR / "connections_princeton.csv.gz"
NEURONS_CSV = DATASET_DIR / "column_assignment.csv.gz"

CONNECTIONS_PARQUET = OUTPUT_DIR / "connections.parquet"
NEURONS_PARQUET = OUTPUT_DIR / "neurons.parquet"
GRAPH_SAMPLE_JSON = OUTPUT_DIR / "graph_sample.json"
STATS_JSON = OUTPUT_DIR / "stats.json"


def log(msg):
    print(msg, flush=True)


def convert_connections():
    log("[1/4] Converting connections CSV → Parquet...")
    t0 = time.time()
    df = pd.read_csv(CONNECTIONS_CSV, compression="gzip", dtype={
        "pre_root_id": "int64",
        "post_root_id": "int64",
        "neuropil": "str",
        "syn_count": "int32",
        "nt_type": "str",
    })
    df.to_parquet(CONNECTIONS_PARQUET, index=False, compression="snappy")
    log(f"    → {len(df):,} connections in {time.time()-t0:.1f}s")
    return df


def convert_neurons():
    log("[2/4] Converting neurons CSV → Parquet...")
    t0 = time.time()
    df = pd.read_csv(NEURONS_CSV, compression="gzip", dtype={
        "root_id": "int64",
        "hemisphere": "str", "type": "str", "column_id": "int32",
        "x": "float32", "y": "float32", "p": "float32", "q": "float32",
    })
    df.to_parquet(NEURONS_PARQUET, index=False, compression="snappy")
    log(f"    → {len(df):,} neurons in {time.time()-t0:.1f}s")
    return df


def build_sample_graph(connections_df, neurons_df, max_edges=60):
    """Build a compact visualization graph using vectorized groupby."""
    log(f"[3/4] Building compact visualization graph (max {max_edges} edges/n)...")
    t0 = time.time()

    c = connections_df.copy()
    # String IDs keep JSON compact-safe
    c["pre"] = c["pre_root_id"].astype(str)
    c["post"] = c["post_root_id"].astype(str)

    # Sort so we keep strongest edges
    c = c.sort_values("syn_count", ascending=False)

    # Keep at most `max_edges` rows per pre and per post neuron
    out_keep = (
        c.groupby("pre")["syn_count"]
        .rank(method="first", ascending=True)
        .le(max_edges)
    )
    in_keep = (
        c.groupby("post")["syn_count"]
        .rank(method="first", ascending=True)
        .le(max_edges)
    )
    keep = out_keep | in_keep
    c = c[keep]

    # Build per-node edge lists via groupby+apply (returns nested lists)
    def pack_out(g):
        return {
            "out": [
                {"target": str(r["post"]), "syn": int(r["syn_count"]),
                 "nt": str(r["nt_type"]), "np": str(r["neuropil"])}
                for r in g.to_dict("records")
            ]
        }

    def pack_in(g):
        return {
            "in": [
                {"source": str(r["pre"]), "syn": int(r["syn_count"]),
                 "nt": str(r["nt_type"]), "np": str(r["neuropil"])}
                for r in g.to_dict("records")
            ]
        }

    out_edges = c.groupby("pre", sort=False).apply(pack_out).to_dict()
    in_edges = c.groupby("post", sort=False).apply(pack_in).to_dict()

    # Node metadata
    neurons_df = neurons_df.copy()
    neurons_df["id"] = neurons_df["root_id"].astype(str)
    node_meta = {
        r["id"]: {
            "type": str(r["type"]),
            "hemisphere": str(r["hemisphere"]),
            "x": float(r["x"]), "y": float(r["y"]),
            "p": float(r["p"]), "q": float(r["q"]),
        }
        for r in neurons_df.to_dict("records")
    }

    node_ids = set(out_edges.keys()) | set(in_edges.keys()) | set(node_meta.keys())
    nodes = []
    for nid in node_ids:
        meta = node_meta.get(nid, {})
        nodes.append({
            "id": nid,
            **meta,
            "out": out_edges.get(nid, {}).get("out", []),
            "in": in_edges.get(nid, {}).get("in", []),
        })

    sample = {"nodes": nodes}
    with open(GRAPH_SAMPLE_JSON, "w") as f:
        json.dump(sample, f)

    log(f"    → {len(nodes):,} node records in {time.time()-t0:.1f}s")
    return sample


def compute_stats(connections_df, neurons_df, sample):
    log("[4/4] Computing statistics...")
    c = connections_df
    n = neurons_df
    stats = {
        "total_neurons": int(len(n)),
        "total_connections": int(len(c)),
        "total_synapses": int(c["syn_count"].sum()),
        "unique_neuropils": sorted(c["neuropil"].unique().tolist()),
        "neurotransmitters": sorted(c["nt_type"].unique().tolist()),
        "neuron_types": sorted(n["type"].unique().tolist()),
        "hemispheres": sorted(n["hemisphere"].unique().tolist()),
        "neuron_type_counts": n["type"].value_counts().to_dict(),
        "neuropil_counts": c["neuropil"].value_counts().to_dict(),
        "nt_type_counts": c["nt_type"].value_counts().to_dict(),
        "avg_synapse_count": float(c["syn_count"].mean()),
        "max_synapse_count": int(c["syn_count"].max()),
        "viz_neuron_count": len(sample["nodes"]),
    }
    with open(STATS_JSON, "w") as f:
        json.dump(stats, f, indent=2)
    log("    → Stats written")
    return stats


def main():
    log("=" * 60)
    log("GENESIS CORE — Parquet + Graph Builder (v4)")
    log("=" * 60)
    t_start = time.time()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    connections_df = convert_connections()
    neurons_df = convert_neurons()
    sample = build_sample_graph(connections_df, neurons_df)
    stats = compute_stats(connections_df, neurons_df, sample)

    log("=" * 60)
    log(f"COMPLETE in {time.time()-t_start:.1f}s")
    log(f"  Neurons:      {stats['total_neurons']:>10,}")
    log(f"  Connections:  {stats['total_connections']:>10,}")
    log(f"  Synapses:     {stats['total_synapses']:>10,}")
    log(f"  Neuropils:    {len(stats['unique_neuropils']):>10}")
    log(f"  NTs:          {stats['neurotransmitters']}")
    log("=" * 60)


if __name__ == "__main__":
    main()
