"""Decision flows: reasoning cards in plain language become gates you can see, approve and run.

The picture is a process map::

    [ query ] ──▶ ◆ gate: known(tax_year)? ── true ──▶ ◆ next gate … ──▶ [ SQL card ]
                    ▲          │ false
       reasoning card          ▼
     (the manager's words)   @core.ask?key=tax_year   (stops here)

* The **query** box is the user's words. As they type, sensors fill keys in the context
  object's address.
* A **gate** (the diamond) is one yes/no question written in **TQL**, the tcxp query
  language: ``known(tax_year)``, ``has(query, "yesterday")``, ``country = "US"``,
  combined with ``and``/``or``/``not``. A key with no value is Dark: a test that needs it
  is unknown, follows the false branch, and the key is asked for.
* Each gate has two **outcomes**, ``true`` and ``false``. Each outcome is a list of
  ``@handler`` calls (highlight, ask, halt, notify…) and optionally the next gate.
  ``@core.ask`` and ``@core.halt`` stop the flow; other actions let it continue.
* A **reasoning card** is a sentence someone writes ("For Section 41 tax preparation,
  require the tax year"). ``compile_card`` turns it into a gate, or into actions on an
  existing gate's outcome ("If false, alert that we cannot proceed"). Common phrasings
  compile with no model. Others can be proposed by Jev or an LLM through ``proposer``,
  and the proposal is validated like anything typed.
* New gates are **proposed**: shown and evaluated, but their actions don't fire.
  Calling ``@core.approve?gate=<id>&by=<who>`` approves one, which is recorded in the
  trace. Approved gates are permanent until replaced.

Gates are addresses and live in the context object's ``reason`` list beside rules, so a
whole flow saves, loads, replays and diffs like everything else::

    !tcxp:/gate/tax-year?by=manager&card=…&false.do=@core.ask%3Fkey%3Dtax_year&status=approved&test=known(tax_year)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Sequence

from .address import Address, encode
from .registry import parse_handler

__all__ = ["TQLError", "parse_tql", "format_tql", "evaluate", "describe", "flow_demo", "Gate", "Flow", "FlowResult", "Step", "compile_card",
           "CardNotUnderstood", "draw_flow", "PROPOSED", "APPROVED", "STOPPING"]

PROPOSED, APPROVED = "proposed", "approved"
STOPPING = ("core.ask", "core.halt")        # actions that end the flow
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


class TQLError(ValueError):
    pass


class CardNotUnderstood(ValueError):
    pass


# ======================================================================
# TQL: the tcxp query language for one yes/no question
# ======================================================================
#   test   := or
#   or     := and ("or" and)*
#   and    := not ("and" not)*
#   not    := "not" not | atom
#   atom   := "(" test ")" | known(key) | dark(key) | has(key, "text") | key OP value
#   OP     := = != < > <= >=        value := "text" | number
_TOK = re.compile(r'\s*(?:(?P<str>"(?:[^"\\]|\\.)*")|(?P<num>-?\d+(?:\.\d+)?)|(?P<op><=|>=|!=|=|<|>|\(|\)|,)|'
                  r'(?P<word>[A-Za-z_][A-Za-z0-9_.]*))')


def _tokens(text: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = _TOK.match(text, pos)
        if not m or m.end() == pos:
            raise TQLError(f"TQL: unexpected text at {text[pos:pos + 12]!r}")
        out.append((m.lastgroup, m.group(m.lastgroup)))
        pos = m.end()
    return out


def parse_tql(text: str) -> tuple:
    """Parse TQL into a small tuple tree: ("and", a, b), ("known", key), ("cmp", key, op, value)…"""
    toks = _tokens(text)
    i = 0

    def peek(n: int = 0) -> tuple[str, str]:
        return toks[i + n] if i + n < len(toks) else ("end", "")

    def take(kind: str | None = None, value: str | None = None) -> str:
        nonlocal i
        k, v = peek()
        if (kind and k != kind) or (value is not None and v.lower() != value):
            raise TQLError(f"TQL: expected {value or kind}, found {v or 'the end'!r}")
        i += 1
        return v

    def p_or() -> tuple:
        node = p_and()
        while peek()[1].lower() == "or":
            take()
            node = ("or", node, p_and())
        return node

    def p_and() -> tuple:
        node = p_not()
        while peek()[1].lower() == "and":
            take()
            node = ("and", node, p_not())
        return node

    def p_not() -> tuple:
        if peek()[1].lower() == "not":
            take()
            return ("not", p_not())
        return atom()

    def atom() -> tuple:
        k, v = peek()
        if v == "(":
            take()
            node = p_or()
            take("op", ")")
            return node
        if k != "word":
            raise TQLError(f"TQL: expected a test, found {v or 'the end'!r}")
        fn = v.lower()
        if fn in ("known", "dark") and peek(1)[1] == "(":
            take(); take("op", "(")
            key = take("word")
            take("op", ")")
            return (fn, key)
        if fn == "has" and peek(1)[1] == "(":
            take(); take("op", "(")
            key = take("word")
            take("op", ",")
            s = take("str")
            take("op", ")")
            return ("has", key, _unquote(s))
        key = take("word")
        if peek()[1] not in ("=", "!=", "<", ">", "<=", ">="):
            raise TQLError(f"TQL: after {key!r} expected =, !=, <, >, <= or >=")
        op = take("op")
        k2, v2 = peek()
        if k2 == "str":
            take()
            return ("cmp", key, op, _unquote(v2))
        if k2 == "num":
            take()
            return ("cmp", key, op, v2)
        raise TQLError(f"TQL: expected a \"quoted\" value or a number after {op}")

    node = p_or()
    if peek()[0] != "end":
        raise TQLError(f"TQL: unexpected {peek()[1]!r}")
    return node


def _unquote(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s[1:-1])


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def format_tql(node: tuple) -> str:
    """One canonical spelling, so equal tests are equal strings."""
    kind = node[0]
    if kind in ("known", "dark"):
        return f"{kind}({node[1]})"
    if kind == "has":
        return f"has({node[1]}, {_quote(node[2])})"
    if kind == "cmp":
        v = node[3]
        num = re.fullmatch(r'-?\d+(?:\.\d+)?', v)
        return f"{node[1]} {node[2]} {v if num else _quote(v)}"
    if kind == "not":
        inner = format_tql(node[1])
        return f"not {inner}" if node[1][0] in ("known", "dark", "has", "not") else f"not ({inner})"
    a, b = (format_tql(n) if n[0] not in ("and", "or") or n[0] == kind else f"({format_tql(n)})" for n in node[1:])
    return f"{a} {kind} {b}"


def _value(state: Mapping[str, Any], key: str) -> str:
    v = state.get(key, "")
    if isinstance(v, (list, tuple)):
        v = v[0] if len(v) == 1 else ""
    return "" if v is None else str(v)


def evaluate(test: str | tuple, state: Mapping[str, Any]) -> tuple[bool | None, tuple[str, ...]]:
    """True, False, or None (unknown because a key is Dark), plus the Dark keys involved."""
    node = parse_tql(test) if isinstance(test, str) else test
    dark: list[str] = []

    def ev(n: tuple) -> bool | None:
        kind = n[0]
        if kind == "known":
            return _value(state, n[1]) != ""
        if kind == "dark":
            return _value(state, n[1]) == ""
        if kind == "has":
            v = _value(state, n[1])
            if v == "":
                dark.append(n[1])
                return None
            return re.search(r"(?<!\w)" + re.escape(n[2]) + r"(?!\w)", v, re.IGNORECASE) is not None
        if kind == "cmp":
            v = _value(state, n[1])
            if v == "":
                dark.append(n[1])
                return None
            num = re.compile(r"-?\d+(?:\.\d+)?")
            a, b = (float(v), float(n[3])) if num.fullmatch(v) and num.fullmatch(n[3]) else (v, n[3])
            return {"=": a == b, "!=": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[n[2]]
        if kind == "not":
            r = ev(n[1])
            return None if r is None else not r
        left, right = ev(n[1]), ev(n[2])
        if kind == "and":
            return False if False in (left, right) else (None if None in (left, right) else True)
        return True if True in (left, right) else (None if None in (left, right) else False)

    result = ev(node)
    return result, (tuple(dict.fromkeys(dark)) if result is None else ())   # Dark only matters when it decided


def keys_in(node: tuple) -> list[str]:
    if node[0] in ("known", "dark", "has", "cmp"):
        return [node[1]]
    return [k for n in node[1:] for k in keys_in(n)]


# ======================================================================
# Gates
# ======================================================================
def _check_actions(actions: Iterable[str]) -> tuple[str, ...]:
    out = []
    for a in actions:
        parse_handler(a)              # raises on anything that isn't an @handler reference
        out.append(a)
    return tuple(out)


@dataclass(frozen=True)
class Gate:
    """One diamond: a TQL test, what happens if it's true or false, and the card it came from."""

    id: str
    test: str
    if_true: tuple[str, ...] = ()
    if_false: tuple[str, ...] = ()
    next_true: str = ""                 # another gate's id; empty = the next gate in order
    next_false: str = ""
    status: str = PROPOSED
    card: str = ""                      # the reasoning card, in the author's words
    by: str = ""                        # who wrote the card
    approved_by: str = ""

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.id):
            raise ValueError(f"Gate id {self.id!r} must be lowercase words joined by '-'")
        object.__setattr__(self, "test", format_tql(parse_tql(self.test)))
        object.__setattr__(self, "if_true", _check_actions(self.if_true))
        object.__setattr__(self, "if_false", _check_actions(self.if_false))
        if self.status not in (PROPOSED, APPROVED):
            raise ValueError("A gate's status is 'proposed' or 'approved'")

    @property
    def approved(self) -> bool:
        return self.status == APPROVED

    def address(self) -> Address:
        return Address.build(f"gate/{self.id}", {
            "test": self.test, "true.do": list(self.if_true), "false.do": list(self.if_false),
            "true.next": self.next_true or None, "false.next": self.next_false or None, "status": self.status,
            "card": self.card or None, "by": self.by or None, "approved_by": self.approved_by or None})

    @classmethod
    def from_address(cls, address: Address | str) -> "Gate":
        a = address if isinstance(address, Address) else Address.parse(address)
        return cls(a.path[-1], a.get("test", ""), tuple(v for v in a.get_all("true.do") if v),
                   tuple(v for v in a.get_all("false.do") if v), a.get("true.next", ""), a.get("false.next", ""),
                   a.get("status", PROPOSED), a.get("card", ""), a.get("by", ""), a.get("approved_by", ""))


