"""Kriegspiel self-learning research layer.

The simulation engine was producing real outcomes (doctrine × terrain × winner)
but never *learning* from them. This module closes that loop:

  1. ``DoctrinePerformanceTracker`` observes every branched scenario and
     accumulates win-rate statistics per (doctrine, terrain) and per
     (doctrine, opposing_doctrine) pairing.
  2. ``distill_findings()`` turns accumulated statistics into human-readable
     research findings ("In mountain terrain, Maneuver doctrine loses 67% of
     engagements against Defensive").
  3. ``self_improve()`` writes per-(doctrine, terrain) parameter overrides
     into ``engines.kriegspiel.combat._TERRAIN_PARAM_OVERRIDES`` based on
     what the engine has learned — underperforming doctrines nudge their
     aggression/risk/supply_focus/morale_drain toward the profile of
     doctrines that win *in that terrain*. The base doctrine table is never
     mutated, so a lesson earned in one theater stays scoped to it.
     Every change is clamped, logged, and reversible (the prior values are
     recorded in the research log).
  4. ``ResearchLog`` is an append-only JSONL dossier documenting every
     finding and every parameter change with timestamps, so progress is
     auditable.

The tracker is a process-wide singleton (``get_tracker()``) so the background
simulation loop and the API endpoints see the same state. State is persisted
to ``analytics_data/research_state.json`` so a service restart does not lose
learned parameters; the JSONL dossier is append-only and never rewritten.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from engines.kriegspiel.models import BATTLEFIELDS, Doctrine, TerrainType
from sims_core.stats import two_proportion_z, benjamini_hochberg


# Resolve the analytics directory relative to this file so the layer works
# regardless of the gateway's cwd. Created lazily on first write.
_ANALYTICS_DIR = Path(__file__).resolve().parent / "analytics_data"
_STATE_PATH = _ANALYTICS_DIR / "research_state.json"
_LOG_PATH = _ANALYTICS_DIR / "research_log.jsonl"
# Rotate the JSONL dossier once it exceeds this size so it cannot grow
# unbounded; archives are kept forever under analytics_data/archives/.
_MAX_LOG_BYTES = 64 * 1024 * 1024

# Self-improvement thresholds. Below 30 samples per (doctrine, terrain) cell
# we don't trust the win-rate enough to rewrite parameters.
_MIN_SAMPLES = 30
_UNDERPERFORM = 0.35      # win rate below this → nudge toward the terrain winner
_OVERPERFORM = 0.65       # win rate above this → log as a strength, no change
_NUDGE = 0.05             # max parameter move per self-improve step (5%)
_PARAM_FLOOR = 0.10
_PARAM_CEIL = 1.00
# Run self_improve() every N observations (batches), not every batch — keeps
# the parameter set stable long enough to gather fresh evidence.
_SELF_IMPROVE_EVERY = 20
# Multiple-testing discipline (MatrAIx-style): every candidate (doctrine,
# terrain, field) adjustment is a hypothesis. Before any parameter rewrite we
# two-proportion-test the cell's win rate against the terrain's strongest
# doctrine, then apply Benjamini-Hochberg FDR control across ALL candidates in
# this step. Only hypotheses that survive the gate move parameters — this stops
# the layer from "learning" noise when dozens of cells are tested at once.
_SELF_IMPROVE_FDR = 0.10


# Battlefield name → TerrainType string. Built once from the canonical list.
_BF_TERRAIN: dict[str, str] = {
    bf.name: bf.terrain.value for bf in BATTLEFIELDS
}


@dataclass
class Cell:
    """One (doctrine, terrain) performance cell."""

    wins: int = 0
    losses: int = 0
    stalemates: int = 0
    total: int = 0
    casualties_when_winning: list[float] = field(default_factory=list)
    decisive_wins: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total else 0.0

    @property
    def avg_casualties_winning(self) -> float:
        return (sum(self.casualties_when_winning) / len(self.casualties_when_winning)
                if self.casualties_when_winning else 0.0)


@dataclass
class Finding:
    """One distilled research finding."""

    ts: float
    kind: str               # "terrain_doctrine", "matchup", "parameter_change", "milestone"
    text: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParamChange:
    """One self-improvement parameter rewrite."""

    ts: float
    doctrine: str
    terrain: str
    field: str              # "aggression" | "risk" | "supply_focus" | "morale_drain"
    before: float
    after: float
    win_rate: float
    rationale: str
    # Statistical evidence behind the change (MatrAIx-style discipline).
    p_value: float = 0.0           # two-proportion z-test vs terrain strongest
    fdr_gate: float = 0.0          # BH critical value at this step
    survived_bh: bool = True


class ResearchLog:
    """Append-only JSONL dossier of findings and parameter changes."""

    def __init__(self, path: Path = _LOG_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._count = 0
        self._ensure_dir()
        self._count = self._count_existing()

    def _ensure_dir(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _count_existing(self) -> int:
        if not self._path.exists():
            return 0
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return sum(1 for _ in fh)
        except OSError:
            return 0

    def _rotate_if_needed(self) -> None:
        """Gzip-archive the log when it exceeds _MAX_LOG_BYTES, then start a
        fresh one. Nothing is ever deleted — the full dossier history stays
        in analytics_data/archives/, only active-file size stays bounded.
        ``_count`` is intentionally left cumulative across rotations."""
        try:
            if not self._path.exists() or self._path.stat().st_size <= _MAX_LOG_BYTES:
                return
            stamp = time.strftime("%Y%m%d-%H%M%S")
            archive_dir = self._path.parent / "archives"
            archive_dir.mkdir(exist_ok=True)
            dest = archive_dir / f"{self._path.name}-{stamp}.gz"
            with open(self._path, "rb") as src, gzip.open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            self._path.unlink()
        except OSError:
            pass

    def append(self, entry: dict[str, Any]) -> None:
        """Append one entry to the JSONL log. Failures are swallowed — the
        dossier is valuable but must never break the simulation loop."""
        with self._lock:
            try:
                self._ensure_dir()
                self._rotate_if_needed()
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, default=str) + "\n")
                self._count += 1
            except OSError:
                pass

    def recent(self, k: int = 50) -> list[dict[str, Any]]:
        """Return the k most recent log entries (newest last)."""
        if not self._path.exists():
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            return []
        return [json.loads(ln) for ln in lines[-k:] if ln.strip()]

    @property
    def count(self) -> int:
        return self._count


class DoctrinePerformanceTracker:
    """Process-wide tracker that observes scenario results, distills
    findings, and self-improves doctrine parameters.

    A singleton is exposed via ``get_tracker()`` so the background loop and
    the API endpoints share state. State persists to ``research_state.json``
    so a service restart resumes with learned parameters intact.
    """

    def __init__(self,
                 state_path: Optional[Path] = None,
                 log_path: Optional[Path] = None) -> None:
        self._state_path = state_path or _STATE_PATH
        self._log_path = log_path or _LOG_PATH
        self._lock = threading.RLock()
        self._cells: dict[tuple[str, str], Cell] = defaultdict(Cell)
        # Per (doctrine, opposing_doctrine) win tally — for matchup findings.
        self._matchups: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: {"wins": 0, "total": 0}
        )
        self._batches_observed = 0
        self._scenarios_observed = 0
        self._findings_emitted = 0
        self._param_changes: list[ParamChange] = []
        # How many times each doctrine has had any parameter adjusted.
        self._adjustments_per_doctrine: dict[str, int] = defaultdict(int)
        # History of multiple-testing gates (MatrAIx-style audit trail).
        self._bh_gates: list[dict[str, Any]] = []
        self._log = ResearchLog(self._log_path)
        self._last_self_improve_ts = 0.0
        self._last_finding_ts = 0.0
        self._load_state()

    # ------------------------------------------------------------------ observe
    def observe(self, report: Any) -> None:
        """Consume one ``ScenarioReport``. Thread-safe.

        ``report.branches`` is a list of ``BattleOutcome``. Each branch's
        red/blue doctrine must have been populated by ``scenarios.py`` (we
        added ``red_doctrine``/``blue_doctrine`` to ``BattleOutcome`` for
        exactly this purpose). Terrain is derived from the battlefield name.
        """
        with self._lock:
            terrain = _BF_TERRAIN.get(report.battlefield_name, "open")
            branches = getattr(report, "branches", []) or []
            for b in branches:
                red_d = getattr(b, "red_doctrine", "") or ""
                blue_d = getattr(b, "blue_doctrine", "") or ""
                if not red_d or not blue_d:
                    # Older report without doctrine tags — skip gracefully.
                    continue
                winner = b.winner
                # Red's cell (terrain, red doctrine) — red is the attacker reference.
                self._observe_cell(red_d, terrain, winner, "red", b)
                # Blue's cell.
                self._observe_cell(blue_d, terrain, winner, "blue", b)
                # Matchup tally.
                mu = self._matchups[(red_d, blue_d)]
                mu["total"] += 1
                if winner == "red":
                    mu["wins"] += 1
            self._batches_observed += 1
            self._scenarios_observed += len(branches)
            # Distill findings periodically — every batch is too noisy; we
            # emit when there's enough new evidence (≥ _MIN_SAMPLES in a cell
            # that didn't have a finding yet, or a notable shift).
            self._maybe_distill()
            # Self-improve on a cadence so parameters stabilize between steps.
            if self._batches_observed % _SELF_IMPROVE_EVERY == 0:
                self.self_improve()
            self._save_state()

    def _observe_cell(self, doctrine: str, terrain: str, winner: str,
                      side: str, branch: Any) -> None:
        cell = self._cells[(doctrine, terrain)]
        cell.total += 1
        if winner == side:
            cell.wins += 1
            cell.casualties_when_winning.append(
                getattr(branch, f"{side}_casualties_pct", 0.0)
            )
            if len(cell.casualties_when_winning) > 200:
                # Cap memory; keep the most recent 200.
                cell.casualties_when_winning = cell.casualties_when_winning[-200:]
            if getattr(branch, "decisive", False):
                cell.decisive_wins += 1
        elif winner == "stalemate":
            cell.stalemates += 1
        else:
            cell.losses += 1

    # --------------------------------------------------------------- distill
    def _maybe_distill(self) -> None:
        """Emit findings for cells that have crossed the evidence threshold
        and haven't been reported yet, plus notable matchup asymmetries."""
        now = time.time()
        emitted_here = 0
        for (doctrine, terrain), cell in self._cells.items():
            if cell.total < _MIN_SAMPLES:
                continue
            # Emit a finding the first time a cell becomes significant, and
            # again whenever its win rate crosses an interesting boundary.
            wr = cell.win_rate
            if wr < _UNDERPERFORM:
                kind = "terrain_doctrine_weak"
                text = (f"In {terrain} terrain, {doctrine} doctrine wins only "
                        f"{wr:.0%} of engagements ({cell.wins}/{cell.total}). "
                        f"Avg casualties when winning: {cell.avg_casualties_winning:.1f}%.")
                if self._emit_finding(now, kind, text, {
                    "doctrine": doctrine, "terrain": terrain,
                    "win_rate": round(wr, 4), "samples": cell.total,
                }):
                    emitted_here += 1
            elif wr > _OVERPERFORM:
                kind = "terrain_doctrine_strong"
                text = (f"In {terrain} terrain, {doctrine} doctrine wins {wr:.0%} "
                        f"of engagements ({cell.wins}/{cell.total}) — a strength.")
                if self._emit_finding(now, kind, text, {
                    "doctrine": doctrine, "terrain": terrain,
                    "win_rate": round(wr, 4), "samples": cell.total,
                }):
                    emitted_here += 1
        # Notable matchup asymmetries (≥30 samples, lopsided).
        for (red_d, blue_d), mu in self._matchups.items():
            if mu["total"] < _MIN_SAMPLES:
                continue
            wr = mu["wins"] / mu["total"]
            if wr <= 0.25 or wr >= 0.75:
                text = (f"Matchup {red_d} vs {blue_d}: red wins {wr:.0%} "
                        f"({mu['wins']}/{mu['total']}).")
                if self._emit_finding(now, "matchup_asymmetry", text, {
                    "red": red_d, "blue": blue_d,
                    "red_win_rate": round(wr, 4), "samples": mu["total"],
                }):
                    emitted_here += 1
        if emitted_here:
            self._last_finding_ts = now

    def _emit_finding(self, ts: float, kind: str, text: str,
                      evidence: dict[str, Any]) -> bool:
        """Emit one finding. Returns True if it was newly logged.

        De-duplicates by (kind, doctrine, terrain) within a 1-hour window so
        the log doesn't flood with the same finding every batch.
        """
        key = (kind, evidence.get("doctrine", ""), evidence.get("terrain", ""),
               evidence.get("red", ""), evidence.get("blue", ""))
        recent = self._log.recent(60)
        cutoff = ts - 3600
        for entry in recent:
            if (entry.get("kind") == kind and
                    entry.get("evidence", {}).get("doctrine") == key[1] and
                    entry.get("evidence", {}).get("terrain") == key[2] and
                    entry.get("evidence", {}).get("red") == key[3] and
                    entry.get("evidence", {}).get("blue") == key[4] and
                    entry.get("ts", 0) >= cutoff):
                return False
        finding = {"ts": ts, "kind": kind, "text": text, "evidence": evidence}
        self._log.append({"type": "finding", **finding})
        self._findings_emitted += 1
        return True

    # ----------------------------------------------------------- self-improve
    def self_improve(self) -> list[ParamChange]:
        """Rewrite per-terrain overrides in ``engines.kriegspiel.combat``
        based on observed performance — gated by multiple-testing correction.

        For each (doctrine, terrain) cell with enough samples:
          - if the doctrine is underperforming, its difference from the
            terrain's strongest doctrine is tested with a two-proportion
            z-test;
          - all candidate adjustments in this step are passed through the
            Benjamini-Hochberg procedure (FDR ``_SELF_IMPROVE_FDR``), so only
            differences that survive correction move parameters;
          - if it is overperforming, log the strength but do not change it.

        Every change is clamped to [_PARAM_FLOOR, _PARAM_CEIL] and recorded
        as a ``ParamChange`` (with its p-value and BH gate) in the research
        log. Returns the changes made.
        """
        with self._lock:
            # Import here so the combat module is loaded by the time we touch it.
            from engines.kriegspiel.combat import _DOCTRINE_PARAMS, _TERRAIN_PARAM_OVERRIDES
            combat_overrides = _TERRAIN_PARAM_OVERRIDES
            changes: list[ParamChange] = []
            now = time.time()

            # Find the strongest doctrine per terrain (by win rate, min samples).
            strongest_per_terrain: dict[str, tuple[str, float, Cell]] = {}
            for (doctrine, terrain), cell in self._cells.items():
                if cell.total < _MIN_SAMPLES:
                    continue
                cur = strongest_per_terrain.get(terrain)
                if cur is None or cell.win_rate > cur[1]:
                    strongest_per_terrain[terrain] = (doctrine, cell.win_rate, cell)

            # Phase 1 — candidate hypotheses: underperforming cells with a
            # stronger doctrine to learn from in the same terrain.
            candidates: list[dict[str, Any]] = []
            for (doctrine, terrain), cell in self._cells.items():
                if cell.total < _MIN_SAMPLES:
                    continue
                wr = cell.win_rate
                if wr >= _UNDERPERFORM:
                    # Not underperforming — no change. Log strength if
                    # overperforming is handled by _maybe_distill, not here.
                    continue
                best = strongest_per_terrain.get(terrain)
                if not best or best[0] == doctrine:
                    # No better doctrine to learn from in this terrain.
                    continue
                best_doctrine, best_wr, best_cell = best
                _z, p_value = two_proportion_z(
                    wr, cell.total, best_wr, best_cell.total,
                )
                candidates.append({
                    "doctrine": doctrine, "terrain": terrain, "cell": cell,
                    "win_rate": wr, "best_doctrine": best_doctrine,
                    "best_wr": best_wr, "best_cell": best_cell,
                    "p_value": p_value,
                })

            # Phase 2 — Benjamini-Hochberg gate across ALL hypotheses in this
            # step. Surviving hypotheses are the only ones that move params.
            rejected: list[bool] = []
            bh_threshold = 0.0
            if candidates:
                rejected, bh_threshold = benjamini_hochberg(
                    [c["p_value"] for c in candidates],
                    fdr=_SELF_IMPROVE_FDR,
                )

            # Phase 3 — apply changes only where the difference survives BH.
            # Adjustments are written as PER-TERRAIN overrides
            # (combat._TERRAIN_PARAM_OVERRIDES), never into the base
            # ``_DOCTRINE_PARAMS`` table. Evidence is per-(doctrine, terrain);
            # under the old design one terrain cell rewrote that doctrine's
            # behavior in every theater, homogenizing doctrines toward
            # whatever exploited engine artifacts. Base doctrine identity now
            # stays canonical; lessons stay scoped to where they were earned.
            for candidate, survive in zip(candidates, rejected):
                if not survive:
                    continue
                doctrine = candidate["doctrine"]
                terrain = candidate["terrain"]
                cell = candidate["cell"]
                wr = candidate["win_rate"]
                best_doctrine = candidate["best_doctrine"]
                p_value = candidate["p_value"]
                d_base = _DOCTRINE_PARAMS.get(
                    Doctrine(doctrine), _DOCTRINE_PARAMS[Doctrine.ATTRITION]
                )
                b_base = _DOCTRINE_PARAMS.get(
                    Doctrine(best_doctrine), _DOCTRINE_PARAMS[Doctrine.ATTRITION]
                )
                # Effective current/target = base merged with any existing
                # same-cell override, so repeated nudges compound correctly.
                cur_ov = combat_overrides.setdefault((doctrine, terrain), {})
                cur_params = {**d_base, **cur_ov}
                target_ov = combat_overrides.get((best_doctrine, terrain), {})
                best_params = {**b_base, **target_ov}
                for pfield in ("aggression", "risk", "supply_focus", "morale_drain", "breakthrough"):
                    before = cur_params[pfield]
                    target = best_params[pfield]
                    # Move 5% of the way toward the target.
                    delta = (target - before) * _NUDGE
                    after = max(_PARAM_FLOOR, min(_PARAM_CEIL, before + delta))
                    if abs(after - before) < 1e-4:
                        continue
                    cur_ov[pfield] = round(after, 4)
                    ch = ParamChange(
                        ts=now, doctrine=doctrine, terrain=terrain,
                        field=pfield, before=round(before, 4),
                        after=round(after, 4), win_rate=round(wr, 4),
                        rationale=(f"{doctrine} wins {wr:.0%} in {terrain} "
                                   f"vs {best_doctrine} at {candidate['best_wr']:.0%}; "
                                   f"nudging {pfield} toward {best_doctrine} "
                                   f"({target:.2f}) by {delta:+.3f} "
                                   f"[override: {doctrine}@{terrain}]"),
                        p_value=round(p_value, 6),
                        fdr_gate=round(bh_threshold, 6),
                        survived_bh=True,
                    )
                    changes.append(ch)
                    self._param_changes.append(ch)
                    self._adjustments_per_doctrine[doctrine] += 1
                    self._log.append({
                        "type": "parameter_change",
                        **asdict(ch),
                    })

            if candidates:
                # Record the gate even when nothing survived — the audit trail
                # must show that hypotheses were tested and rejected.
                n_survived = sum(1 for r in rejected if r)
                gate_record = {
                    "ts": now,
                    "candidates_tested": len(candidates),
                    "survived_bh": n_survived,
                    "bh_threshold": round(bh_threshold, 6),
                    "batches": self._batches_observed,
                    "scenarios": self._scenarios_observed,
                    "fdr": _SELF_IMPROVE_FDR,
                }
                self._bh_gates.append(gate_record)
                if len(self._bh_gates) > 200:
                    self._bh_gates = self._bh_gates[-200:]
                self._log.append({
                    "type": "milestone",
                    "ts": now,
                    "text": (f"Self-improvement gate: {len(candidates)} "
                             f"candidate adjustment(s) tested, {n_survived} "
                             f"survived Benjamini-Hochberg (FDR="
                             f"{_SELF_IMPROVE_FDR:.0%}, threshold="
                             f"{bh_threshold:.4g}). Applied {len(changes)} "
                             f"parameter adjustment(s)."),
                    "evidence": gate_record,
                })

            if changes:
                self._last_self_improve_ts = now
            self._save_state()
            return changes

    # --------------------------------------------------------------- readouts
    def strategy_table(self) -> dict[str, Any]:
        """Doctrine × terrain win-rate matrix for the dashboard."""
        with self._lock:
            doctrines = sorted({d for (d, _t) in self._cells})
            terrains = sorted({t for (_d, t) in self._cells})
            matrix: list[list[dict[str, Any]]] = []
            for d in doctrines:
                row: list[dict[str, Any]] = []
                for t in terrains:
                    cell = self._cells.get((d, t))
                    if cell and cell.total:
                        row.append({
                            "win_rate": round(cell.win_rate, 4),
                            "samples": cell.total,
                            "wins": cell.wins,
                            "losses": cell.losses,
                            "stalemates": cell.stalemates,
                            "decisive_wins": cell.decisive_wins,
                        })
                    else:
                        row.append({"win_rate": None, "samples": 0})
                matrix.append(row)
            return {
                "doctrines": doctrines,
                "terrains": terrains,
                "matrix": matrix,
                "scenarios_observed": self._scenarios_observed,
                "batches_observed": self._batches_observed,
            }

    def findings(self, k: int = 10) -> list[dict[str, Any]]:
        """The k most recent findings (newest last)."""
        entries = self._log.recent(k * 3)
        return [e for e in entries if e.get("type") == "finding"][-k:]

    def parameters(self) -> dict[str, Any]:
        """Current doctrine parameters + adjustment counts."""
        with self._lock:
            from engines.kriegspiel.combat import _DOCTRINE_PARAMS, _TERRAIN_PARAM_OVERRIDES
            out: dict[str, Any] = {}
            for doctrine, params in _DOCTRINE_PARAMS.items():
                n_ov = sum(1 for (d, _t) in _TERRAIN_PARAM_OVERRIDES
                           if d == doctrine.value)
                out[doctrine.value] = {
                    "aggression": params["aggression"],
                    "risk": params["risk"],
                    "supply_focus": params["supply_focus"],
                    "morale_drain": params["morale_drain"],
                    "breakthrough": params.get("breakthrough", 0.0),
                    "adjustments": self._adjustments_per_doctrine.get(doctrine.value, 0),
                    "terrain_overrides": n_ov,
                }
            return {
                "current": out,
                "total_adjustments": len(self._param_changes),
                "last_self_improve_ts": self._last_self_improve_ts,
                "last_finding_ts": self._last_finding_ts,
            }

    def dossier(self, k: int = 50) -> dict[str, Any]:
        """Full research dossier: counts, recent log, parameter change history."""
        with self._lock:
            return {
                "findings_emitted": self._findings_emitted,
                "parameter_changes": len(self._param_changes),
                "log_entries": self._log.count,
                "scenarios_observed": self._scenarios_observed,
                "batches_observed": self._batches_observed,
                "recent_log": self._log.recent(k),
                "recent_param_changes": [
                    asdict(ch) for ch in self._param_changes[-k:]
                ],
            }

    def bh_gate_history(self, k: int = 20) -> dict[str, Any]:
        """Multiple-testing gate audit trail for the research API."""
        with self._lock:
            return {
                "fdr": _SELF_IMPROVE_FDR,
                "gates_ran": len(self._bh_gates),
                "hypotheses_tested": sum(g["candidates_tested"] for g in self._bh_gates),
                "hypotheses_survived": sum(g["survived_bh"] for g in self._bh_gates),
                "recent_gates": self._bh_gates[-k:],
            }

    # ------------------------------------------------------------- persistence
    def _save_state(self) -> None:
        """Persist learned parameters + cell counts so a restart resumes
        with learning intact. Failures are swallowed — the simulation must
        never block on a write."""
        try:
            _ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
            from engines.kriegspiel.combat import _TERRAIN_PARAM_OVERRIDES
            payload = {
                "batches_observed": self._batches_observed,
                "scenarios_observed": self._scenarios_observed,
                "findings_emitted": self._findings_emitted,
                "last_self_improve_ts": self._last_self_improve_ts,
                "last_finding_ts": self._last_finding_ts,
                "adjustments_per_doctrine": dict(self._adjustments_per_doctrine),
                "bh_gates": self._bh_gates,
                # Learned adjustments are per-(doctrine, terrain) overrides.
                # The base _DOCTRINE_PARAMS table is canonical source config
                # and is never persisted or mutated at runtime anymore.
                "terrain_overrides": {
                    f"{d}|{t}": dict(p) for (d, t), p in _TERRAIN_PARAM_OVERRIDES.items()
                },
                "cells": {
                    f"{d}|{t}": {
                        "wins": c.wins, "losses": c.losses,
                        "stalemates": c.stalemates, "total": c.total,
                        "decisive_wins": c.decisive_wins,
                    } for (d, t), c in self._cells.items()
                },
            }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, self._state_path)
        except OSError:
            pass

    def _load_state(self) -> None:
        """Restore learned state from disk. Rehydrates the per-terrain
        parameter overrides in the combat module so self-improvements
        survive a restart. Base ``_DOCTRINE_PARAMS`` are canonical source
        config and are deliberately NOT overwritten from state."""
        if not self._state_path.exists():
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        self._batches_observed = payload.get("batches_observed", 0)
        self._scenarios_observed = payload.get("scenarios_observed", 0)
        self._findings_emitted = payload.get("findings_emitted", 0)
        self._last_self_improve_ts = payload.get("last_self_improve_ts", 0.0)
        self._last_finding_ts = payload.get("last_finding_ts", 0.0)
        self._adjustments_per_doctrine = defaultdict(
            int, payload.get("adjustments_per_doctrine", {})
        )
        self._bh_gates = payload.get("bh_gates", [])
        # Rehydrate cells.
        for key, vals in payload.get("cells", {}).items():
            d, t = key.split("|", 1)
            cell = self._cells[(d, t)]
            cell.wins = vals.get("wins", 0)
            cell.losses = vals.get("losses", 0)
            cell.stalemates = vals.get("stalemates", 0)
            cell.total = vals.get("total", 0)
            cell.decisive_wins = vals.get("decisive_wins", 0)
        # Rehydrate per-terrain overrides into the live combat module.
        # Legacy ``current_params`` (global doctrine drift from the pre-fix
        # design) is intentionally ignored — those values encoded engine
        # artifacts and must not silently redefine base doctrines.
        saved_overrides = payload.get("terrain_overrides", {})
        try:
            from engines.kriegspiel.combat import _TERRAIN_PARAM_OVERRIDES
            for key, params in saved_overrides.items():
                try:
                    d_name, t_name = key.split("|", 1)
                    Doctrine(d_name)
                    TerrainType(t_name)
                except (ValueError, KeyError):
                    continue
                clean = {k_: float(v) for k_, v in params.items()
                         if isinstance(v, (int, float)) and v == v}
                if clean:
                    _TERRAIN_PARAM_OVERRIDES[(d_name, t_name)] = clean
        except Exception:
            # Combat module not loaded yet — overrides will rehydrate when it
            # loads via the gateway's _load_kriegspiel(). Not fatal.
            pass


