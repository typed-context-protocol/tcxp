"""Benchmark: is the tax year stated, and does the system act or ask correctly?

Ten requests with known ground truth (``CASES``). Each **arm** decides, for each
request, either to ACT on a tax year or to ASK. Scoring:

* **correct**: acted on the true year, or asked when no year was stated
* **silent error**: acted on a wrong year, or invented one that wasn't stated (regret)
* **extra ask**: asked even though the year was stated (safe, costs a question)

Arms:

==================  =========================================================
code                regex only; asks whenever it doesn't find a year
llm_alone           the LLM's answer is taken as-is
llm_with_context    code first; then the LLM with the context object's rules; ask below 0.8 confidence
jev_alone           Jev's top choice is taken as-is
jev_with_context    code first; then Jev with the context object's rules; ask below 0.8
ladder              code → Jev → LLM (with context) → ask
==================  =========================================================

``mode="simulated"`` uses ``SimulatedChecker`` with the declared assumptions in
``SIM_LLM`` and ``SIM_JEV`` (edit them; results are only as good as they are).
``mode="real"`` calls Jev and Claude using JEV_API_KEY and ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .ladder import NOT_STATED, Answer, CodeChecker, Ladder, Question, SimulatedChecker

__all__ = ["CASES", "OPTIONS", "CONTEXT_RULES", "SIM_LLM", "SIM_JEV", "detect_tax_year", "run_bench", "BenchRow"]

OPTIONS = ("2023", "2024", "2025", NOT_STATED)

CASES: list[tuple[str, str]] = [
    ("How much should I deduct for Section 41 US-based QREs?", NOT_STATED),
    ("What were our qualified research expenses for tax year 2024?", "2024"),
    ("Calculate the R&D credit for FY24.", "2024"),
    ("The Atlas project started in 2025. How much can we claim?", NOT_STATED),
    ("For our 2024 return, how much R&D investment qualifies under section 41?", "2024"),
    ("How much did we spend on research last year?", NOT_STATED),
    ("Use the 2024 numbers to figure the section 41 credit.", "2024"),
    ("We're filing for 2024 but the payroll export runs into 2025. What's the QRE total?", "2024"),
    ("What were total US wages for engineers working on Atlas?", NOT_STATED),
    ("Section 41 credit for the 2025 tax year, please.", "2025"),
]

CONTEXT_RULES = ("tax_year is essential to this decision. Answer not_stated unless the request explicitly names the "
                 "tax year, fiscal year, or return or filing year. A year that only says when a project started or "
                 "launched does not count. Relative words like 'last year' do not count.")

ASK = "Which tax year is this request for?"

SIM_LLM = dict(accuracy=0.95, guess_rate=0.6, context_effect=0.15, calibrated=False, latency_ms=900.0,
               tokens_overhead=150, tokens_out=14, price_in=1.0, price_out=5.0)
SIM_JEV = dict(accuracy=0.9, guess_rate=0.4, context_effect=0.3, calibrated=True, latency_ms=120.0,
               tokens_overhead=300, tokens_out=0, price_in=0.042, price_out=0.0)

_YEAR_PATTERNS = [
    re.compile(r"\b(?:tax\s*year|taxable\s*year|fiscal\s*year|tax\s*return|return|filing)\s*(?:of|for|is|:)?\s*'?(20\d{2})\b", re.I),
    re.compile(r"\b(20\d{2})\s*(?:tax\s*year|taxable\s*year|fiscal\s*year|tax\s*return|return|filing)\b", re.I),
    re.compile(r"\bFY\s?'?(\d{2}|\d{4})\b", re.I),
]


def detect_tax_year(text: str) -> str | None:
    """Deterministic check: a year next to 'tax year', 'FY', 'return' or 'filing'."""
    for p in _YEAR_PATTERNS:
        m = p.search(text)
        if m:
            y = m.group(1)
            return "20" + y if len(y) == 2 else y
    return None


def _code_strict(q: Question) -> tuple[Any, float]:
    y = detect_tax_year(q.text)
    return (y, 1.0) if y else (NOT_STATED, 1.0)


def _code_first(q: Question) -> tuple[Any, float] | None:
    y = detect_tax_year(q.text)
    return (y, 1.0) if y else None


@dataclass
class BenchRow:
    arm: str
    correct: int = 0
    silent_errors: int = 0
    extra_asks: int = 0
    errors: int = 0
    ms: float = 0.0
    tokens: int = 0
    cost: float = 0.0
    simulated: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)


def _checkers(mode: str, seed: int, jev_key: str | None, claude_key: str | None) -> tuple[Callable[[], Any], Callable[[], Any]]:
    if mode == "real":
        from .models import ClaudeChecker, JevChecker
        return (lambda: JevChecker(jev_key)), (lambda: ClaudeChecker(claude_key))
    return (lambda: SimulatedChecker("jev", seed=seed, **SIM_JEV)), (lambda: SimulatedChecker("llm", seed=seed, **SIM_LLM))


def run_bench(mode: str = "simulated", seed: int = 0, arms: tuple[str, ...] | None = None,
              jev_key: str | None = None, claude_key: str | None = None) -> list[BenchRow]:
    jev, llm = _checkers(mode, seed, jev_key, claude_key)
    code_strict, code_first = CodeChecker("code", _code_strict), CodeChecker("code", _code_first)
    plans: dict[str, tuple[Ladder, bool]] = {
        "code": (Ladder([code_strict], 0.0), False),
        "llm_alone": (Ladder([llm()], 0.0), False),
        "llm_with_context": (Ladder([code_first, llm()], 0.8), True),
        "jev_alone": (Ladder([jev()], 0.0), False),
        "jev_with_context": (Ladder([code_first, jev()], 0.8), True),
        "ladder": (Ladder([code_first, jev(), llm()], 0.8), True),
    }
    rows = []
    for arm in arms or tuple(plans):
        ladder, with_ctx = plans[arm]
        row = BenchRow(arm, simulated=(mode != "real") and arm != "code")
        for i, (text, truth) in enumerate(CASES):
            q = Question(f"case-{i}", text, ASK, "choice", OPTIONS, context=CONTEXT_RULES if with_ctx else "", truth=truth)
            res = ladder.run(q)
            row.ms += res.ms
            row.tokens += res.tokens
            row.cost += res.cost
            errs = [a.error for a in res.steps if a.error]
            if errs and not any(not a.error for a in res.steps):
                row.errors += 1
                outcome = "error"
            elif res.verdict == "ASK":
                outcome = "correct" if truth == NOT_STATED else "extra ask"
            else:
                outcome = "correct" if res.answer.value == truth else "silent error"
            row.correct += outcome == "correct"
            row.silent_errors += outcome == "silent error"
            row.extra_asks += outcome == "extra ask"
            row.details.append({"case": text, "truth": truth, "verdict": res.verdict,
                                "value": res.answer.value if res.answer else None, "decided_by": res.decided_by,
                                "outcome": outcome, "errors": errs})
        rows.append(row)
    return rows