# ======================================================================
# Reasoning cards → gates (deterministic phrasings; anything else goes to a proposer)
# ======================================================================
DEFAULT_SLOTS = {"tax year": "tax_year", "fiscal year": "tax_year", "year": "tax_year", "country": "country",
                 "start date": "start_date", "end date": "end_date", "client": "client", "currency": "currency",
                 "time zone": "timezone", "timezone": "timezone", "date format": "date_format"}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48].strip("-") or "gate"


def _fact_key(phrase: str, slots: Mapping[str, str]) -> str:
    p = re.sub(r"^(?:the|a|an|our|their)\s+", "", phrase.strip().lower())
    p = re.sub(r"\s+(?:is|are|be|was)\s+(?:known|confirmed|provided|given|present|set|stated)$", "", p)
    if p in slots:
        return slots[p]
    key = re.sub(r"[^a-z0-9]+", "_", p).strip("_")
    if not key or not _KEY.fullmatch(key):
        raise CardNotUnderstood(f"Couldn't turn {phrase!r} into a key name")
    return key


_VERBS = r"(?:alert|notify|warn|tell|highlight|ask|halt|stop|block|log|note)"
_HALT_WORDS = r"\b(halt|halted|stop|stopped|cannot proceed|can't proceed|can not proceed|block|blocked)\b"