# ------------------------------------------------------------------- singleton
_tracker: Optional[DoctrinePerformanceTracker] = None
_tracker_lock = threading.Lock()


def get_tracker() -> DoctrinePerformanceTracker:
    """Return the process-wide tracker singleton."""
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = DoctrinePerformanceTracker()
    return _tracker


# -------------------------------------------------------------------
# Campaign-level learning (operational layer)
#
# Battles teach tactics; campaigns teach operations. This tracker folds
# campaign outcomes into the research dossier so tempo/pyrrhic lessons
# ("an offensive that outruns its replacements stalls and bleeds") are
# learned alongside doctrine x terrain win rates. Outcomes are bucketed by
# *sustainment context* because phase-4 validation showed reinforcement
# asymmetry is a first-order campaign variable — pooling symmetric and
# asymmetric runs would average the lesson away.
# -------------------------------------------------------------------

_CAMPAIGN_STATE_PATH = _ANALYTICS_DIR / "campaign_state.json"
_MIN_CAMPAIGN_SAMPLES = 20      # findings below this n are marked preliminary


def sustainment_bucket(red_rate: float, blue_rate: float,
                       tol: float = 0.05) -> str:
    """Classify a campaign's sustainment context.

    "symmetric"        — both sides reinforced comparably
    "red_starved"      — red's replacements lag blue's (attacker outrunning
                         its supply in the standard offensive role)
    "blue_starved"     — mirror case
    """
    if abs(red_rate - blue_rate) <= tol:
        return "symmetric"
    return "red_starved" if red_rate < blue_rate else "blue_starved"


