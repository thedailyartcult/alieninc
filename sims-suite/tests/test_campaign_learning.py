"""Campaign learning tracker tests.

Covers CampaignPerformanceTracker: accumulation, sustainment bucketing,
persistence round-trip, and finding distillation (matchup strength +
tempo effects). Uses tmp paths — never touches production campaign state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.learning import (
    CampaignPerformanceTracker,
    sustainment_bucket,
)


def _make_tracker(tmp_path):
    return CampaignPerformanceTracker(
        state_path=tmp_path / "campaign_state.json",
        log_path=tmp_path / "campaign_log.jsonl",
    )


def _report(winner="red", front=65.0, red_left=80.0, blue_left=20.0,
            engagements=4, red_doctrine="shock", blue_doctrine="defensive"):
    return SimpleNamespace(
        campaign_winner=winner, front_final_pct=front,
        red_remaining_pct=red_left, blue_remaining_pct=blue_left,
        engagements_fought=engagements, red_doctrine=red_doctrine,
        blue_doctrine=blue_doctrine,
    )


def test_bucketing_logic():
    assert sustainment_bucket(0.30, 0.30) == "symmetric"
    assert sustainment_bucket(0.28, 0.30) == "symmetric"      # within tol
    assert sustainment_bucket(0.10, 0.35) == "red_starved"
    assert sustainment_bucket(0.35, 0.05) == "blue_starved"


def test_record_accumulates(tmp_path):
    tr = _make_tracker(tmp_path)
    for _ in range(3):
        tr.record("shock", "defensive", "symmetric", "red",
                  front_final_pct=70, red_remaining_pct=80,
                  blue_remaining_pct=20, engagements_fought=4)
    tr.record("shock", "defensive", "symmetric", "blue",
              55.0, 60.0, 40.0, 5)
    cell = tr._cells[("shock", "defensive", "symmetric")]
    assert cell.total == 4 and cell.red_wins == 3 and cell.blue_wins == 1
    table = tr.table()
    entry = table["cells"][0]
    assert entry["total"] == 4
    assert abs(entry["avg_front_pct"] - 66.2) < 0.1


def test_observe_report_duck_typed(tmp_path):
    tr = _make_tracker(tmp_path)
    tr.observe_report(_report(), red_reinforcement=0.1, blue_reinforcement=0.35)
    tr.observe_report(_report(winner="blue"), red_reinforcement=0.35,
                      blue_reinforcement=0.10)
    assert tr._cells[("shock", "defensive", "red_starved")].total == 1
    assert tr._cells[("shock", "defensive", "blue_starved")].total == 1


def test_state_round_trip(tmp_path):
    tr = _make_tracker(tmp_path)
    for i in range(5):
        tr.record("maneuver", "guerrilla", "symmetric", "red",
                  68.0 + i, 75.0 - i, 25.0 + i, 3)
    tr2 = _make_tracker(tmp_path)
    assert tr2._observed_total == 5
    cell = tr2._cells[("maneuver", "guerrilla", "symmetric")]
    assert cell.red_wins == 5 and cell.total == 5
    assert abs(cell.front_sum / 5 - 70.0) < 1e-9


def test_findings_matchup_and_tempo(tmp_path):
    tr = _make_tracker(tmp_path)
    n = 22   # above _MIN_CAMPAIGN_SAMPLES
    # Symmetric: shock dominates defensive campaigns.
    for _ in range(n):
        tr.record("shock", "defensive", "symmetric", "red",
                  72.0, 82.0, 18.0, 4)
    # Red-starved: shock's campaign wins collapse.
    for _ in range(n):
        tr.record("shock", "defensive", "red_starved", "blue",
                  42.0, 55.0, 45.0, 6)
    findings = tr.findings()
    kinds = {f["kind"] for f in findings}
    assert "campaign_matchup" in kinds
    assert "tempo_effect" in kinds
    tempo = next(f for f in findings if f["kind"] == "tempo_effect")
    assert "74%" in tempo["text"].replace(".00%", "%").replace(".0%", "%") or \
           "100%" in tempo["text"]
    assert "sustainment" in tempo["text"] or "replacements" in tempo["text"]


def test_findings_skip_small_cells(tmp_path):
    tr = _make_tracker(tmp_path)
    for _ in range(3):   # below min samples
        tr.record("shock", "defensive", "symmetric", "red", 70, 80, 20, 4)
    assert tr.findings() == []


def test_singleton():
    from engines.kriegspiel.learning import get_campaign_tracker
    assert get_campaign_tracker() is get_campaign_tracker()