def _actions_from(clause: str, gate_id: str) -> list[str]:
    """'highlight it and alert that we cannot proceed' → [@core.highlight…, @core.notify…, @core.halt…]."""
    c = clause.strip().rstrip(".!")
    parts = re.split(r"\s+(?:and|then|,)\s+(?=(?:then\s+)?" + _VERBS + r"\b)|\s*,\s*(?=" + _VERBS + r"\b)", c, flags=re.I)
    acts: list[str] = []
    for part in (p.strip() for p in parts if p.strip()):
        part = re.sub(r"^(?:then|do|send|show|raise)\s+(?:an?\s+)?", "", part, flags=re.I)
        low = part.lower()
        verb = re.match(_VERBS, low)
        v = verb.group(0) if verb else ""
        if v in ("alert", "notify", "warn", "tell"):
            msg = re.sub(r"^(?:alert|notify|warn|tell)\w*\s*(?:them|the user|me|everyone)?\s*(?:that\s+)?", "", part,
                         flags=re.I).strip() or part
            acts.append(f"@core.notify?message={encode(msg)}&gate={gate_id}")
            if re.search(_HALT_WORDS, msg.lower()):
                acts.append(f"@core.halt?reason={encode(msg)}")
        elif v == "highlight":
            m = re.match(r"highlight\s+(?:the\s+word\s+)?[\"']?([^\"']+?)[\"']?$", part, re.I)
            word = m.group(1).strip() if m else ""
            acts.append(f"@core.highlight?word={encode(word)}&color=yellow" if word and word.lower() not in
                        ("it", "them", "that", "this") else "@core.highlight?color=yellow")
        elif v == "ask":
            m = re.match(r"ask\s+(?:for\s+|about\s+)?(.+)$", part, re.I)
            if not m:
                raise CardNotUnderstood(f"Ask for what? {part!r}")
            acts.append(f"@core.ask?key={_fact_key(m.group(1), DEFAULT_SLOTS)}")
        elif v in ("halt", "stop", "block"):
            acts.append(f"@core.halt?reason={encode(part)}")
        elif v in ("log", "note"):
            msg = re.sub(r"^(?:log|note)\s*(?:that\s+)?", "", part, flags=re.I).strip() or part
            acts.append(f"@core.log?message={encode(msg)}")
        elif re.search(_HALT_WORDS, low):
            acts.append(f"@core.halt?reason={encode(part)}")
        else:
            raise CardNotUnderstood(f"Couldn't find an action in {part!r}. Try: highlight it · ask for the tax year · "
                                    "alert that … · halt · note that …")
    return acts


