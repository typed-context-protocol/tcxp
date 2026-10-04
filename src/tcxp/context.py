"""Context objects and Observatrons.

* A **context object** is the plan: plain data with five lists,
  ``observe`` (sensors), ``intent`` (what the people involved confirmed they mean, and
  which handlers that allows), ``reason`` (rules), ``decision`` (verdicts) and ``trace``
  (every address it has had). Its current state is one Address.
* **Intent map vs. registry.** The registry is shared and says what *can* run: every
  handler that exists. The intent map belongs to one context object and says what *this
  decision meant* to run. ``ctx.call("@sql.run?...")`` runs a handler only when both
  agree: it is registered, and a confirmed intent allows it. Built-in ``@core.*``
  handlers act only on the context object itself and are always allowed.
* An **Observatron** is a context object switched on: mounted on something (a text
  box, by its id) and wired to an event bus. The context object is the sheet music;
  the Observatron is the musician playing it.
* A **Sensor** is one entry in ``observe``: "watch for the word *yesterday*".
* A **Spike** (see ``facets.py``) is one firing of one sensor.

Flow on every input: observe (sensors fire spikes) → intent (their ``@`` actions run
through the intent gate and update the address) → reason → decision (the Governor
returns ACT / ASK / HALT) → trace.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .address import MAX_INLINE, Address, encode
from .bus import EventBus
from .facets import Spike, spikes_in
from .governor import Governor, Rule, Verdict
from .registry import Registry, parse_handler
from .schema import Schema
from .trace import Trace, utc_now

__all__ = ["Sensor", "Intent", "IntentNotAllowed", "ContextObject", "Observatron", "Observation"]

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class IntentNotAllowed(PermissionError):
    """A handler exists, but no confirmed intent in this context object allows calling it."""


@dataclass(frozen=True)
class Intent:
    """One confirmed meaning: what a person said they meant, the keys it sets, the handlers it allows.

    ``allows`` holds handler names (``sql.run``) or prefixes (``sql.*``); never code.
    """

    id: str
    text: str = ""                                   # their words
    means: tuple[tuple[str, str], ...] = ()          # keys this meaning sets, e.g. (("task", "section_41_qre"),)
    allows: tuple[str, ...] = ()                     # handlers it lets this context object call
    by: str = ""                                     # who confirmed it

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.id):
            raise ValueError(f"Intent id {self.id!r} must be lowercase words joined by '-'")
        means = self.means.items() if isinstance(self.means, Mapping) else self.means
        object.__setattr__(self, "means", tuple(sorted((str(k), str(v)) for k, v in means)))
        allows = tuple(a[1:] if a.startswith("@") else a for a in self.allows)
        for a in allows:
            if not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*(?:\.\*)?|\*", a):
                raise ValueError(f"Intent {self.id}: {a!r} is not a handler name or prefix like 'sql.*'")
        object.__setattr__(self, "allows", allows)

    def permits(self, handler: str) -> bool:
        return any(a == "*" or a == handler or (a.endswith(".*") and handler.startswith(a[:-1])) for a in self.allows)

    def address(self) -> Address:
        return Address.build(f"intent/{self.id}", {"text": self.text or None, "by": self.by or None,
                                                    "allows": ["@" + a for a in self.allows],
                                                    **{f"means.{k}": v for k, v in self.means}})

    @classmethod
    def from_address(cls, address: Address | str) -> "Intent":
        a = address if isinstance(address, Address) else Address.parse(address)
        means = tuple((k[6:], a.get(k, "")) for k in a.keys() if k.startswith("means."))
        return cls(a.path[-1], a.get("text", ""), means, tuple(v for v in a.get_all("allows") if v), a.get("by", ""))


@dataclass
class Sensor:
    """One thing to watch for. ``actions`` are ``@handler`` references run when it fires.

    In an action, ``{0}`` is the whole match and ``{1}``, ``{2}``… are regex groups
    (percent-encoded before they are inserted).
    """

    id: str
    pattern: str
    actions: tuple[str, ...] = ()
    kind: str = "regex"              # "regex" or "keyword" (words separated by "|")
    key: str = ""                    # the slot the observed data belongs to
    meaning: tuple[str, ...] = ()
    structure: tuple[str, ...] = ()
    environment: tuple[str, ...] = ()
    color: str = "yellow"
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("regex", "keyword"):
            raise ValueError("Sensor kind is 'regex' or 'keyword'")
        src = r"\b(?:" + "|".join(re.escape(w.strip()) for w in self.pattern.split("|")) + r")\b" \
            if self.kind == "keyword" else self.pattern
        self._re = re.compile(src, re.IGNORECASE)
        self.actions = tuple(self.actions)

    def find(self, text: str) -> list[re.Match]:
        return [m for m in self._re.finditer(text) if m.group(0)]

    def fill(self, action: str, match: re.Match) -> str:
        groups = [match.group(0), *match.groups()]
        return re.sub(r"\{(\d+)\}", lambda m: encode(groups[int(m.group(1))] or "") if int(m.group(1)) < len(groups) else "", action)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Sensor":
        return cls(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})


def _reason_from(text: str) -> Any:
    """A reason entry is a rule (``!tcxp:/rule/…``) or a flow gate (``!tcxp:/gate/…``)."""
    a = Address.parse(text)
    if a.path and a.path[0] == "gate":
        from .flow import Gate
        return Gate.from_address(a)
    return Rule.from_address(a)


class ContextObject:
    """The plan and its state. Every change goes through ``set`` and lands in ``trace``."""

    def __init__(self, path: str = "reason", schema: Schema | None = None,
                 observe: Iterable[Sensor] = (), reason: Iterable[Rule] = (),
                 registry: Registry | None = None, params: Mapping[str, Any] | None = None,
                 clock: Callable[[], str] = utc_now, inline_limit: int = MAX_INLINE,
                 intent: Iterable[Intent] = ()):
        self.registry = registry or Registry()
        self.schema = schema
        self.observe: list[Sensor] = list(observe)
        self.intent: list[Intent] = list(intent)
        self.reason: list[Rule] = list(reason)
        self.decision: list[Verdict] = []
        self.trace = Trace(clock)
        self.inline_limit = inline_limit
        self.address = Address.build(path, params or {})
        # scratch state the built-in handlers write to (reset on each input)
        self.highlights: list[dict[str, Any]] = []
        self.asks: list[str] = []
        self.notes: list[str] = []
        self.halted: str | None = None
        self.trace.append("set", "", "", "init", self.snapshot())

    # ---------- state ----------
    def snapshot(self) -> str:
        """The current address, or a hash pointer to it when it is too long to inline."""
        text = str(self.address)
        if len(text) <= self.inline_limit:
            return text
        return str(self.registry.put_state({"address": text}))

    def resolve(self, snapshot: str) -> Address:
        """Turn a trace snapshot (inline or pointer) back into an Address."""
        if snapshot.startswith("!tcxp:/state/sha256-"):
            return Address.parse(self.registry.get_state(snapshot)["address"])
        return Address.parse(snapshot)

    def get(self, key: str, default: Any = None) -> Any:
        return self.address.get(key, default)

    def typed(self) -> dict[str, Any]:
        """Schema-typed values (requires a schema)."""
        if not self.schema:
            raise ValueError("This context object has no schema")
        return self.schema.coerce(self.address)

    def set(self, key: str, value: Any, cause: str, learnable: bool = False, features: str = "") -> Any:
        new = self.address.set(key, value)
        if new == self.address and not learnable:
            return None
        self.address = new
        op = "unset" if value is None else "set"
        shown = "" if value is None else (value if isinstance(value, str) else ",".join(new.get_all(key)))
        return self.trace.append(op, key, shown, cause, self.snapshot(), learnable, features)

    def update(self, values: Mapping[str, Any], cause: str) -> list[Any]:
        return [r for k, v in values.items() if (r := self.set(k, v, cause)) is not None]

    def confirm(self, key: str, value: Any, by: str = "person", features: str | None = None) -> Any:
        """A person supplied this value. The row is marked learnable (a labeled example)."""
        return self.set(key, value, f"person:{by}", learnable=True,
                        features=features if features is not None else self.address.get("query", ""))

    def spikes(self) -> list[Spike]:
        return spikes_in(self.address)

    # ---------- intent ----------
    def add_intent(self, intent: Intent | str, means: Mapping[str, Any] | None = None,
                   allows: Iterable[str] = (), by: str = "", text: str = "") -> Intent:
        """Record a confirmed meaning: set the keys it means, allow the handlers it needs.

        Confirmed by a person (``by``), it is also a labeled example (text → intent id)
        that the perceptron can learn from.
        """
        it = intent if isinstance(intent, Intent) else (
            Intent.from_address(intent) if intent.startswith(("!", "tcxp:")) else
            Intent(intent, text, tuple((means or {}).items()), tuple(allows), by))
        self.intent = [x for x in self.intent if x.id != it.id] + [it]
        cause = f"intent:{it.id}"
        for k, v in it.means:
            self.set(k, v, cause)
        # the value is the intent id, so a confirmed row is a ready training label: text -> intent
        self.trace.append("trigger", "intent", it.id, f"person:{it.by}" if it.by else cause,
                          self.snapshot(), learnable=bool(it.by), features=it.text)
        return it

    def allowed(self, handler: str) -> Intent | None:
        """The intent that allows this handler (``core.*`` is always allowed), or None."""
        if handler.startswith("core."):
            return Intent("core", allows=("core.*",))
        return next((i for i in reversed(self.intent) if i.permits(handler)), None)

    def call(self, ref: str, cause: str = "", **extra: Any) -> Any:
        """Run ``@handler?args`` through the intent gate, then the registry. Recorded in the trace."""
        name, _ = parse_handler(ref)
        it = self.allowed(name)
        if it is None:
            self.trace.append("refuse", name, ref, cause or "intent-gate", self.snapshot())
            raise IntentNotAllowed(f"No intent in this context object allows @{name}; "
                                   f"add one that does (e.g. allows=['{name}'])")
        result = self.registry.trigger(ref, self, **extra, **({"_cause": cause} if cause else {}))
        if it.id != "core":           # core handlers record their own effects
            shown = result if isinstance(result, (str, int, float, bool)) or result is None else type(result).__name__
            self.trace.append("trigger", name, "" if shown is None else str(shown), cause or f"intent:{it.id}",
                              self.snapshot())
        return result

    # ---------- reasoning ----------
    def add_rule(self, rule: Rule | str, **compile_kw: Any) -> Rule:
        r = rule if isinstance(rule, Rule) else (Rule.from_address(rule) if rule.startswith(("!", "tcxp:"))
                                                 else Rule.compile(rule, **compile_kw))
        self.reason = [x for x in self.reason if x.id != r.id] + [r]
        self.trace.append("trigger", "rule", str(r.address()), "rule:add", self.snapshot())
        return r

    def decide(self, action: str = "answer") -> Verdict:
        if self.halted:
            v = Verdict("HALT", action, (), (), f"HALT: {self.halted}")
        else:
            v = Governor([r for r in self.reason if isinstance(r, Rule)], self.schema).evaluate(self.address, action)
            if v.kind == "HALT":
                self.halted = v.message      # HALT is absorbing: later inputs cannot lower it
        self.decision.append(v)
        for k in v.missing:
            if k not in self.asks:
                self.asks.append(k)
        self.trace.append("decide", action, v.kind, "governor", self.snapshot())
        return v

    # ---------- persistence ----------
    def to_dict(self) -> dict[str, Any]:
        return {"address": str(self.address), "schema": self.schema.to_dict() if self.schema else None,
                "observe": [s.to_dict() for s in self.observe], "intent": [str(i.address()) for i in self.intent],
                "reason": [str(r.address()) for r in self.reason],
                "decision": [str(v.address()) for v in self.decision], "halted": self.halted,
                "inline_limit": self.inline_limit, "trace": self.trace.to_dicts(),
                "trace_head": self.trace.last_hash, "trace_rows": len(self.trace)}

    def save(self) -> Address:
        """Store the whole context object; returns its content-addressed pointer."""
        return self.registry.put_state(self.to_dict())

    @classmethod
    def load(cls, data: Mapping[str, Any] | Address | str, registry: Registry | None = None) -> "ContextObject":
        registry = registry or Registry()
        if not isinstance(data, Mapping):
            data = registry.get_state(data)
        addr = Address.parse(data["address"])
        obj = cls(addr.path_text, Schema.from_dict(data["schema"]) if data.get("schema") else None,
                  [Sensor.from_dict(s) for s in data["observe"]], [_reason_from(r) for r in data["reason"]],
                  registry)
        obj.address = addr
        obj.intent = [Intent.from_address(i) for i in data.get("intent", [])]
        obj.trace = Trace.from_dicts(data["trace"])
        obj.halted = data.get("halted")
        obj.inline_limit = int(data.get("inline_limit", MAX_INLINE))
        obj.decision = [Verdict(a.get("kind", ""), a.get("action", ""), tuple(v for v in a.get_all("missing") if v),
                                tuple(v for v in a.get_all("rule") if v))
                        for a in (Address.parse(d) for d in data.get("decision", []))]
        problems = obj.integrity_problems(data)
        if problems:
            raise ValueError("Context object failed its integrity check: " + "; ".join(problems))
        return obj

    def integrity_problems(self, saved: Mapping[str, Any] | None = None) -> list[str]:
        """Everything that would make this context object untrustworthy (empty list = intact).

        Checks the trace's hash chain and state pointers, that the current address is the
        trace's last snapshot, and (when given saved metadata) that no rows were cut off the end.
        """
        problems = self.trace.verify(self.registry)
        if self.trace.rows:
            try:
                last = self.resolve(self.trace.rows[-1].address)
                if last != self.address:
                    problems.append("the current address is not the trace's last snapshot")
            except Exception as exc:
                problems.append(f"the last snapshot cannot be resolved: {exc}")
        if saved is not None:
            if "trace_rows" in saved and int(saved["trace_rows"]) != len(self.trace):
                problems.append(f"trace has {len(self.trace)} rows but {saved['trace_rows']} were saved")
            if "trace_head" in saved and saved["trace_head"] != self.trace.last_hash:
                problems.append("trace head hash does not match the saved head")
        return problems


@dataclass
class Observation:
    text: str
    spikes: list[Spike]
    highlights: list[dict[str, Any]]
    verdict: Verdict
    address: Address
    asks: list[str] = field(default_factory=list)


class Observatron:
    """A context object mounted on an input and wired to an event bus.

    Events emitted: ``mount``, ``spike``, ``decision``. ``debounce_ms`` applies to
    ``keystroke`` / ``tick`` (simulated typing); ``feed`` processes immediately.
    """

    def __init__(self, context: ContextObject, target: str = "query", bus: EventBus | None = None,
                 action: str = "answer", debounce_ms: int = 300):
        self.context = context
        self.target = target
        self.bus = bus or EventBus()
        self.action = action
        self.debounce_ms = debounce_ms
        self._pending: tuple[str, int] | None = None
        self.bus.emit("mount", {"target": target, "address": str(context.address)})

    def feed(self, text: str) -> Observation:
        """Observe the text, then let the Governor decide."""
        found = self.observe(text)
        ctx = self.context
        verdict = ctx.decide(self.action)
        self.bus.emit("decision", verdict)
        return Observation(text, found, list(ctx.highlights), verdict, ctx.address, list(ctx.asks))

    def observe(self, text: str) -> list[Spike]:
        """Only the sensing half: set the input, fire sensors, run their actions. No decision."""
        ctx = self.context
        ctx.highlights.clear()
        ctx.asks.clear()
        ctx.set(self.target, text, f"input:{self.target}")
        found: list[Spike] = []
        for sensor in ctx.observe:
            for m in sensor.find(text):
                spike = Spike(sensor.key or sensor.id, m.group(0), sensor.meaning, sensor.structure,
                              sensor.environment, sensor.id, self.target, m.start(), m.end(), ctx.trace.clock())
                found.append(spike)
                ctx.trace.append("trigger", sensor.id, m.group(0), f"sensor:{sensor.id}", ctx.snapshot())
                self.bus.emit("spike", spike)
                for action in sensor.actions:
                    ctx.call(sensor.fill(action, m), f"sensor:{sensor.id}", _spike=spike)
        return found

    # simulated typing with a debounce
    def keystroke(self, text: str, t_ms: int) -> None:
        self._pending = (text, t_ms)

    def tick(self, t_ms: int) -> Observation | None:
        if self._pending and t_ms - self._pending[1] >= self.debounce_ms:
            text, _ = self._pending
            self._pending = None
            return self.feed(text)
        return None
