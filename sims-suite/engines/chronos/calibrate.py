"""Corpus-wide calibration — tune Chronos coefficients against CDB90 ground truth.

Runs a sample of the historical battle corpus through the engine and reports
aggregate casualty statistics vs the recorded history. Iterate coefficients
in engine.py until aggregates converge, then freeze them.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engines.chronos.engine import resolve_battle          # noqa: E402
from engines.chronos.loader import DEFAULT_DB, load_battle  # noqa: E402


def corpus_ground_truth(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """WITH pairs AS (
                 SELECT isqno,
                   SUM(CASE WHEN side=1 THEN CAST(casualties AS REAL)/NULLIF(strength,0) END) af,
                   SUM(CASE WHEN side=0 THEN CAST(casualties AS REAL)/NULLIF(strength,0) END) df
                 FROM chronos_belligerents WHERE strength>100 AND casualties IS NOT NULL
                 GROUP BY isqno)
               SELECT af, df FROM pairs
               WHERE af IS NOT NULL AND df > 0 AND af < 0.9 AND df < 0.9"""
        ).fetchall()
    finally:
        conn.close()
    att = [r[0] for r in rows]
    dfd = [r[1] for r in rows]
    n = len(rows)
    return {
        "n": n,
        "attacker_mean": sum(att) / n,
        "defender_mean": sum(dfd) / n,
        "attacker_worse_pct": sum(1 for a, d in zip(att, dfd) if a > d) / n,
    }


def simulate_corpus(sample: int = 200, seed: int = 7, db_path: Path = DEFAULT_DB) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        isqnos = [r[0] for r in conn.execute(
            """SELECT b.isqno FROM chronos_battles b
               JOIN chronos_belligerents bl ON bl.isqno = b.isqno
               GROUP BY b.isqno HAVING COUNT(*) = 2
                 AND MAX(bl.strength) > 100
                 AND MIN(bl.casualties) >= 0 AND MAX(bl.casualties) IS NOT NULL"""
        ).fetchall()]
    finally:
        conn.close()
    rng = random.Random(seed)
    if sample < len(isqnos):
        isqnos = rng.sample(isqnos, sample)

    winner_hits = total = 0
    att_fracs: list[float] = []
    dfd_fracs: list[float] = []
    skipped = 0
    for isq in isqnos:
        battle = load_battle(isq, db_path)
        if not battle or battle.attacker.strength <= 100 or battle.defender.strength <= 100:
            skipped += 1
            continue
        actual = battle.actual_winner
        outcome = resolve_battle(battle, rng.randint(0, 2**31 - 1))
        predicted = outcome.winner
        if actual != "stalemate":
            total += 1
            if predicted == actual or (predicted == "stalemate" and False):
                winner_hits += 1
        af = outcome.attacker_casualties / battle.attacker.strength
        df = outcome.defender_casualties / battle.defender.strength
        if af < 0.9 and df < 0.9:
            att_fracs.append(af)
            dfd_fracs.append(df)

    n = max(len(att_fracs), 1)
    return {
        "battles_run": len(isqnos),
        "skipped": skipped,
        "winner_accuracy": round(winner_hits / max(total, 1), 4),
        "scored": total,
        "sim_attacker_mean": round(sum(att_fracs) / n, 4),
        "sim_defender_mean": round(sum(dfd_fracs) / n, 4),
        "sim_attacker_worse_pct": round(
            sum(1 for a, d in zip(att_fracs, dfd_fracs) if a > d) / n, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--truth-only", action="store_true")
    args = ap.parse_args()

    truth = corpus_ground_truth(Path(args.db))
    print("GROUND TRUTH (CDB90):", truth)
    if not args.truth_only:
        print("ENGINE:", simulate_corpus(args.sample, db_path=Path(args.db)))


if __name__ == "__main__":
    main()
