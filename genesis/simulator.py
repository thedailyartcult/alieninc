#!/usr/bin/env python3
"""Genesis Core — Leaky Integrate-and-Fire (LIF) SNN Simulator

Implements the plain-text bootstrap runtime from mission.html:

    tau_m * (dV_i / dt) = -(V_i - V_rest) + R * sum_j W_ij S_j(t)

Loads the distilled sparse SNN adjacency tables (pre/post/weight) and
simulates spiking activity. Outputs membrane-potential traces, spike rasters,
and information-flow statistics suitable for the WebAssembly terminal.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("/home/alieninc/genesis")
OUTPUT = BASE / "output"
SYN_DEFAULT = OUTPUT / "snn_adjacency.csv"

# Physical membrane parameters (standard LIF, ms / mV)
TAU_M = 10.0       # membrane time constant (ms)
V_REST = -70.0     # resting potential (mV)
V_THRESH = -55.0   # firing threshold (mV)
V_RESET = -75.0    # reset potential (mV)
R_M = 1.0          # membrane resistance
DT = 1.0           # integration step (ms)

NT_COLORS = {
    "ACH": "#4ea2fd",
    "GABA": "#ff6b6b",
    "GLUT": "#ffd400",
    "DA": "#c084fc",
    "SER": "#34d399",
    "OCT": "#fb923c",
}


def log(msg):
    print(msg, flush=True)


def load_synapses(path, max_edges=None):
    df = pd.read_csv(path)
    if max_edges is not None:
        df = df.head(max_edges)
    return df


def simulate(df, sim_time=200.0, pop_size=None, seed=42):
    """Run a LIF simulation over the distilled graph.

    Returns dict of arrays for downstream plotting / WASM."
    """
    t0 = time.time()
    n_edges = len(df)
    pre = df["pre"].to_numpy(dtype=np.int64)
    post = df["post"].to_numpy(dtype=np.int64)
    w = df["weight"].to_numpy(dtype=np.float32)

    n_neurons = int(max(n_edges and int(pre.max()), int(post.max()))) + 1
    if pop_size is not None:
        n_neurons = min(n_neurons, pop_size)
        keep = (pre < pop_size) & (post < pop_size)
        pre, post, w = pre[keep], post[keep], w[keep]

    n_steps = int(sim_time / DT)

    V = np.full(n_neurons, V_REST, dtype=np.float32)
    spikes = np.zeros(n_neurons, dtype=np.float32)
    raster = []
    rng = np.random.default_rng(seed)
    firing_counts = np.zeros(n_neurons, dtype=np.int32)

    # build pre-synaptic adjacency using argsort (memory-light)
    order = np.argsort(post)
    post_sorted = post[order]
    pre_sorted = pre[order]
    w_sorted = w[order]
    # unique start indices per post neuron
    starts = {}
    uniq, counts = np.unique(post_sorted, return_counts=True)
    scan = 0
    for u, c in zip(uniq, counts):
        starts[int(u)] = (scan, scan + c)
        scan += c

    log(f"  sim: {n_neurons:,} neurons, {len(pre):,} edges, {n_steps} steps")
    for t in range(n_steps):
        # LIF update via discrete approximation:
        #   dV = (dt/tau_m) * (-(V - V_rest) + R * I_syn)
        I_syn = np.zeros(n_neurons, dtype=np.float32)

        # --- integration over edges: pre[e] fired -> add w[e] to post[e] ---
        fired_pre = np.nonzero(spikes)[0]
        if len(fired_pre):
            mask = np.isin(pre_sorted, fired_pre)
            if mask.any():
                np.add.at(I_syn, post_sorted[mask], w_sorted[mask])

        # membrane dynamics
        V = V + (DT / TAU_M) * (-(V - V_REST) + R_M * I_syn)

        # Poisson input drive to keep network alive
        noise = rng.random(n_neurons) < 0.004
        V[noise] += 14.0

        # threshold + reset
        fired = V >= V_THRESH
        spikes = fired.astype(np.float32)
        V[fired] = V_RESET

        if fired.any():
            firing_counts += fired.astype(np.int32)
            idx = np.nonzero(fired)[0]
            raster.append((t, [int(i) for i in idx[:5000]]))  # cap logging

    log(f"  done in {time.time()-t0:.2f}s")
    return {
        "n_neurons": n_neurons,
        "n_steps": n_steps,
        "firing_counts": firing_counts,
        "total_spikes": int(firing_counts.sum()),
        "active_neurons": int((firing_counts > 0).sum()),
        "mean_rate_hz": float(firing_counts.sum() / (sim_time / 1000.0) / n_neurons),
        "raster": raster,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--syn", default=str(SYN_DEFAULT))
    ap.add_argument("--time", type=float, default=100.0)
    ap.add_argument("--pop", type=int, default=None)
    ap.add_argument("--max-edges", type=int, default=None)
    ap.add_argument("--output", default=str(OUTPUT / "simulation_results.json"))
    args = ap.parse_args()

    log("=" * 60)
    log("GENESIS CORE — LIF SNN Simulator")
    log("=" * 60)
    t_start = time.time()

    df = load_synapses(args.syn, args.max_edges)
    log(f"  loaded {len(df):,} synaptic edges")

    res = simulate(df, sim_time=args.time, pop_size=args.pop)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": {
            "tau_m": TAU_M, "v_rest": V_REST, "v_thresh": V_THRESH,
            "v_reset": V_RESET, "dt": DT,
            "sim_time_ms": args.time,
        },
        "stats": {
            "n_neurons": res["n_neurons"],
            "total_spikes": res["total_spikes"],
            "active_neurons": res["active_neurons"],
            "mean_rate_hz": res["mean_rate_hz"],
        },
        "raster": res["raster"][:200],
    }
    with open(out, "w") as f:
        json.dump(payload, f)

    log("=" * 60)
    log(f"  Neurons       : {res['n_neurons']:,}")
    log(f"  Total spikes  : {res['total_spikes']:,}")
    log(f"  Active neurons: {res['active_neurons']:,}")
    log(f"  Mean rate     : {res['mean_rate_hz']:.2f} Hz")
    log(f"  Results       : {out}")
    log(f"COMPLETE in {time.time()-t_start:.1f}s")
    log("=" * 60)


if __name__ == "__main__":
    main()