@dataclass
class CardResult:
    gate: Gate                      # the new or changed gate
    new: bool                       # True: a new gate; False: actions added to an existing gate


def compile_card(text: str, flow_gates: Sequence[Gate] = (), by: str = "", target: str = "",
                 slots: Mapping[str, str] | None = None,
                 proposer: Callable[[str], Mapping[str, Any]] | None = None) -> CardResult:
    """Turn a reasoning card into a proposed gate (or extra actions on an existing one).

    Understood without a model:
      * "If the query contains yesterday, highlight it."
      * "For Section 41 tax preparation, require the tax year."  /  "Don't answer until the tax year is confirmed."
      * "If false, alert that it's halted and you cannot proceed."  (attaches to ``target`` or the last gate)
      * "If true, …" / "Otherwise, …" likewise.
      * "Test: known(tax_year) and country = "US""  (TQL written directly)

    Anything else goes to ``proposer(text)``, which must return ``{"test": TQL, "if_true": [...],
    "if_false": [...], "id": optional}``; it is validated exactly like a typed card.
    """
    slots = {**DEFAULT_SLOTS, **(slots or {})}
    t = " ".join(text.strip().split())
    low = t.lower().rstrip(".!")

    # 1. an outcome card: "If false, …" / "If true, …" / "Otherwise, …"
    m = re.match(r"^(?:if\s+(?P<b>false|true|not|no|yes)|(?P<o>otherwise|else))\s*[,:]?\s*(?:then\s+)?(?P<rest>.+)$", t, re.I)
    if m:
        branch = "false" if (m.group("o") or (m.group("b") or "").lower() in ("false", "not", "no")) else "true"
        gates = list(flow_gates)
        g = next((x for x in gates if x.id == target), None) if target else (gates[-1] if gates else None)
        if g is None:
            raise CardNotUnderstood("An 'If false/If true' card attaches to a gate; add a gate first")
        acts = _actions_from(m.group("rest"), g.id)
        field_ = "if_false" if branch == "false" else "if_true"
        changed = replace(g, **{field_: tuple(getattr(g, field_)) + tuple(acts), "status": PROPOSED,
                                "card": (g.card + " | " if g.card else "") + t, "approved_by": ""})
        return CardResult(changed, False)

    # 2. TQL written directly
    m = re.match(r"^(?:test|tql|check)\s*:\s*(?P<q>.+)$", t, re.I)
    if m:
        q = format_tql(parse_tql(m.group("q")))
        return CardResult(Gate(_slug(q), q, card=t, by=by), True)

    # 3. "If the query contains X, highlight it"
    m = re.match(r"^if\s+(?:the\s+)?(?:query|question|text|request|message)\s+(?:contains|mentions|has|says|includes)\s+"
                 r"(?:the\s+word\s+)?[\"']?(?P<w>[^\"',]+?)[\"']?(?:\s*,\s*(?:then\s+)?|\s+then\s+)(?P<rest>.+)$", t, re.I)
    if m:
        word = m.group("w").strip()
        gid = _slug(f"mentions {word}")
        acts = _actions_from(re.sub(r"\bhighlight\s+(?:it|that|them)\b", "highlight", m.group("rest"), flags=re.I), gid)
        acts = [f"@core.highlight?word={encode(word)}&color=yellow" if a == "@core.highlight?color=yellow" else a for a in acts]
        return CardResult(Gate(gid, f"has(query, {_quote(word)})", if_true=tuple(acts), card=t, by=by), True)

    # 4. "require X" / "until X is confirmed" / "make sure we have X"
    m = (re.search(r"\buntil\s+(?P<f>.+?)\s+(?:is|are|has been|have been)\s+(?:known|confirmed|provided|given|stated)\b", low)
         or re.search(r"\b(?:require|requires|required|need|needs|must have|must include|make sure (?:we|they|you) have)\s+"
                      r"(?P<f>(?:the\s+)?[a-z][a-z0-9 _-]*?)(?=\s+(?:before|when|for|to|in|from|on)\b|[.,;]|$)", low))
    if m:
        key = _fact_key(m.group("f"), slots)
        gid = _slug(f"{key.replace('_', ' ')} required")
        return CardResult(Gate(gid, f"known({key})", if_false=(f"@core.ask?key={key}",), card=t, by=by), True)

    # 5. a model proposes; code validates
    if proposer is not None:
        p = dict(proposer(t))
        q = format_tql(parse_tql(str(p["test"])))
        gid = p.get("id") or _slug(q)
        return CardResult(Gate(gid, q, tuple(p.get("if_true", ())), tuple(p.get("if_false", ())), card=t,
                               by=by or "proposer"), True)
    raise CardNotUnderstood(
        "I couldn't turn that card into a gate. Phrasings that work: "
        "'If the query contains yesterday, highlight it.' · 'For Section 41, require the tax year.' · "
        "'If false, alert that we cannot proceed.' · 'Test: known(tax_year) and country = \"US\"'")


