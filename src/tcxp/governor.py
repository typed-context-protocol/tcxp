"""Rules and the Governor.

A **Rule** always has the same fixed shape, so a model can never change what a rule means:

    when <action>, require <keys>, otherwise <verdict>

and it is itself an address, so it can be shared by link or text message:

    !tcxp:/rule/r1?by=manager&require=tax_year&verdict=ASK&when=answer

``Rule.compile`` turns a manager's plain-English sentence in the shape
"Don't <action> until <fact>" into a Rule deterministically.

The **Governor** takes a state (an Address) and the rules, and returns one
**Verdict**: ``ACT``, ``ASK`` or ``HALT``. HALT is absorbing: once a HALT rule
fires, nothing lowers it. The Verdict is an address too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .address import Address
from .schema import Schema

__all__ = ["ACT", "ASK", "HALT", "Rule", "Verdict", "Governor", "RuleCompileError"]

ACT, ASK, HALT = "ACT", "ASK", "HALT"


class RuleCompileError(ValueError):
    pass


_ACTION_WORDS = [
    (r"answer|give|respond|reply|report|deduct|claim|credit|calculate|compute", "answer"),
    (r"run|query|select|sql", "query"),
    (r"send|share|publish|post", "send"),
    (r"approve|sign|commit|book|execute|pay", "commit"),
]


def _slug(text: str) -> str:
    text = re.sub(r"[’']s\b", "", text.lower())
    text = re.sub(r"\b(the|a|an|is|are|has|have|been|be|confirmed|established|known|set|given|provided|verified|checked|stated)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:40] or "fact"


@dataclass(frozen=True)
class Rule:
    id: str
    when: str
    require: tuple[str, ...]
    verdict: str = ASK
    text: str = ""
    by: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in (ASK, HALT):
            raise ValueError("A rule's verdict is ASK or HALT (ACT is what happens when it is satisfied)")

    def address(self) -> Address:
        return Address.build(f"rule/{self.id}", {"when": self.when, "require": list(self.require),
                                                  "verdict": self.verdict, "by": self.by or None,
                                                  "text": self.text or None})

    @classmethod
    def from_address(cls, address: Address | str) -> "Rule":
        a = address if isinstance(address, Address) else Address.parse(address)
        return cls(a.path[-1], a.get("when", "*"), tuple(v for v in a.get_all("require") if v),
                   a.get("verdict", ASK), a.get("text", ""), a.get("by", ""))

    @classmethod
    def compile(cls, text: str, rule_id: str = "", by: str = "", slots: Mapping[str, str] | None = None) -> "Rule":
        """Compile "Don't <action> until <fact>" deterministically.

        ``slots`` maps phrases to known keys, e.g. ``{"tax year": "tax_year"}``. Unknown
        facts become a new key named from the phrase.
        """
        m = re.match(r"^\s*(?:don'?t|do not|never|no)\s+(.+?)\s+(?:until|unless|without|before)\s+(.+?)\.?\s*$", text, re.I)
        if not m:
            raise RuleCompileError("Expected the shape \"Don't <action> until <fact>\"")
        action_phrase, fact_phrase = m.group(1), m.group(2)
        when = next((key for pat, key in _ACTION_WORDS if re.search(pat, action_phrase, re.I)), None)
        if when is None:
            raise RuleCompileError(f"Couldn't match {action_phrase!r} to an action")
        verdict = HALT if re.match(r"^\s*never\b", text, re.I) else ASK
        req = None
        for phrase, key in (slots or {}).items():
            if re.search(r"\b" + re.escape(phrase) + r"\b", fact_phrase, re.I):
                req = key
                break
        req = req or _slug(fact_phrase)
        return cls(rule_id or f"{when}-requires-{req}".replace("_", "-"), when, (req,), verdict, text, by)


@dataclass(frozen=True)
class Verdict:
    kind: str
    action: str
    missing: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    message: str = ""

    def address(self) -> Address:
        return Address.build("decision", {"kind": self.kind, "action": self.action,
                                          "missing": list(self.missing) or None, "rule": list(self.rules) or None})

    def __str__(self) -> str:
        return self.message or f"{self.kind} {self.action}"


@dataclass
class Governor:
    rules: list[Rule] = field(default_factory=list)
    schema: Schema | None = None

    def add(self, rule: Rule | str) -> Rule:
        r = rule if isinstance(rule, Rule) else Rule.from_address(rule)
        self.rules = [x for x in self.rules if x.id != r.id] + [r]
        return r

    @staticmethod
    def _is_dark(address: Address, key: str, schema: Schema | None) -> bool:
        values = address.get_all(key)
        if not values or any(v == "" for v in values):   # Lit only when every value is filled
            return True
        if schema and key in schema.fields:
            return any(p.key == key for p in schema.problems(address))
        return False

    def evaluate(self, address: Address, action: str = "answer") -> Verdict:
        """The Decidability Gate: can this action run on this state?"""
        missing: list[str] = []
        halting: list[str] = []
        asking: list[str] = []
        required = [(r, k) for r in self.rules if r.when in (action, "*") for k in r.require]
        if self.schema:
            required += [(None, k) for k in self.schema.essential]
        for rule, key in required:
            if self._is_dark(address, key, self.schema):
                if key not in missing:
                    missing.append(key)
                if rule is not None:
                    (halting if rule.verdict == HALT else asking).append(rule.id)
        if halting:
            return Verdict(HALT, action, tuple(missing), tuple(dict.fromkeys(halting)),
                           f"HALT: {', '.join(missing)} must be known before '{action}'")
        if missing:
            return Verdict(ASK, action, tuple(missing), tuple(dict.fromkeys(asking)),
                           f"ASK: {', '.join(missing)} before '{action}'")
        return Verdict(ACT, action, (), (), f"ACT: everything '{action}' needs is known")
