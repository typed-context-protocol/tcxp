"""Fleet: many Observatrons, one stream of requests, with and without context objects.

Answers the question: once the system has collected confirmed answers, **how useful are
they?** How good does inference get, what does it cost, and how much risk is taken when
the system acts instead of asking?

Every request has ground truth (is the tax year stated, and which one). The same request
stream runs through four arms:

=================  ==============================================================
llm_alone          the LLM answers; its answer is acted on (no context object)
jev_alone          Jev answers; its top choice is acted on (no context object)
context            code → Jev → LLM with the context object's rules; ask below the threshold
context_learning   perceptron guard dogs first, then the context ladder. The guard learns
                   online from confirmed answers (people's answers and code-certain cases),
                   shared across the whole fleet. It can also **veto**: if it is confident the
                   year isn't stated while a model names one, the system asks instead.
=================  ==============================================================

Per epoch (a slice of time) each arm reports: correct, silent errors, asks, who decided,
model cost, ask cost, realized regret, **risk taken** (the regret the arm's own confidence
predicted for the decisions it acted on), and for the learning arm the guard's coverage,
confident accuracy and confidence histogram (the probability density over time).

``share=False`` gives every Observatron its own guard instead of one shared guard, which
shows why pooling confirmed answers across a fleet matters.

Simulated rungs use the declared assumptions in ``tcxp.bench`` (SIM_JEV, SIM_LLM). With
``mode="real"`` the same arms call Jev and Claude; use ``limit`` to cap spend.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Iterator

from .address import Address
from .bench import CONTEXT_RULES, OPTIONS, SIM_JEV, SIM_LLM, detect_tax_year
from .ladder import NOT_STATED, Answer, CodeChecker, Ladder, Question, SimulatedChecker
from .learn import SoftmaxPerceptron

__all__ = ["FleetConfig", "Fleet", "FleetResult", "Request", "generate_requests", "ARMS"]

ARMS = ("llm_alone", "jev_alone", "context", "context_learning")

_STATED = ["What were our QREs for tax year {y}?", "Calculate the R&D credit for FY{yy}.",
           "For our {y} return, what qualifies under section 41?", "Section 41 credit for the {y} tax year, please.",
           "We're filing for {y}; total the research wages.", "Tax year {y}: how much can we deduct?",
           "Run the {y} filing numbers for the R&D credit."]
_HIDDEN = ["Use the {y} numbers to figure the section 41 credit.", "Figure the {y} R&D credit for us.",
           "Our {y} section 41 claim: what's the total?", "Pull {y} research costs for the credit."]
_NOT = ["How much should I deduct for Section 41 US-based QREs?", "What R&D credit can we take?",
        "Total the qualified research wages.", "How much did we spend on research last year?",
        "Estimate our section 41 deduction.", "What counts as a QRE for us?", "What can engineering wages add to the credit?"]
_TRAPS = ["The {p} project started in {y}. How much can we claim?", "We launched {p} in {y}; what's deductible?",
          "Payroll for {p} began in {y}. What's the credit?", "{p} kicked off in {y}. Estimate the R&D deduction."]
# phrasings that only appear after the drift point: the guard has never seen them
_STATED_NEW = ["Book the {y} research credit against this year's return.", "Our TY{yy} R&D: what's the number?",
               "Close out the {y} filing; what QREs do we report?"]
_HIDDEN_NEW = ["Redo the {y} research credit with the corrected wages.", "Give me {y}'s section 41 figure."]
_NOT_NEW = ["Before we file, how big is the research credit?", "What's our total qualifying research spend?",
            "Can contractor costs count toward the deduction?"]
_TRAPS_NEW = ["{p} went live in {y}. What can we write off?", "Since {p} launched in {y}, what's our credit?"]
_PROJECTS = ["Atlas", "Beacon", "Comet", "Delta", "Ember", "Falcon"]
_YEARS = ("2023", "2024", "2025")


@dataclass(frozen=True)
class Request:
    index: int
    observatron: int
    epoch: int
    text: str
    truth: str          # a year, or "not_stated"
    kind: str           # stated | hidden | not_stated | trap


def generate_requests(n_observatrons: int, per: int, epochs: int, stated_rate: float, hidden_rate: float,
                      trap_rate: float, seed: int, drift_epoch: int | None = None, drift_rate: float = 0.5) -> list[Request]:
    """A seeded stream of requests with ground truth. From ``drift_epoch`` on, ``drift_rate`` of them use new phrasings."""
    rng = random.Random(f"requests|{seed}")
    total = n_observatrons * per
    out = []
    for i in range(total):
        epoch = min(epochs - 1, i * epochs // total)
        novel = drift_epoch is not None and epoch >= drift_epoch and rng.random() < drift_rate
        y = rng.choice(_YEARS)
        r = rng.random()
        if r < stated_rate * (1 - hidden_rate):
            kind, text, truth = "stated", rng.choice(_STATED_NEW if novel else _STATED).format(y=y, yy=y[2:]), y
        elif r < stated_rate:
            kind, text, truth = "hidden", rng.choice(_HIDDEN_NEW if novel else _HIDDEN).format(y=y), y
        elif r < stated_rate + (1 - stated_rate) * trap_rate:
            kind, text, truth = "trap", rng.choice(_TRAPS_NEW if novel else _TRAPS).format(y=y, p=rng.choice(_PROJECTS)), NOT_STATED
        else:
            kind, text, truth = "not_stated", rng.choice(_NOT_NEW if novel else _NOT), NOT_STATED
        out.append(Request(i, i % n_observatrons, epoch, text, truth, kind + ("+new" if novel else "")))
    return out


@dataclass(frozen=True)
class FleetConfig:
    observatrons: int = 10000
    requests_per: int = 3
    epochs: int = 10
    stated_rate: float = 0.5
    hidden_rate: float = 0.25        # stated in words code can't parse ("the 2024 numbers")
    trap_rate: float = 0.3           # a year is present but it isn't the tax year
    cost_error: float = 1000.0
    ask_cost: float = 5.0
    threshold: float = 0.8           # ladder rungs act at or above this confidence
    guard_threshold: float = 0.9     # the guard acts (or vetoes) at or above this
    share: bool = True               # one guard for the whole fleet
    drift_epoch: int = 5             # new phrasings start appearing at this epoch (-1 = never)
    drift_rate: float = 0.5          # share of requests using new phrasings after the drift
    seed: int = 7

    def __post_init__(self) -> None:
        if self.observatrons < 1 or self.requests_per < 1 or self.epochs < 1:
            raise ValueError("observatrons, requests_per and epochs must each be at least 1")
        for name in ("stated_rate", "hidden_rate", "trap_rate", "drift_rate", "threshold", "guard_threshold"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_address(self) -> Address:
        return Address.build("sim/fleet", asdict(self))

    @classmethod
    def from_address(cls, address: Address | str) -> "FleetConfig":
        a = address if isinstance(address, Address) else Address.parse(address)
        kw: dict[str, Any] = {}
        for f in fields(cls):
            v = a.get(f.name)
            if v is not None:
                kw[f.name] = (v == "true") if f.type in ("bool", bool) else (float(v) if f.type in ("float", float) else int(v))
        return cls(**kw)


@dataclass
class EpochStats:
    epoch: int
    n: int = 0
    correct: int = 0
    silent_errors: int = 0
    asks: int = 0
    extra_asks: int = 0
    vetoes: int = 0
    vetoes_right: int = 0
    by: dict[str, int] = field(default_factory=dict)
    model_cost: float = 0.0
    model_ms: float = 0.0
    risk_taken: float = 0.0          # Σ (1 - confidence) × cost_error over decisions acted on
    guard_confident: int = 0
    guard_confident_right: int = 0
    labels: int = 0
    guard_novel: int = 0             # guard acted alone on a phrasing it had never seen
    guard_novel_right: int = 0
    hist: list[int] = field(default_factory=lambda: [0] * 10)   # guard top-confidence density

    def regret(self, cost_error: float) -> float:
        return self.silent_errors * cost_error


@dataclass
class FleetResult:
    config: FleetConfig
    epochs: dict[str, list[EpochStats]]
    limited_to: int | None = None

    def totals(self, arm: str) -> dict[str, Any]:
        es, c = self.epochs[arm], self.config
        n = sum(e.n for e in es)
        silent = sum(e.silent_errors for e in es)
        asks = sum(e.asks for e in es)
        model_cost = sum(e.model_cost for e in es)
        by: dict[str, int] = {}
        for e in es:
            for k, v in e.by.items():
                by[k] = by.get(k, 0) + v
        regret, ask_cost = silent * c.cost_error, asks * c.ask_cost
        return {"arm": arm, "decisions": n, "accuracy": sum(e.correct for e in es) / n if n else 0.0,
                "silent_errors": silent, "asks": asks, "extra_asks": sum(e.extra_asks for e in es),
                "vetoes": sum(e.vetoes for e in es), "vetoes_right": sum(e.vetoes_right for e in es),
                "model_cost": model_cost, "ask_cost": ask_cost, "regret": regret,
                "total_cost": regret + ask_cost + model_cost, "risk_taken": sum(e.risk_taken for e in es),
                "decided_by": by, "labels": sum(e.labels for e in es),
                "guard_acted": sum(e.guard_confident for e in es),
                "guard_accuracy": (sum(e.guard_confident_right for e in es) / max(1, sum(e.guard_confident for e in es))),
                "guard_novel_acted": sum(e.guard_novel for e in es),
                "guard_novel_accuracy": (sum(e.guard_novel_right for e in es) / max(1, sum(e.guard_novel for e in es)))}

    def delta(self) -> dict[str, float]:
        """Context with learning versus the LLM alone: what the typed context object changes."""
        a, b = self.totals("llm_alone"), self.totals("context_learning")
        return {k: b[k] - a[k] for k in ("accuracy", "silent_errors", "asks", "model_cost", "regret", "total_cost", "risk_taken")}


class _Guard:
    """Perceptron guard dogs: one shared model, or one per Observatron."""

    def __init__(self, share: bool):
        self.share = share
        self.models: dict[int, SoftmaxPerceptron] = {}

    def model(self, obs: int) -> SoftmaxPerceptron:
        key = 0 if self.share else obs
        if key not in self.models:
            self.models[key] = SoftmaxPerceptron(list(OPTIONS), dim=512, lr=0.4)
        return self.models[key]


class Fleet:
    def __init__(self, config: FleetConfig | Address | str | None = None, mode: str = "simulated",
                 limit: int | None = None, jev_key: str | None = None, claude_key: str | None = None, **overrides: Any):
        if config is None:
            config = FleetConfig(**overrides)
        elif not isinstance(config, FleetConfig):
            config = FleetConfig.from_address(config)
        self.config, self.mode, self.limit = config, mode, limit
        c = config
        self.requests = generate_requests(c.observatrons, c.requests_per, c.epochs, c.stated_rate, c.hidden_rate,
                                          c.trap_rate, c.seed, None if c.drift_epoch < 0 else c.drift_epoch, c.drift_rate)
        if limit is not None:
            self.requests = self.requests[:max(0, limit)]
        if mode == "real":
            from .models import ClaudeChecker, JevChecker
            self.jev, self.llm = JevChecker(jev_key), ClaudeChecker(claude_key)
        else:
            self.jev = SimulatedChecker("jev", seed=c.seed, **SIM_JEV)
            self.llm = SimulatedChecker("llm", seed=c.seed, **SIM_LLM)
        self.code = CodeChecker("code", lambda q: (detect_tax_year(q.text), 1.0) if detect_tax_year(q.text) else None)

    def _question(self, r: Request, ctx: bool) -> Question:
        return Question(f"r{r.index}", r.text, "Which tax year is this request for?", "choice", OPTIONS,
                        context=CONTEXT_RULES if ctx else "", truth=r.truth)

    def run(self) -> FleetResult:
        c = self.config
        out: dict[str, list[EpochStats]] = {a: [EpochStats(e) for e in range(c.epochs)] for a in ARMS}
        guard = _Guard(c.share)
        ladders = {"llm_alone": Ladder([self.llm], 0.0), "jev_alone": Ladder([self.jev], 0.0),
                   "context": Ladder([self.code, self.jev, self.llm], c.threshold)}
        for r in self.requests:
            for arm in ARMS:
                st = out[arm][r.epoch]
                st.n += 1
                if arm == "context_learning":
                    verdict, value, conf, steps, decided = self._learning_step(r, guard, st)
                else:
                    res = ladders[arm].run(self._question(r, arm == "context"))
                    steps = res.steps
                    verdict, decided = res.verdict, res.decided_by
                    value = res.answer.value if res.answer else None
                    conf = res.answer.confidence if res.answer else 0.0
                for a in steps:
                    st.model_cost += a.cost
                    st.model_ms += a.ms
                st.by[decided] = st.by.get(decided, 0) + 1
                if verdict == "ASK":
                    st.asks += 1
                    if r.truth == NOT_STATED:
                        st.correct += 1
                    else:
                        st.extra_asks += 1
                elif value == r.truth:
                    st.correct += 1
                    st.risk_taken += (1 - conf) * c.cost_error
                else:
                    st.silent_errors += 1
                    st.risk_taken += (1 - conf) * c.cost_error
        return FleetResult(c, out, self.limit)

    def _learning_step(self, r: Request, guard: _Guard, st: EpochStats) -> tuple[str, Any, float, list[Answer], str]:
        c = self.config
        model = guard.model(r.observatron)
        steps: list[Answer] = []
        g_value, g_conf = (model.predict(r.text) if model.n_trained else (None, 0.0))
        if model.n_trained:
            st.hist[min(9, int(g_conf * 10))] += 1
        # code is exact and free, so it still goes first
        code = self.code.check(self._question(r, True))
        if code is not None:
            steps.append(code)
            self._learn(model, r.text, code.value, st)
            return "ACT", code.value, 1.0, steps, "code"
        # the guard acts on its own when confident
        if model.n_trained and g_conf >= c.guard_threshold:
            st.guard_confident += 1
            st.guard_confident_right += g_value == r.truth
            if r.kind.endswith("+new"):
                st.guard_novel += 1
                st.guard_novel_right += g_value == r.truth
            if g_value == NOT_STATED:
                return "ASK", None, g_conf, steps, "guard"
            return "ACT", g_value, g_conf, steps, "guard"
        res = Ladder([self.jev, self.llm], c.threshold).run(self._question(r, True))
        steps += res.steps
        # veto: the guard is fairly sure no year is stated, but a model named one
        if res.verdict == "ACT" and model.n_trained and g_value == NOT_STATED and g_conf >= c.guard_threshold * 0.8:
            st.vetoes += 1
            st.vetoes_right += r.truth == NOT_STATED
            res_verdict, value, conf, decided = "ASK", None, g_conf, "guard-veto"
        else:
            res_verdict = res.verdict
            value = res.answer.value if res.answer else None
            conf = res.answer.confidence if res.answer else 0.0
            decided = res.decided_by
        if res_verdict == "ASK":
            # a person answers: that answer is ground truth, recorded as a label
            self._learn(model, r.text, r.truth, st)
        return res_verdict, value, conf, steps, decided

    @staticmethod
    def _learn(model: SoftmaxPerceptron, text: str, label: str, st: EpochStats) -> None:
        model.partial_fit(text, label)
        st.labels += 1

    def stream(self) -> Iterator[Request]:
        yield from self.requests