# ======================================================================
# Running a flow
# ======================================================================
@dataclass
class Step:
    gate: str
    result: bool | None             # None = unknown (a Dark key)
    branch: str                     # "true" or "false"
    actions: tuple[str, ...]
    fired: bool                     # False for proposed gates (shown, not acted on)
    dark: tuple[str, ...] = ()


@dataclass
class FlowResult:
    query: str
    steps: list[Step] = field(default_factory=list)
    stopped_at: str = ""            # gate id where an ask/halt ended the flow
    asks: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    halted: str = ""
    highlights: list[dict[str, Any]] = field(default_factory=list)
    address: str = ""

    @property
    def passed(self) -> bool:
        return not self.stopped_at


class Flow:
    """Query box → gates → (optionally) a SQL card, on top of a context object."""

    def __init__(self, context: Any, query_key: str = "query", observatron: Any = None, card: Any = None,
                 db: Any = None):
        from .context import Observatron  # noqa: avoid an import cycle
        self.ctx = context
        self.query_key = query_key
        self.obs = observatron or Observatron(context, query_key)
        self.card, self.db = card, db

    # ---- the gates live in ctx.reason, beside rules ----
    @property
    def gates(self) -> list[Gate]:
        return [g for g in self.ctx.reason if isinstance(g, Gate)]

    def gate(self, gid: str) -> Gate:
        g = next((x for x in self.gates if x.id == gid), None)
        if g is None:
            raise LookupError(f"No gate {gid!r}. Gates: {', '.join(x.id for x in self.gates) or 'none'}")
        return g

    def put(self, gate: Gate, cause: str) -> Gate:
        if any(x.id == gate.id for x in self.gates):
            self.ctx.reason = [gate if isinstance(x, Gate) and x.id == gate.id else x for x in self.ctx.reason]
        else:
            self.ctx.reason.append(gate)
        self.ctx.trace.append("trigger", "gate", str(gate.address()), cause, self.ctx.snapshot())
        return gate

    def add_card(self, text: str, by: str = "", target: str = "", proposer: Callable | None = None,
                 slots: Mapping[str, str] | None = None) -> Gate:
        """Compile a reasoning card and store the (proposed) gate it produces."""
        res = compile_card(text, self.gates, by, target, slots, proposer)
        return self.put(res.gate, f"card:{by or 'anonymous'}")

    def approve(self, gid: str, by: str) -> Gate:
        """Approve through the registry, so approval is a recorded, intended call."""
        self.ctx.call(f"@core.approve?gate={gid}&by={encode(by)}", f"person:{by}")
        return self.gate(gid)

    # ---- run ----
    def run(self, query: str) -> FlowResult:
        ctx = self.ctx
        ctx.highlights.clear()
        ctx.asks.clear()
        ctx.notes.clear()
        ctx.halted = None
        self.obs.observe(query)                 # observe: sensors fill keys, highlight what they recognize
        state = ctx.address.to_dict()
        res = FlowResult(query)
        gates = self.gates
        order = {g.id: i for i, g in enumerate(gates)}
        i, seen = 0, set()
        while 0 <= i < len(gates):
            g = gates[i]
            if g.id in seen:
                break                            # a loop in next-pointers: stop rather than spin
            seen.add(g.id)
            result, dark = evaluate(g.test, state)
            branch = "true" if result else "false"
            acts = g.if_true if result else g.if_false
            step = Step(g.id, result, branch, acts, g.approved, dark)
            res.steps.append(step)
            ctx.trace.append("decide", g.id, branch if result is not None else f"false (dark: {', '.join(dark)})",
                             f"gate:{g.id}", ctx.snapshot())
            stop = False
            if g.approved:
                for k in dark:                   # unknown because a key is Dark: ask for it
                    if k not in ctx.asks:
                        ctx.asks.append(k)
                for a in acts:
                    name, params = parse_handler(a)
                    extra: dict[str, Any] = {}
                    if name == "core.highlight" and params.get("word"):
                        for m in re.finditer(r"(?<!\w)" + re.escape(params["word"]) + r"(?!\w)", query, re.I):
                            ctx.call(a, f"gate:{g.id}", _spike=SimpleNamespace(start=m.start(), end=m.end(), sensor=g.id))
                        continue
                    ctx.call(a, f"gate:{g.id}", **extra)
                    stop = stop or name in STOPPING
                if dark and not acts:
                    stop = True
            if stop:
                res.stopped_at = g.id
                break
            nxt = g.next_true if result else g.next_false
            i = order.get(nxt, i + 1) if nxt else i + 1
        res.asks = list(ctx.asks)
        res.alerts = [n for n in ctx.notes if n.startswith("ALERT")]
        res.halted = ctx.halted or ""
        res.highlights = list(ctx.highlights)
        res.address = str(ctx.address)
        return res


