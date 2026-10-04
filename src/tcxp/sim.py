"""Organization simulator: how a Dark facet propagates through hand-offs.

Everything about a run is in its address, so a link reproduces it exactly:

    !tcxp:/sim/org?agents=10&ambiguity=0.3&cycles=3&decisions_per_task=3&employees=50&gate=false&seed=42&steps_max=7&steps_min=2&tasks=20

What happens:

1. **Ground truth is chosen up front** (seeded). For each decision, the sender
   really means one date format, ``MM/DD`` or ``DD/MM``.
2. The message passes through ``steps_min``-``steps_max`` hand-offs between people
   and agents across teams (engineering → legal → marketing → back…).
3. If the structure facet is **Lit** (the format travels with the data, as an
   address), every reader reads it right. If it is **Dark**, each reader guesses,
   and **interpretation becomes intent**: the next hop inherits the guess.
4. The final reader decides. A wrong reading is a silent error: nobody saw it,
   so it shows up only as regret (``cost_error``).
5. With ``gate=true``, a Dark essential facet is asked about at the first hop
   (``ask_cost``) and the answer is recorded, so later cycles start Lit.

Each hop emits an event whose address is a snapshot: the lightning bolt.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Iterator

from .address import Address
from .trace import Trace

__all__ = ["SimConfig", "HELP", "STORIES", "story", "parse_teams", "Organization", "SimResult", "Hop", "TEAMS", "FORMATS"]

TEAMS = ("engineering", "finance", "legal", "marketing", "operations")
FORMATS = ("MM/DD", "DD/MM")
_STRUCTURE = {"MM/DD": "!tcxp:/schema/date/mm-dd-yyyy", "DD/MM": "!tcxp:/schema/date/dd-mm-yyyy"}


HELP = {
    "employees": "people in the organization who pass work along",
    "agents": "AI agents in the organization who pass work along",
    "tasks": "pieces of work started per cycle (e.g. one tax filing)",
    "decisions_per_task": "decisions each task needs (e.g. which year, which country, which costs)",
    "steps_min": "fewest hand-offs a decision passes through",
    "steps_max": "most hand-offs a decision passes through",
    "cycles": "how many times the same kind of work repeats (later cycles can reuse answers)",
    "ambiguity": "0-1: chance a hand-off arrives without its format stated (the facet is Dark)",
    "gate": "ask a person when an essential fact is Dark, instead of guessing",
    "share_resolutions": "once someone answers, later cycles reuse that answer",
    "cost_error": "dollar cost of one silent wrong decision",
    "ask_cost": "dollar cost of stopping to ask a person once",
    "seed": "random seed: the same seed gives the same organization and the same run",
    "teams": "name:size:ambiguity,... e.g. marketing:2000:0.5,engineering:2000:0.2 "
             "(replaces employees/agents; each team misreads at its own rate)",
}


def parse_teams(spec: str) -> list[tuple[str, int, float]]:
    """``"marketing:2000:0.5,engineering:2000:0.2"`` → [("marketing", 2000, 0.5), ...]."""
    out: list[tuple[str, int, float]] = []
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        bits = part.split(":")
        if len(bits) != 3 or not bits[0].replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"team {part!r}: expected name:size:ambiguity, e.g. marketing:2000:0.5")
        name, size, amb = bits[0], int(bits[1]), float(bits[2])
        if size < 1 or not 0 <= amb <= 1:
            raise ValueError(f"team {name!r}: size must be at least 1 and ambiguity between 0 and 1")
        if any(name == n for n, _, _ in out):
            raise ValueError(f"team {name!r} is listed twice")
        out.append((name, size, amb))
    return out


@dataclass(frozen=True)
class SimConfig:
    employees: int = 50
    agents: int = 10
    tasks: int = 20
    decisions_per_task: int = 3
    steps_min: int = 2
    steps_max: int = 7
    cycles: int = 3
    ambiguity: float = 0.3           # chance the structure facet is Dark on a new message
    gate: bool = False               # ask when an essential facet is Dark
    share_resolutions: bool = True   # a recorded answer is reused in later cycles
    cost_error: float = 1000.0
    ask_cost: float = 5.0
    seed: int = 42
    teams: str = ""                  # name:size:ambiguity,...  (empty = employees/agents across TEAMS)

    def __post_init__(self) -> None:
        if self.teams:
            if sum(n for _, n, _ in parse_teams(self.teams)) < 2:
                raise ValueError("Need at least two participants")
        elif self.employees + self.agents < 2:
            raise ValueError("Need at least two participants")
        if not (1 <= self.steps_min <= self.steps_max):
            raise ValueError("Need 1 <= steps_min <= steps_max")
        if not (0 <= self.ambiguity <= 1):
            raise ValueError("ambiguity is between 0 and 1")

    def to_address(self) -> Address:
        d = asdict(self)
        if not d["teams"]:
            d.pop("teams")
        else:                                  # teams replace these, so they would only mislead
            for k in ("employees", "agents", "ambiguity"):
                d.pop(k)
        return Address.build("sim/org", d)

    @classmethod
    def from_address(cls, address: Address | str) -> "SimConfig":
        a = address if isinstance(address, Address) else Address.parse(address)
        kw: dict[str, Any] = {}
        for f in fields(cls):
            v = a.get(f.name)
            if v is None:
                continue
            if f.type in ("bool", bool):
                kw[f.name] = v == "true"
            elif f.type in ("float", float):
                kw[f.name] = float(v)
            elif f.type in ("str", str):
                kw[f.name] = v
            else:
                kw[f.name] = int(v)
        return cls(**kw)


@dataclass(frozen=True)
class Hop:
    index: int
    cycle: int
    task: int
    decision: int
    step: int
    sender: str
    receiver: str
    sender_team: str
    receiver_team: str
    truth: str
    intent: str
    read: str
    lit: bool
    asked: bool

    def address(self) -> Address:
        return Address.build("sim/hop", {
            "index": self.index, "cycle": self.cycle, "task": self.task, "decision": self.decision, "step": self.step,
            "from": self.sender, "to": self.receiver, "intent": self.intent, "read": self.read, "truth": self.truth,
            "date.structure": _STRUCTURE[self.intent] if self.lit else "", "asked": self.asked})


@dataclass
class SimResult:
    config: SimConfig
    hops: list[Hop] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def metrics(self) -> dict[str, Any]:
        n = len(self.outcomes)
        wrong = sum(not o["correct"] for o in self.outcomes)
        asks = sum(o["asked"] for o in self.outcomes)
        regret = wrong * self.config.cost_error
        ask_cost = asks * self.config.ask_cost
        return {"decisions": n, "correct": n - wrong, "silent_errors": wrong,
                "accuracy": (n - wrong) / n if n else 0.0, "asks": asks,
                "regret": regret, "ask_cost": ask_cost, "total_cost": regret + ask_cost,
                "hops": len(self.hops), "dark_hops": sum(not h.lit for h in self.hops),
                "mean_steps": len(self.hops) / n if n else 0.0}

    def by_team(self) -> list[dict[str, Any]]:
        """Outcomes grouped by the team where each decision started."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for o in self.outcomes:
            groups.setdefault(o["team"], []).append(o)
        rows = []
        for team, os_ in sorted(groups.items()):
            wrong = sum(not o["correct"] for o in os_)
            rows.append({"team": team, "decisions": len(os_), "silent_errors": wrong, "asks": sum(o["asked"] for o in os_),
                         "accuracy": (len(os_) - wrong) / len(os_), "regret": wrong * self.config.cost_error})
        return rows

    def to_trace(self) -> Trace:
        """Every hop as a trace row, for playback with ``tcxp play``. Time is a sim label."""
        labels = iter([f"cycle-{h.cycle}/hop-{h.index}" for h in self.hops])
        t = Trace(clock=lambda: next(labels))
        for h in self.hops:
            t.append("trigger", "hop", h.read, f"actor:{h.sender}", h.address())
        return t


