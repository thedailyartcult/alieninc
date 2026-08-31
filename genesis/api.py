#!/usr/bin/env python3
"""Genesis Core — FastAPI Backend
Serves the FlyWire FAFB connectome dataset over HTTP for the Genesis
Connectome Explorer and public API.

Run:  uvicorn api:app --host 127.0.0.1 --port 8001
"""
import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

BASE = Path("/home/alieninc/genesis/dataset")

app = FastAPI(title="Genesis Core API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-load large artifacts
_stats = None
_explorer = None
_conn = None
_neurons = None


def get_stats():
    global _stats
    if _stats is None:
        with open(BASE / "stats.json") as f:
            _stats = json.load(f)
    return _stats


def get_explorer():
    global _explorer
    if _explorer is None:
        with open(BASE / "explorer.json") as f:
            _explorer = json.load(f)
    return _explorer


def get_conn():
    global _conn
    if _conn is None:
        _conn = pd.read_parquet(BASE / "connections.parquet")
    return _conn


def get_neurons():
    global _neurons
    if _neurons is None:
        _neurons = pd.read_parquet(BASE / "neurons.parquet")
    return _neurons


@app.get("/api/genesis/stats")
def stats():
    return get_stats()


@app.get("/api/genesis/explorer")
def explorer():
    return get_explorer()


@app.get("/api/genesis/neuropils")
def neuropils():
    s = get_stats()
    return {"neuropils": s["unique_neuropils"], "counts": s["neuropil_counts"]}


@app.get("/api/genesis/nt_types")
def nt_types():
    s = get_stats()
    return {"neurotransmitters": s["neurotransmitters"], "counts": s["nt_type_counts"]}


@app.get("/api/genesis/neuron_types")
def neuron_types():
    s = get_stats()
    return {"types": s["neuron_types"], "counts": s["neuron_type_counts"]}


@app.get("/api/genesis/neurons")
def neurons(
    type: Optional[str] = Query(None),
    hemisphere: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
):
    df = get_neurons()
    if type:
        df = df[df["type"] == type]
    if hemisphere:
        df = df[df["hemisphere"] == hemisphere]
    df = df.head(limit)
    records = df.to_dict("records")
    return {"count": len(records), "neurons": records}


@app.get("/api/genesis/neuron/{neuron_id}")
def neuron(neuron_id: str, limit: int = Query(100, ge=1, le=2000)):
    """Return a single neuron plus its strongest outgoing/incoming connections."""
    try:
        nid = int(neuron_id)
    except ValueError:
        return JSONResponse({"error": "invalid neuron id"}, status_code=400)

    neurons_df = get_neurons()
    n = neurons_df[neurons_df["root_id"] == nid]
    if n.empty:
        return JSONResponse({"error": "neuron not found"}, status_code=404)
    node = n.iloc[0].to_dict()
    node["root_id"] = str(node["root_id"])

    conn = get_conn()
    out = conn[conn["pre_root_id"] == nid].sort_values("syn_count", ascending=False).head(limit)
    inc = conn[conn["post_root_id"] == nid].sort_values("syn_count", ascending=False).head(limit)

    out_records = [
        {
            "target": str(r["post_root_id"]),
            "syn_count": int(r["syn_count"]),
            "nt_type": str(r["nt_type"]),
            "neuropil": str(r["neuropil"]),
        }
        for r in out.to_dict("records")
    ]
    in_records = [
        {
            "source": str(r["pre_root_id"]),
            "syn_count": int(r["syn_count"]),
            "nt_type": str(r["nt_type"]),
            "neuropil": str(r["neuropil"]),
        }
        for r in inc.to_dict("records")
    ]

    return {
        "neuron": node,
        "outgoing": out_records,
        "incoming": in_records,
        "out_count": int(len(out_records)),
        "in_count": int(len(in_records)),
    }


@app.get("/api/genesis/search")
def search(q: str, limit: int = Query(20, ge=1, le=100)):
    """Search neurons by type (e.g. T4a, Mi9, L2)."""
    df = get_neurons()
    out = df[df["type"].str.contains(q, case=False, na=False)].head(limit)
    records = []
    for r in out.to_dict("records"):
        r = dict(r)
        r["root_id"] = str(r["root_id"])
        records.append(r)
    return {"count": len(records), "neurons": records}


@app.get("/api/genesis/health")
def health():
    return {"status": "ok", "genesis": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