def flow_demo(registry: Any = None) -> Flow:
    """The minimal example: query box → the manager's tax-year gate → SQL card. No gates yet: add cards."""
    from .context import ContextObject
    from .demo import section41
    base, _, db, card = section41(registry)
    sensors = [s for s in base.observe if s.id != "relative-date"]      # highlighting comes from cards here
    ctx = ContextObject("reason/section-41", base.schema, sensors, registry=base.registry,
                        params={"query": "", "task": "", "country": "", "tax_year": ""})
    return Flow(ctx, "query", card=card, db=db)


def describe(action: str) -> str:
    """A short human label for an action: ``@core.ask?key=tax_year`` → ``ask for tax_year``."""
    name, p = parse_handler(action)
    if name == "core.ask":
        return "ask for " + (p["key"] if isinstance(p.get("key"), str) else ", ".join(p.get("key", [])))
    if name == "core.halt":
        return "halt"
    if name == "core.notify":
        return f'alert "{p.get("message", "")}"'
    if name == "core.highlight":
        return f'highlight "{p["word"]}"' if p.get("word") else "highlight"
    if name == "core.log":
        return f'note "{p.get("message", "")}"'
    if name == "core.update":
        return "set " + ", ".join(f"{k}={v}" for k, v in p.items() if not k.startswith("_"))
    return "@" + name