@dataclass
class CampaignCell:
    """Accumulated campaign statistics for one (matchup, sustainment) cell."""

    red_wins: int = 0
    blue_wins: int = 0
    stalemates: int = 0
    total: int = 0
    front_sum: float = 0.0
    red_remaining_sum: float = 0.0
    blue_remaining_sum: float = 0.0
    engagements_sum: int = 0

    @property
    def red_win_share(self) -> float:
        decided = self.red_wins + self.blue_wins
        return self.red_wins / decided if decided else 0.0


class CampaignPerformanceTracker:
    """Accumulates campaign outcomes into (matchup, sustainment-bucket) cells
    and distills operational-tempo findings. Persisted separately from the
    tactical research state; same audit conventions."""

    def __init__(self,
                 state_path: Optional[Path] = None,
                 log_path: Optional[Path] = None) -> None:
        self._state_path = state_path or _CAMPAIGN_STATE_PATH
        self._log = ResearchLog(log_path or (_ANALYTICS_DIR / "campaign_log.jsonl"))
        self._lock = threading.Lock()
        self._cells: dict[tuple[str, str, str], CampaignCell] = defaultdict(CampaignCell)
        self._observed_total = 0
        self._findings_emitted = 0
        self._last_finding_ts = 0.0
        self._load_state()

    # ------------------------------------------------------------- observe
    def record(self,
               red_doctrine: str,
               blue_doctrine: str,
               bucket: str,
               winner: str,
               front_final_pct: float,
               red_remaining_pct: float,
               blue_remaining_pct: float,
               engagements_fought: int) -> None:
        """Record one finished campaign. ``winner`` is 'red'/'blue'/'stalemate'."""
        with self._lock:
            cell = self._cells[(red_doctrine, blue_doctrine, bucket)]
            cell.total += 1
            if winner == "red":
                cell.red_wins += 1
            elif winner == "blue":
                cell.blue_wins += 1
            else:
                cell.stalemates += 1
            cell.front_sum += float(front_final_pct)
            cell.red_remaining_sum += float(red_remaining_pct)
            cell.blue_remaining_sum += float(blue_remaining_pct)
            cell.engagements_sum += int(engagements_fought)
            self._observed_total += 1
            self._save_state()

    def observe_report(self, report: Any,
                       red_reinforcement: float,
                       blue_reinforcement: float) -> None:
        """Duck-typed ingest of a ``CampaignReport`` (+ its sustainment rates)."""
        self.record(
            red_doctrine=getattr(report, "red_doctrine", ""),
            blue_doctrine=getattr(report, "blue_doctrine", ""),
            bucket=sustainment_bucket(red_reinforcement, blue_reinforcement),
            winner=getattr(report, "campaign_winner", "stalemate"),
            front_final_pct=getattr(report, "front_final_pct", 50.0),
            red_remaining_pct=getattr(report, "red_remaining_pct", 100.0),
            blue_remaining_pct=getattr(report, "blue_remaining_pct", 100.0),
            engagements_fought=getattr(report, "engagements_fought", 0),
        )

    # ------------------------------------------------------------ readouts
    def table(self) -> dict[str, Any]:
        """Matchup x sustainment summary for dashboards/research consumers."""
        with self._lock:
            out = []
            for (r_d, b_d, bucket), cell in sorted(self._cells.items()):
                if not cell.total:
                    continue
                out.append({
                    "red_doctrine": r_d,
                    "blue_doctrine": b_d,
                    "sustainment": bucket,
                    "total": cell.total,
                    "red_win_share": round(cell.red_win_share, 3),
                    "stalemates": cell.stalemates,
                    "avg_front_pct": round(cell.front_sum / cell.total, 1),
                    "avg_red_remaining_pct": round(cell.red_remaining_sum / cell.total, 1),
                    "avg_blue_remaining_pct": round(cell.blue_remaining_sum / cell.total, 1),
                    "avg_engagements": round(cell.engagements_sum / max(cell.total, 1), 2),
                })
            return {"cells": out, "observed_total": self._observed_total}

    def findings(self, k: int = 12) -> list[dict[str, Any]]:
        """Distill operational-tempo lessons from accumulated cells.

        Two finding shapes:
          - matchup strength: who wins campaigns in a given sustainment context
          - tempo effect: how an attacker's campaign fortunes shift when
            replacements outrun (or trail) the advance — only emitted when BOTH
            buckets of the same matchup have enough samples.
        """
        with self._lock:
            now = time.time()
            findings: list[dict[str, Any]] = []
            by_matchup: dict[tuple[str, str], dict[str, CampaignCell]] = defaultdict(dict)
            for (r_d, b_d, bucket), cell in self._cells.items():
                if cell.total >= _MIN_CAMPAIGN_SAMPLES:
                    by_matchup[(r_d, b_d)][bucket] = cell
                    share = cell.red_win_share
                    leader = ("red" if share > 0.5 else
                              ("blue" if share < 0.5 else "neither"))
                    if leader != "neither":
                        strong = (cell.red_wins if leader == "red" else cell.blue_wins)
                        findings.append({
                            "ts": now,
                            "kind": "campaign_matchup",
                            "text": (
                                f"{r_d} defeats {b_d} in {strong}/{cell.total} "
                                f"campaigns ({strong / cell.total:.0%}) under "
                                f"{bucket.replace('_', ' ')} sustainment; avg front "
                                f"{cell.front_sum / cell.total:.0f}%"
                            ),
                            "evidence": {
                                "matchup": f"{r_d}|{b_d}", "bucket": bucket,
                                "n": cell.total, "share": round(share, 3),
                            },
                        })

            # Tempo effects: same matchup, opposite starvation buckets.
            for (r_d, b_d), buckets in by_matchup.items():
                sym = buckets.get("symmetric")
                starved = buckets.get("red_starved")
                fed = buckets.get("blue_starved")
                if sym and starved:
                    drop = sym.red_win_share - starved.red_win_share
                    if abs(drop) >= 0.08:
                        findings.append({
                            "ts": now,
                            "kind": "tempo_effect",
                            "text": (
                                f"Tempo lesson ({r_d} vs {b_d}): when replacements "
                                f"outrun the advance, {r_d}'s campaign wins fall "
                                f"{sym.red_win_share:.0%} -> {starved.red_win_share:.0%}"
                                f" (Δ{drop:+.0%}, n={sym.total}/{starved.total}) — "
                                f"offensives need sustainment to convert tactical "
                                f"wins into ground."
                            ),
                            "evidence": {
                                "matchup": f"{r_d}|{b_d}",
                                "symmetric_share": round(sym.red_win_share, 3),
                                "starved_share": round(starved.red_win_share, 3),
                            },
                        })
                if sym and fed:
                    gain = fed.red_win_share - sym.red_win_share
                    if abs(gain) >= 0.08:
                        findings.append({
                            "ts": now,
                            "kind": "tempo_effect",
                            "text": (
                                f"Tempo lesson ({r_d} vs {b_d}): starving the "
                                f"defense lifts {r_d} campaign wins "
                                f"{sym.red_win_share:.0%} -> {fed.red_win_share:.0%}"
                                f" (Δ{gain:+.0%}, n={sym.total}/{fed.total})."
                            ),
                            "evidence": {
                                "matchup": f"{r_d}|{b_d}",
                                "symmetric_share": round(sym.red_win_share, 3),
                                "defender_starved_share": round(fed.red_win_share, 3),
                            },
                        })

            new_findings = findings[:k]
            if new_findings:
                self._findings_emitted += len(new_findings)
                self._last_finding_ts = now
                for f in new_findings:
                    self._log.append({"type": "campaign_finding", **f})
            return new_findings

    # --------------------------------------------------------- persistence
    def _save_state(self) -> None:
        try:
            _ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "observed_total": self._observed_total,
                "findings_emitted": self._findings_emitted,
                "last_finding_ts": self._last_finding_ts,
                "cells": {
                    "|".join(key): {
                        "red_wins": c.red_wins, "blue_wins": c.blue_wins,
                        "stalemates": c.stalemates, "total": c.total,
                        "front_sum": c.front_sum,
                        "red_remaining_sum": c.red_remaining_sum,
                        "blue_remaining_sum": c.blue_remaining_sum,
                        "engagements_sum": c.engagements_sum,
                    } for key, c in self._cells.items()
                },
            }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, self._state_path)
        except OSError:
            pass

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        self._observed_total = payload.get("observed_total", 0)
        self._findings_emitted = payload.get("findings_emitted", 0)
        self._last_finding_ts = payload.get("last_finding_ts", 0.0)
        for key, vals in payload.get("cells", {}).items():
            parts = key.split("|")
            if len(parts) != 3:
                continue
            cell = self._cells[tuple(parts)]
            cell.red_wins = vals.get("red_wins", 0)
            cell.blue_wins = vals.get("blue_wins", 0)
            cell.stalemates = vals.get("stalemates", 0)
            cell.total = vals.get("total", 0)
            cell.front_sum = vals.get("front_sum", 0.0)
            cell.red_remaining_sum = vals.get("red_remaining_sum", 0.0)
            cell.blue_remaining_sum = vals.get("blue_remaining_sum", 0.0)
            cell.engagements_sum = vals.get("engagements_sum", 0)


_campaign_tracker: Optional[CampaignPerformanceTracker] = None
_campaign_tracker_lock = threading.Lock()


def get_campaign_tracker() -> CampaignPerformanceTracker:
    """Process-wide singleton, mirroring :func:`get_tracker`."""
    global _campaign_tracker
    if _campaign_tracker is None:
        with _campaign_tracker_lock:
            if _campaign_tracker is None:
                _campaign_tracker = CampaignPerformanceTracker()
    return _campaign_tracker
