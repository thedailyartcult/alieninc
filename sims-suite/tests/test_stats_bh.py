"""Stats tests — two-proportion z-test and Benjamini-Hochberg FDR control.

The MatrAIx validation protocol relies on significance testing with
multiple-testing correction; these are the stdlib-only primitives the persona
core and the Kriegspiel learning layer share.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sims_core.stats import two_proportion_z, benjamini_hochberg, normal_cdf


def test_two_proportion_z_rejects_big_difference():
    z, p = two_proportion_z(0.2, 100, 0.5, 100)
    assert abs(z) > 3
    assert p < 0.01


def test_two_proportion_z_accepts_similar_proportions():
    z, p = two_proportion_z(0.5, 100, 0.52, 100)
    assert p > 0.05


def test_two_proportion_z_degenerate_inputs():
    z, p = two_proportion_z(0.5, 0, 0.5, 100)
    assert p == 1.0
    z, p = two_proportion_z(0.0, 100, 0.0, 100)
    assert p == 1.0


def test_normal_cdf_bounds():
    assert abs(normal_cdf(0.0) - 0.5) < 1e-9
    assert normal_cdf(3.0) > 0.99
    assert normal_cdf(-3.0) < 0.01


def test_bh_rejects_small_pvalues_only():
    pvals = [0.001, 0.01, 0.03, 0.4, 0.5, 0.9]
    rejected, threshold = benjamini_hochberg(pvals, fdr=0.10)
    assert rejected == [True, True, True, False, False, False]
    assert threshold == 0.03


def test_bh_empty():
    rejected, threshold = benjamini_hochberg([], fdr=0.10)
    assert rejected == []
    assert threshold == 0.0


def test_bh_preserves_input_order():
    pvals = [0.9, 0.001, 0.02, 0.05]
    rejected, _ = benjamini_hochberg(pvals, fdr=0.10)
    # Input order preserved: the three small p-values are rejected; the 0.9
    # at index 0 is not.
    assert rejected == [False, True, True, True]


def test_bh_stricter_fdr_rejects_fewer():
    pvals = [0.01, 0.02, 0.05, 0.09]
    loose, _ = benjamini_hochberg(pvals, fdr=0.25)
    strict, _ = benjamini_hochberg(pvals, fdr=0.05)
    assert sum(strict) <= sum(loose)