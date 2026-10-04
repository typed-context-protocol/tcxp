"""Trace: the append-only log of every change to a context object's address.

One row per change, keyed on keys (not character positions, which break as soon as
the canonical form reorders keys):

=====  ========================  ======  ========  ===========  ===========  ===========  ======
index  time (ISO 8601, UTC)      op      key       value        cause        address      hash
=====  ========================  ======  ========  ===========  ===========  ===========  ======
0      2026-10-03T21:54:01.000Z  set     query     what should  input:query  !tcxp:/...   a41f…
=====  ========================  ======  ========  ===========  ===========  ===========  ======

* ``op`` is ``set``, ``unset``, ``append``, ``trigger`` or ``decide``.
* ``address`` is the full canonical address *after* the change. Above
  ``MAX_INLINE`` characters it is a ``!tcxp:/state/sha256-…`` pointer instead.
* ``hash`` chains each row to the previous one, so any edit to history is detectable.
* ``learnable`` marks rows a person confirmed: labeled examples for training.

``verify(registry)`` checks the chain and that every state pointer resolves with a
matching hash. Passing it is the guarantee that nothing was lost.
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from .address import Address
from .registry import Registry, canonical_json

__all__ = ["Row", "Trace", "utc_now"]

GENESIS = "0" * 64


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Row:
    index: int
    time: str
    op: str
    key: str
    value: str
    cause: str
    address: str
    prev_hash: str
    hash: str
    learnable: bool = False
    features: str = ""   # for learnable rows: the text the label belongs to

    def body(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("hash")
        return d


class Trace:
    def __init__(self, clock: Callable[[], str] = utc_now):
        self.rows: list[Row] = []
        self.clock = clock

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    @property
    def last_hash(self) -> str:
        return self.rows[-1].hash if self.rows else GENESIS

    def append(self, op: str, key: str, value: Any, cause: str, address: Address | str,
               learnable: bool = False, features: str = "") -> Row:
        value_text = value if isinstance(value, str) else canonical_json(value)
        partial = dict(index=len(self.rows), time=self.clock(), op=op, key=key, value=value_text,
                       cause=cause, address=str(address), prev_hash=self.last_hash,
                       learnable=learnable, features=features)
        digest = hashlib.sha256(canonical_json(partial).encode("utf-8")).hexdigest()
        row = Row(hash=digest, **partial)
        self.rows.append(row)
        return row

    # ---------- guarantees ----------
    def verify(self, registry: Registry | None = None) -> list[str]:
        """Problems found (empty list = intact). Checks the hash chain and every state pointer."""
        problems, prev = [], GENESIS
        for r in self.rows:
            if r.prev_hash != prev:
                problems.append(f"row {r.index}: chain broken (prev_hash does not match row {r.index - 1})")
            if hashlib.sha256(canonical_json(r.body()).encode("utf-8")).hexdigest() != r.hash:
                problems.append(f"row {r.index}: contents changed after it was written")
            if r.address.startswith("!tcxp:/state/sha256-"):
                if registry is None:
                    problems.append(f"row {r.index}: state pointer cannot be checked without a registry")
                else:
                    try:
                        registry.get_state(r.address)
                    except Exception as exc:  # KeyError or IntegrityError
                        problems.append(f"row {r.index}: {exc}")
            prev = r.hash
        return problems

    # ---------- views ----------
    def learnable(self) -> list[Row]:
        return [r for r in self.rows if r.learnable]

    def summary(self) -> dict[str, Any]:
        """Start, end, and what changed in between (by key)."""
        if not self.rows:
            return {"rows": 0}
        start, end = self.rows[0].address, self.rows[-1].address
        changed: dict[str, list[str]] = {}
        for r in self.rows:
            if r.op in ("set", "unset", "append"):
                changed.setdefault(r.key, []).append(r.value)
        return {"rows": len(self.rows), "start": start, "end": end,
                "changed": {k: {"from": v[0], "to": v[-1], "edits": len(v)} for k, v in changed.items()},
                "learnable": len(self.learnable())}

    def to_dicts(self) -> list[dict[str, Any]]:
        return [asdict(r) for r in self.rows]

    def to_json(self) -> str:
        return json.dumps(self.to_dicts(), indent=2, ensure_ascii=False)

    def to_csv(self) -> str:
        buf = io.StringIO()
        fields = list(Row.__dataclass_fields__)
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        for r in self.rows:
            w.writerow(asdict(r))
        return buf.getvalue()

    def to_dataframe(self):  # pragma: no cover - optional dependency
        import pandas as pd
        return pd.DataFrame(self.to_dicts())

    @classmethod
    def from_dicts(cls, rows: Iterable[dict[str, Any]]) -> "Trace":
        t = cls()
        t.rows = [Row(**r) for r in rows]
        return t