# ======================================================================
# Terminal view
# ======================================================================
def draw_flow(flow: Flow, result: FlowResult | None = None, color: bool | None = None) -> str:
    from .pretty import highlight, paint, show_card
    lines: list[str] = []
    q = result.query if result else flow.ctx.get(flow.query_key, "")
    shown = highlight(q, result.highlights, color) if result else q
    width = max(24, min(76, len(q) + 2))
    lines.append("┌" + "─" * width + "┐")
    lines.append("│ " + paint("query", "dim", color=color) + "  " + shown)
    lines.append("└" + "─" * width + "┘")
    steps = {s.gate: s for s in (result.steps if result else [])}
    for g in flow.gates:
        s = steps.get(g.id)
        lines.append("   │")
        badge = paint("approved" + (f" by {g.approved_by}" if g.approved_by else ""), "green", color=color) if g.approved \
            else paint("proposed: shown, not acted on", "yellow", color=color)
        lines.append("   ◆ " + paint(g.id, "bold", color=color) + "   " + g.test + "?   " + badge)
        if g.card:
            lines.append("   │   " + paint("card: " + g.card + (f"  ({g.by})" if g.by else ""), "dim", color=color))
        for branch, acts, nxt in (("true", g.if_true, g.next_true), ("false", g.if_false, g.next_false)):
            taken = s is not None and s.branch == branch
            label = ", ".join(describe(a) for a in acts) if acts else ("continue" if not nxt else "")
            if nxt:
                label = (label + " → " if acts else "→ ") + nxt
            row = f"   {'├' if branch == 'true' else '└'}─ {branch:<5} {label}"
            if taken:
                why = "" if s.result is not None else f"  (unknown: {', '.join(s.dark)} is Dark)"
                row = paint(row + "   ◀ taken" + why, "bold", color=color)
            lines.append(row)
        if result and result.stopped_at == g.id:
            lines.append("   ■ " + paint("stops here", "red", color=color))
            break
    if result:
        for a in result.alerts:
            lines.append(paint("   ! " + a, "red", color=color))
        if result.asks:
            lines.append(paint("   ? ask for: " + ", ".join(result.asks), "yellow", color=color))
        if flow.card is not None:
            lines.append("   │")
            lines.append(show_card(flow.card, flow.ctx.address.to_dict(), color))
            if result.passed and not flow.card.missing(flow.ctx.address.to_dict()) and flow.db is not None:
                r = flow.card.run(flow.db, flow.ctx.address.to_dict())
                lines.append(paint(f"   result: {r.columns[0]} = {r.scalar()}", "green", color=color))
    return "\n".join(lines)


