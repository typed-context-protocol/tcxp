"""How many verified examples a decision needs before it is safe to automate.

* ``end_to_end_error(cost, tolerated, floor_pct)``: the error rate you can afford:
  tolerated loss ÷ cost of one error, never more than the reliability floor allows.
* ``per_step_error(E, k)``: a chain of k steps is right only if every step is,
  so each step must stay under ``1 - (1 - E) ** (1 / k)``.
* ``cases_needed(e, confidence, failures)``: the fewest test cases that prove the
  error rate is below ``e`` (about ``3 / e`` at 95% with zero failures).
* ``weeks_to(n, volume, answered_pct)``: how long collecting them takes.
* ``budget(...)``: all of the above for one decision, with a recommendation.

These are planning estimates. They assume test cases look like real traffic and errors
are independent. A new client, format or tax year is a new population.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["end_to_end_error", "per_step_error", "cases_needed", "weeks_to", "recommend", "budget", "Budget", "binom_cdf"]


def end_to_end_error(cost: float, tolerated: float, floor_pct: float = 95.0) -> float:
    if not (cost > 0 and tolerated > 0 and 0 < floor_pct < 100):
        raise ValueError("cost and tolerated must be positive; floor_pct between 0 and 100")
    return min(tolerated / cost, (100 - floor_pct) / 100)


def per_step_error(e2e: float, steps: int) -> float:
    if not (0 < e2e < 1 and steps >= 1):
        raise ValueError("e2e must be between 0 and 1; steps at least 1")
    return -math.expm1(math.log1p(-e2e) / steps)


def binom_cdf(n: int, e: float, f: int) -> float:
    """P(X <= f) for X ~ Binomial(n, e), in log space so large n stays finite."""
    if f < 0:
        return 0.0
    if f >= n or e <= 0:
        return 1.0
    if e >= 1:
        return 0.0
    le, lq = math.log(e), math.log1p(-e)
    logp = n * lq
    s = math.exp(logp)
    for i in range(min(f, n)):
        logp += math.log((n - i) / (i + 1)) + le - lq
        s += math.exp(logp)
    return s


def cases_needed(e: float, confidence: float = 0.95, failures: int = 0) -> int:
    if not (0 < e < 1 and 0 < confidence < 1 and failures >= 0):
        raise ValueError("e and confidence must be between 0 and 1; failures >= 0")
    a = 1 - confidence
    n0 = math.ceil(math.log(a) / math.log1p(-e) - 1e-9)
    if failures == 0:
        return n0
    lo = hi = max(n0, failures + 1)
    while binom_cdf(hi, e, failures) > a:
        lo, hi = hi, hi * 2
    while lo < hi:
        mid = (lo + hi) // 2
        if binom_cdf(mid, e, failures) > a:
            lo = mid + 1
        else:
            hi = mid
    return lo


def weeks_to(n: int, volume: float, answered_pct: float) -> float:
    rate = volume * answered_pct / 100
    return n / rate if rate > 0 else math.inf


def recommend(weeks: float) -> str:
    if not math.isfinite(weeks):
        return "No volume to learn from"
    if weeks <= 4:
        return "Automate within a month"
    if weeks <= 26:
        return "Gate it and collect"
    return "Keep a person on it, or split it"


@dataclass(frozen=True)
class Budget:
    e2e: float
    per_step: float
    cases: int
    weeks: float
    recommendation: str


def budget(steps: int, cost: float, tolerated: float, volume: float, answered_pct: float,
           floor_pct: float = 95.0, confidence: float = 0.95, failures: int = 0) -> Budget:
    e = end_to_end_error(cost, tolerated, floor_pct)
    s = per_step_error(e, steps)
    n = cases_needed(s, confidence, failures)
    w = weeks_to(n, volume, answered_pct)
    return Budget(e, s, n, w, recommend(w))
