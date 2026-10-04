"""The check ladder: code first, then Jev, then an LLM, then a person.

Each rung is a **checker** that answers a typed **Question** (yes/no or pick-one)
with a value and a confidence. The ladder stops at the first rung confident enough
(``threshold``). If no rung is, the verdict is ASK: a person decides, and their answer
becomes a labeled example.

Rungs are interchangeable because they all return the same ``Answer`` shape:

* ``CodeChecker``: a plain Python function (regex, lookup). Instant, free, exact.
* ``SimulatedChecker``: stands in for Jev or an LLM with *declared* accuracy,
  guessing and calibration, so experiments run with no API keys. Every number it
  produces comes from those declared assumptions, and is labeled simulated.
* ``tcxp.models.JevChecker`` / ``ClaudeChecker``: real API calls (optional).

The answer ``"not_stated"`` means "the information isn't there". On an essential key
it routes to ASK, never to a guess.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Protocol

__all__ = ["Question", "Answer", "Checker", "CodeChecker", "SimulatedChecker", "Ladder", "LadderResult", "NOT_STATED"]

NOT_STATED = "not_stated"


@dataclass(frozen=True)
class Question:
    id: str
    text: str                                   # what the checker reads (the state, e.g. the user's query)
    ask: str = ""                               # the question about it
    kind: str = "choice"                        # "bool" or "choice"
    options: tuple[str, ...] = ()               # the declared answer space (choice)
    descriptions: Mapping[str, str] = field(default_factory=dict)
    context: str = ""                           # instructions from the context object (schema, rules)
    truth: Any = None                           # ground truth, for experiments only


@dataclass
class Answer:
    value: Any
    confidence: float
    source: str
    ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    simulated: bool = False
    error: str = ""
    raw: Any = None

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


class Checker(Protocol):
    name: str

    def check(self, q: Question) -> Answer | None: ...


class CodeChecker:
    """Wrap a function ``fn(question) -> (value, confidence) | None``. None means "can't decide"."""

    def __init__(self, name: str, fn: Callable[[Question], tuple[Any, float] | None]):
        self.name, self.fn = name, fn

    def check(self, q: Question) -> Answer | None:
        t0 = time.perf_counter()
        out = self.fn(q)
        ms = (time.perf_counter() - t0) * 1000
        if out is None:
            return None
        value, conf = out
        return Answer(value, conf, self.name, ms)


@dataclass
class SimulatedChecker:
    """A stand-in for a model, driven entirely by declared assumptions.

    * ``accuracy``: chance of the right answer when the information *is* in the text.
    * ``guess_rate``: when it is *not* in the text, chance the model invents an answer
      instead of saying ``not_stated``.
    * ``context_effect``: multiplier on ``guess_rate`` when the question carries
      context-object instructions (``Question.context``). 0.2 means it guesses one
      fifth as often.
    * ``calibrated``: whether its confidence is lower when it is wrong.
    """

    name: str
    accuracy: float = 0.9
    guess_rate: float = 0.7
    context_effect: float = 0.2
    calibrated: bool = True
    latency_ms: float = 400.0
    tokens_overhead: int = 120
    tokens_out: int = 12
    price_in: float = 1.0          # dollars per million input tokens
    price_out: float = 5.0         # dollars per million output tokens
    seed: int = 0

    def check(self, q: Question) -> Answer:
        rng = random.Random(f"{self.seed}|{self.name}|{q.id}|{q.text}|{bool(q.context)}")
        options = list(q.options) if q.kind == "choice" else [True, False]
        wrong = [o for o in options if o != q.truth and o != NOT_STATED] or options
        guess = self.guess_rate * (self.context_effect if q.context else 1.0)
        if q.truth == NOT_STATED:
            if rng.random() < guess:
                value, correct = rng.choice(wrong), False
            else:
                value, correct = NOT_STATED, True
        else:
            correct = rng.random() < self.accuracy
            value = q.truth if correct else rng.choice(wrong)
        if correct:
            conf = rng.uniform(0.82, 0.99)
        else:
            conf = rng.uniform(0.35, 0.75) if self.calibrated else rng.uniform(0.8, 0.97)
        tin = self.tokens_overhead + len(q.text) // 4 + len(q.context) // 4
        ms = self.latency_ms * rng.uniform(0.7, 1.3)
        cost = tin * self.price_in / 1e6 + self.tokens_out * self.price_out / 1e6
        return Answer(value, round(conf, 3), self.name, round(ms, 1), tin, self.tokens_out, cost, simulated=True)


@dataclass
class LadderResult:
    verdict: str                     # "ACT" or "ASK"
    answer: Answer | None            # the answer acted on (None when asking)
    steps: list[Answer]
    reason: str

    @property
    def ms(self) -> float:
        return sum(a.ms for a in self.steps)

    @property
    def tokens(self) -> int:
        return sum(a.tokens for a in self.steps)

    @property
    def cost(self) -> float:
        return sum(a.cost for a in self.steps)

    @property
    def decided_by(self) -> str:
        return self.answer.source if self.answer else "person"


class Ladder:
    def __init__(self, checkers: Iterable[Checker], threshold: float = 0.8):
        self.checkers = list(checkers)
        self.threshold = threshold

    def run(self, q: Question) -> LadderResult:
        steps: list[Answer] = []
        for c in self.checkers:
            a = c.check(q)
            if a is None:
                continue
            steps.append(a)
            if a.error or a.confidence < self.threshold:
                continue
            if a.value == NOT_STATED:
                return LadderResult("ASK", None, steps, f"{a.source}: the information isn't there, so ask")
            return LadderResult("ACT", a, steps, f"{a.source} answered with confidence {a.confidence:.2f}")
        return LadderResult("ASK", None, steps, "no rung was confident enough, so ask a person")
