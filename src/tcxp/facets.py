"""Spikes and facets.

A Spike is one observation: whatever a sensor caught (the word "yesterday", a
column of dates). It has two facet categories:

* **Anchor:** the ``data`` facet. What was observed, as text.
* **Context:** ``meaning``, ``structure`` and ``environment``. Each is a list of
  addresses.

  - *meaning* points to a shared definition (where semantic and ontology work lives).
  - *structure* points to a schema: validation, constraints, or the limits a generator must stay within.
  - *environment* points to what the reader needs about the situation to use the data
    (the Baltic Sea freezes at a different temperature than fresh water).

A context facet is **Lit** when it holds at least one address and **Dark** when it is
empty. That makes two guarantees exact and scale-free:

1. Counting Dark facets is counting empty lists.
2. Comparing two readings is string equality on canonical addresses: ``MATCH``,
   ``NO MATCH`` or ``DARK``. A MATCH is never false. A NO MATCH can be a missed
   equivalence (two addresses for one concept) until someone records the equivalence.

In an address, a slot ``date`` and its facets are four keys:
``date=05/04/2026&date.meaning=&date.structure=!tcxp:/schema/date/mm-dd-yyyy&date.environment=``
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

from .address import Address

__all__ = ["Spike", "FACETS", "MATCH", "NO_MATCH", "DARK", "LIT", "spikes_in", "dark_count", "Equivalences"]

FACETS = ("meaning", "structure", "environment")
MATCH, NO_MATCH, DARK, LIT = "MATCH", "NO MATCH", "DARK", "LIT"


class Equivalences:
    """Recorded, confirmed equivalences between addresses (each pair is itself a record)."""

    def __init__(self, pairs: Iterable[tuple[str, str]] = ()):
        self._groups: dict[str, set[str]] = {}
        for a, b in pairs:
            self.add(a, b)

    def add(self, a: str, b: str) -> None:
        a, b = str(Address.parse(str(a))), str(Address.parse(str(b)))
        group = self._groups.get(a, {a}) | self._groups.get(b, {b})
        for member in group:
            self._groups[member] = group

    def same(self, a: str, b: str) -> bool:
        return a == b or b in self._groups.get(a, ())


@dataclass(frozen=True)
class Spike:
    """One observation with its anchor (data) and context facets."""

    key: str
    data: str = ""
    meaning: tuple[str, ...] = ()
    structure: tuple[str, ...] = ()
    environment: tuple[str, ...] = ()
    # what triggered it (empty when the spike was read back from an address)
    sensor: str = ""
    target: str = ""
    start: int = -1
    end: int = -1
    time: str = ""

    def __post_init__(self) -> None:
        for name in FACETS:  # store canonical, non-empty addresses only
            vals = tuple(str(Address.parse(v)) for v in getattr(self, name) if v)
            object.__setattr__(self, name, vals)

    def status(self, facet: str) -> str:
        return LIT if getattr(self, facet) else DARK

    @property
    def dark(self) -> tuple[str, ...]:
        return tuple(f for f in FACETS if not getattr(self, f))

    @property
    def lit(self) -> tuple[str, ...]:
        return tuple(f for f in FACETS if getattr(self, f))

    def compare(self, other: "Spike", facet: str, equivalences: Equivalences | None = None) -> str:
        """MATCH / NO MATCH / DARK for one facet, by string equality on canonical addresses."""
        if facet not in FACETS:
            raise ValueError(f"compare() works on context facets {FACETS}, not {facet!r}")
        mine, theirs = getattr(self, facet), getattr(other, facet)
        if not mine or not theirs:
            return DARK
        if set(mine) == set(theirs):
            return MATCH
        if equivalences and all(any(equivalences.same(a, b) for b in theirs) for a in mine) \
                and all(any(equivalences.same(b, a) for a in mine) for b in theirs):
            return MATCH
        return NO_MATCH

    def with_facet(self, facet: str, *addresses: str) -> "Spike":
        return replace(self, **{facet: tuple(addresses)})

    # ---------- address round trip ----------
    def to_params(self) -> dict[str, object]:
        return {self.key: self.data, **{f"{self.key}.{f}": list(getattr(self, f)) for f in FACETS}}

    @classmethod
    def from_address(cls, address: Address, key: str) -> "Spike":
        return cls(key, address.get(key, ""), *(tuple(v for v in address.get_all(f"{key}.{f}") if v) for f in FACETS))


def spikes_in(address: Address) -> list[Spike]:
    """Every slot in the address that carries facet keys."""
    keys = sorted({k.rsplit(".", 1)[0] for k in address.keys() if k.rsplit(".", 1)[-1] in FACETS and "." in k})
    return [Spike.from_address(address, k) for k in keys]


def dark_count(address: Address) -> int:
    """How many context facets in the whole address are Dark."""
    return sum(len(s.dark) for s in spikes_in(address))