# ======================================================================
# Interactive terminal app: tcxp flow
# ======================================================================
DEMO_CARDS = (
    ("For Section 41 tax preparation, when we get CSVs, require the tax year.", "manager"),
    ("If false, alert that it's halted and you cannot proceed.", "manager"),
    ("If the query contains yesterday, highlight it.", "manager"),
)
FLOW_HELP = ("Type a query to run it.  :card <sentence> adds a reasoning card (proposed)  ·  :approve <gate|all>  ·  "
             ":gates  ·  :address  ·  :quit")


def repl(lines: Iterable[str] | None = None, cards: bool = True, approve: bool = True, by: str = "manager",
         color: bool | None = None, out: Callable[[str], None] = print, session_path: Any = None) -> Flow:
    """``tcxp flow``: type queries and cards, watch the gates. Scriptable with ``lines`` (tests, docs)."""
    from .pretty import paint
    flow = flow_demo()
    if cards:
        for text, who in DEMO_CARDS:
            g = flow.add_card(text, by=who)
            if approve:
                flow.approve(g.id, who)
    out(paint("tcxp flow", "bold", color=color) + "  " + paint(FLOW_HELP, "dim", color=color))
    interactive = lines is None
    source = iter(lines) if lines is not None else None
    last: FlowResult | None = None
    while True:
        try:
            line = input(paint("\nflow> ", "bold", color=color)) if interactive else next(source)
        except (EOFError, StopIteration, KeyboardInterrupt):
            break
        line = line.strip()
        if not interactive:
            out(paint("\nflow> ", "bold", color=color) + line)
        if not line:
            continue
        if line.startswith(":"):
            cmd, _, arg = line[1:].partition(" ")
            try:
                if cmd in ("quit", "q", "exit"):
                    break
                if cmd == "card":
                    g = flow.add_card(arg, by=by)
                    out(f"Gate {g.id} is proposed: {g.test}?  Approve it with :approve {g.id}")
                    out(paint("  " + str(g.address()), "dim", color=color))
                elif cmd == "approve":
                    ids = [g.id for g in flow.gates if not g.approved] if arg in ("", "all") else arg.split()
                    for gid in ids:
                        flow.approve(gid, by)
                    out("Approved: " + (", ".join(ids) or "nothing to approve"))
                elif cmd == "gates":
                    for g in flow.gates:
                        out(str(g.address()))
                elif cmd == "address":
                    out(str(flow.ctx.address))
                else:
                    out(FLOW_HELP)
            except (ValueError, LookupError) as exc:
                out(paint(f"  {exc}", "red", color=color))
                continue
            if last is not None and cmd in ("card", "approve"):
                last = flow.run(last.query)
                out("\n" + draw_flow(flow, last, color))
            continue
        last = flow.run(line)
        out("\n" + draw_flow(flow, last, color))
    if session_path is not None:
        from .session import Session
        p = Session(flow.ctx, 0, session_path).save()
        out(paint(f"\nSession saved to {p}. Replay it with: tcxp roll", "dim", color=color))
    return flow