class Organization:
    def __init__(self, config: SimConfig | Address | str | None = None, **overrides: Any):
        if config is None:
            config = SimConfig(**overrides)
        elif not isinstance(config, SimConfig):
            config = SimConfig.from_address(config)
        self.config = config
        rng = random.Random(f"actors|{config.seed}")
        if config.teams:
            spec = parse_teams(config.teams)
            self.actors = [(f"{name}-{i}", name) for name, size, _ in spec for i in range(size)]
            self.ambiguity = {name: amb for name, _, amb in spec}
        else:
            self.actors = [(f"employee-{i}", rng.choice(TEAMS)) for i in range(config.employees)] + \
                          [(f"agent-{i}", rng.choice(TEAMS)) for i in range(config.agents)]
            self.ambiguity = {t: config.ambiguity for t in TEAMS}

    def stream(self) -> Iterator[Hop]:
        """Yield hops one at a time (the event stream)."""
        yield from self.run().hops

    def run(self) -> SimResult:
        c = self.config
        rng = random.Random(f"run|{c.seed}")
        truths = {(t, d): rng.choice(FORMATS) for t in range(c.tasks) for d in range(c.decisions_per_task)}
        resolved: set[tuple[int, int]] = set()
        result = SimResult(c)
        index = 0
        for cycle in range(c.cycles):
            for (t, d), truth in truths.items():
                # one RNG for the case (Dark draw, path) and one for guesses, so a gated and an
                # ungated run share the same ground truth, paths and Dark draws: the gate is the only difference
                case = random.Random(f"case|{c.seed}|{cycle}|{t}|{d}")
                guess = random.Random(f"guess|{c.seed}|{cycle}|{t}|{d}")
                u = case.random()
                steps = case.randint(c.steps_min, c.steps_max)
                si = case.randrange(len(self.actors))
                sender = self.actors[si]
                origin = sender[1]
                lit = (t, d) in resolved or not u < self.ambiguity[origin]   # the origin team's misreading rate
                asked = False
                if not lit and c.gate:
                    asked, lit = True, True
                if asked and c.share_resolutions:   # a confirmed answer is recorded and reused
                    resolved.add((t, d))
                intent = truth
                n = len(self.actors)
                for step in range(steps):
                    ri = case.randrange(n - 1)      # anyone but the sender (same draw as choosing from the others)
                    ri += ri >= si
                    receiver = self.actors[ri]
                    read = intent if lit else guess.choice(FORMATS)
                    result.hops.append(Hop(index, cycle, t, d, step, sender[0], receiver[0], sender[1], receiver[1],
                                           truth, intent, read, lit, asked and step == 0))
                    index += 1
                    intent, sender, si = read, receiver, ri   # interpretation becomes intent
                result.outcomes.append({"cycle": cycle, "task": t, "decision": d, "team": origin, "truth": truth, "final": intent,
                                        "correct": intent == truth, "asked": asked, "steps": steps})
        return result


