"""Shared statistical helpers — stdlib-only (air-gapped friendly).

The MatrAIx validation protocol leans on two things the sims stack now shares:
two-proportion significance testing and Benjamini-Hochberg multiple-testing
correction. Pure stdlib (math only) so the stack stays dependency-free.
"""

from __future__ import annotations

import math


def normal_cdf(x: float) -> float:
    """Standard normal CDF via the erf approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_proportion_z(
    p1: float, n1: int, p2: float, n2: int,
) -> tuple[float, float]:
    """Two-proportion z-test. Returns ``(z, p_value)`` (two-sided).

    Tests H0: the true proportions are equal. Used to compare one cell's win
    rate against a reference win rate before we trust a difference.
    """
    if n1 <= 0 or n2 <= 0:
        return (0.0, 1.0)
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    if pooled <= 0 or pooled >= 1:
        return (0.0, 1.0)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p1 - p2) / se
    p_value = 2 * (1 - normal_cdf(abs(z)))
    return (z, p_value)


def benjamini_hochberg(
    p_values: list[float],
    fdr: float = 0.10,
) -> tuple[list[bool], float]:
    """Benjamini-Hochberg FDR control.

    Returns ``(rejected, threshold)`` where ``rejected[i]`` is True iff the
    i-th p-value survives correction and ``threshold`` is the largest p-value
    still rejected (the BH critical value). Input order is preserved, so
    callers can zip the result against their original hypotheses.
    """
    m = len(p_values)
    if m == 0:
        return ([], 0.0)
    order = sorted(range(m), key=lambda i: p_values[i])
    max_k = 0
    threshold = 0.0
    for rank, idx in enumerate(order, start=1):
        crit = (rank / m) * fdr
        if p_values[idx] <= crit:
            max_k = rank
            threshold = max(threshold, p_values[idx])
    rejected = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= max_k:
            rejected[idx] = True
    return (rejected, threshold)