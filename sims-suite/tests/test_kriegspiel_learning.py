"""Kriegspiel learning-layer tests — the BH-gated self-improvement audit trail.

Covers ``engines.kriegspiel.learning.DoctrinePerformanceTracker`` public API:
observe (consuming scenario reports), strategy_table, findings, parameters,
dossier, bh_gate_history, and state save/load. Uses isolated tmp paths so it
never touches the live research_state.json.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.learning import DoctrinePerformanceTracker, _MIN_SAMPLES, _UNDERPERFORM


def _branch(winner, red_doctrine="shock", blue_doctrine="defensive",
            red_cas=20.0, blue_cas=10.0, decisive=False):
    return SimpleNamespace(
        winner=winner, red_doctrine=red_doctrine, blue_doctrine=blue_doctrine,
        red_casualties_pct=red_cas, blue_casualties_pct=blue_cas, decisive=decisive,
    )


def _report(branches, battlefield_name="Eastern Europe"):
    return SimpleNamespace(battlefield_name=battlefield_name, branches=branches)


def _make_tracker(tmp_path):
    return DoctrinePerformanceTracker(
        state_path=tmp_path / "state.json", log_path=tmp_path / "log.jsonl",
    )


def test_observe_updates_cells_and_matchups(tmp_path):
    tr = _make_tracker(tmp_path)
    # Red shock beats blue defensive in open terrain (Eastern Europe).
    tr.observe(_report([_branch("red", red_doctrine="shock", blue_doctrine="defensive")]))
    tr.observe(_report([_branch("red", red_doctrine="shock", blue_doctrine="defensive")]))

    assert tr._cells[("shock", "open")].wins == 2
    assert tr._cells[("defensive", "open")].losses == 2
    assert tr._matchups[("shock", "defensive")]["total"] == 2
    assert tr._matchups[("shock", "defensive")]["wins"] == 2
    assert tr._batches_observed == 2
    assert tr._scenarios_observed == 2


def test_observe_skips_untagged_branches(tmp_path):
    tr = _make_tracker(tmp_path)
    untagged = SimpleNamespace(
        winner="red", red_doctrine="", blue_doctrine="",
        red_casualties_pct=1.0, blue_casualties_pct=1.0, decisive=False,
    )
    tr.observe(_report([untagged]))
    assert tr._cells == {}  # no cells created (the key skip behavior)
    assert tr._matchups == {}


def test_strategy_table_shape(tmp_path):
    tr = _make_tracker(tmp_path)
    tr.observe(_report([_branch("red")] * 3 + [_branch("blue")]))
    table = tr.strategy_table()
    assert "doctrines" in table and "terrains" in table and "matrix" in table
    assert "open" in table["terrains"]
    # shock (red) should have a populated cell.
    shock_idx = table["doctrines"].index("shock")
    open_idx = table["terrains"].index("open")
    cell = table["matrix"][shock_idx][open_idx]
    assert cell["samples"] == 4
    assert cell["win_rate"] == 0.75


def test_parameters_readout_includes_breakthrough(tmp_path):
    tr = _make_tracker(tmp_path)
    params = tr.parameters()
    assert "current" in params
    shock = params["current"]["shock"]
    assert "breakthrough" in shock
    assert "aggression" in shock
    assert "total_adjustments" in params


def test_dossier_shape(tmp_path):
    tr = _make_tracker(tmp_path)
    tr.observe(_report([_branch("red")] * 5))
    d = tr.dossier(k=5)
    assert d["scenarios_observed"] == 5
    assert "recent_log" in d
    assert "recent_param_changes" in d
    assert "findings_emitted" in d


def test_bh_gate_history_initial(tmp_path):
    tr = _make_tracker(tmp_path)
    h = tr.bh_gate_history()
    assert h["fdr"] == 0.10
    assert h["gates_ran"] == 0
    assert h["hypotheses_tested"] == 0


def test_findings_emitted_when_cell_significant(tmp_path):
    tr = _make_tracker(tmp_path)
    # Feed enough underperforming branches to cross _MIN_SAMPLES.
    branches = [_branch("blue")] * (_MIN_SAMPLES + 5)   # red (shock) always loses
    tr.observe(_report(branches))
    findings = tr.findings()
    # At least one terrain_doctrine_weak finding for shock losing.
    weak = [f for f in findings if f.get("kind") == "terrain_doctrine_weak"]
    assert weak, "expected a weak-doctrine finding"
    assert tr.dossier()["findings_emitted"] >= 1


def test_state_saves_and_loads(tmp_path):
    tr = _make_tracker(tmp_path)
    tr.observe(_report([_branch("red")] * 4))
    # New tracker loading the same state should see the persisted cells.
    tr2 = _make_tracker(tmp_path)
    assert tr2._cells[("shock", "open")].wins == 4
    assert tr2._batches_observed == tr._batches_observed


def test_get_tracker_returns_singleton():
    from engines.kriegspiel.learning import get_tracker
    a = get_tracker()
    b = get_tracker()
    assert a is b