# ---------- stories: named scenarios, each just a sim address ----------
STORIES: dict[str, tuple[str, str]] = {
    "launch": ("A 6,000-person product launch: marketing, engineering and product each misread the date format "
               "at their own rate.",
               "!tcxp:/sim/org?teams=marketing:2000:0.5,engineering:2000:0.2,product:2000:0.35"
               "&tasks=40&decisions_per_task=3&steps_min=3&steps_max=9&cycles=3&cost_error=50000&ask_cost=25"),
    "section41": ("The Section 41 hand-off: engineers report project dates, finance and tax turn them into a credit.",
                  "!tcxp:/sim/org?teams=engineering:200:0.5,finance:30:0.25,tax:5:0.1"
                  "&tasks=25&decisions_per_task=3&steps_min=2&steps_max=6&cycles=4&cost_error=25000&ask_cost=10"),
    "merger": ("Two companies merge with opposite date conventions and nothing written down.",
               "!tcxp:/sim/org?teams=legacy:500:0.6,acquirer:500:0.1"
               "&tasks=30&decisions_per_task=2&steps_min=2&steps_max=8&cycles=3&cost_error=10000&ask_cost=5"),
    "agent-swarm": ("Ten people supervising 500 agents that pass work to each other.",
                    "!tcxp:/sim/org?teams=people:10:0.2,agents:500:0.4"
                    "&tasks=50&decisions_per_task=2&steps_min=4&steps_max=12&cycles=3&cost_error=2000&ask_cost=1"),
    "startup": ("A 12-person startup where everyone mostly shares context.",
                "!tcxp:/sim/org?teams=founders:3:0.05,team:9:0.15"
                "&tasks=10&decisions_per_task=2&steps_min=1&steps_max=3&cycles=3&cost_error=5000&ask_cost=5"),
}


def story(name: str, **overrides: Any) -> SimConfig:
    """A named scenario as a SimConfig; keyword overrides change single settings."""
    if name not in STORIES:
        raise LookupError(f"No story {name!r}. Stories: {', '.join(STORIES)}")
    base = SimConfig.from_address(STORIES[name][1])
    return SimConfig(**{**asdict(base), **{k: v for k, v in overrides.items() if v is not None}})
