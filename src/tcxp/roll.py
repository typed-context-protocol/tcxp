"""The context roll: a piano roll for addresses, in the terminal.

    step 6/14 · 2026-10-03T22:18:56Z · set tax_year = 2024 (person:you)
                              -3          -2          -1         ▼ NOW        +1          +2
                                                                ─────────
    !tcxp:/reason/section-41  ●                       ●          ●
      country                 US          US          US         US          US          US
      tax_year                ·           ·           ·          2024        2024        2024
      ...

* The first column is fixed: the address path, then one sub-row per key.
* Each other column is a step. ``▼ NOW`` marks the step being played. Past steps sit to its
  left, upcoming steps to its right; as play advances, columns scroll left.
* A cell lights up when its value changes at that step (like a MIDI note-on).
  ``·`` is an empty (Dark) value. ``●`` on the address row means the address changed.

``tcxp roll`` (alias ``tcxp sequencer play``) plays the session through the roll, redrawing
once per ``--speed`` seconds. ``Roll.to_dict()`` exports the same frames for the web simulator.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .address import Address
from .pretty import paint, strip, use_color

__all__ = ["Roll", "Step", "steps_from_session"]


@dataclass(frozen=True)
class Step:
    index: int
    time: str
    change: str
    address: Address


def steps_from_session(session: Any) -> list[Step]:
    ctx = session.context
    out = []
    for r in ctx.trace.rows:
        change = f"{r.op} {r.key}" + (f" = {r.value}" if r.value else "") + f" ({r.cause})"
        out.append(Step(r.index, r.time, change, ctx.resolve(r.address)))
    return out


def _short(value: str) -> str:
    """Pointers show their last segment (↗US), since the full address is printed under the roll."""
    parts = []
    for v in value.split(","):
        parts.append("↗" + v.split("?")[0].rstrip("/").rsplit("/", 1)[-1] if v.startswith("!tcxp:/") else v)
    return ",".join(parts)


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


class Roll:
    def __init__(self, steps: Sequence[Step], past: int = 3, future: int = 2, key_width: int = 26, cell_width: int = 12):
        self.steps = list(steps)
        self.past, self.future, self.key_width, self.cell_width = past, future, key_width, cell_width
        keys: list[str] = []
        for s in self.steps:
            for k in s.address.keys():
                if k not in keys:
                    keys.append(k)
        self.keys = sorted(keys)

    def _value(self, i: int, key: str) -> str | None:
        if not 0 <= i < len(self.steps):
            return None
        vals = self.steps[i].address.get_all(key)
        return ",".join(vals) if vals else None

    def _changed(self, i: int, key: str | None) -> bool:
        if i <= 0 or i >= len(self.steps):
            return False
        if key is None:
            return self.steps[i].address != self.steps[i - 1].address
        return self._value(i, key) != self._value(i - 1, key)

    def render(self, now: int, color: bool | None = None) -> str:
        c = use_color() if color is None else color
        cols = list(range(now - self.past, now + self.future + 1))
        W, K = self.cell_width, self.key_width
        step = self.steps[now]
        lines = [paint(f"tcxp context roll · step {step.index}/{len(self.steps) - 1} · {step.time} · {step.change}", "bold", color=c)]
        head, rule = " " * K, " " * K
        for i in cols:
            label = "▼ NOW" if i == now else (f"{i - now:+d}" if 0 <= i < len(self.steps) else "")
            cell = label.center(W)
            head += paint(cell, "bold", color=c) if i == now else paint(cell, "dim", color=c)
            rule += ("─" * (W - 2)).center(W) if i == now else " " * W
        lines += [head.rstrip(), rule.rstrip()]
        # the address row
        row = paint(_fit(str(step.address).split("?", 1)[0], K - 1).ljust(K), "bold", color=c)
        for i in cols:
            mark = "●" if self._changed(i, None) or (i == 0 and 0 <= i < len(self.steps)) else ""
            row += paint(mark.center(W), "yellow" if i == now else "dim", color=c) if mark else " " * W
        lines.append(row.rstrip())
        # one sub-row per key
        for key in self.keys:
            row = "  " + _fit(key, K - 3).ljust(K - 2)
            for i in cols:
                v = self._value(i, key)
                if v is None:
                    row += " " * W
                    continue
                text = _fit(_short(v), W - 2) if v else "·"
                cell = text.center(W)
                if self._changed(i, key):
                    cell = paint(cell, "bg_yellow" if i == now else "yellow", color=c)
                elif not v:
                    cell = paint(cell, "dark" if i == now else "dim", color=c)
                elif i != now:
                    cell = paint(cell, "dim", color=c)
                else:
                    cell = paint(cell, "green", color=c)
                row += cell
            lines.append(row.rstrip())
        lines.append("")
        lines.append(paint(str(step.address), "cyan", color=c))
        return "\n".join(lines)

    def play(self, start: int = 0, steps: int | None = None, speed: float = 1.0, out: Callable[[str], None] | None = None,
             color: bool | None = None, clear: bool | None = None) -> int:
        """Redraw once per ``speed`` seconds. Returns the index after the last step played."""
        end = len(self.steps) if steps is None else min(len(self.steps), start + steps)
        write = out or (lambda s: (sys.stdout.write(s + "\n"), sys.stdout.flush()))
        wipe = (sys.stdout.isatty() if clear is None else clear) and out is None
        for now in range(start, end):
            frame = self.render(now, color)
            write(("\x1b[2J\x1b[H" if wipe else "") + frame)
            if speed and now < end - 1:
                time.sleep(speed)
        return end

    def to_dict(self) -> dict[str, Any]:
        """Frames for the web simulator: keys, and per step its time, change, address and values."""
        return {"keys": self.keys, "past": self.past, "future": self.future,
                "steps": [{"index": s.index, "time": s.time, "change": s.change, "address": str(s.address),
                           "path": s.address.path_text, "values": {k: self._value(i, k) for k in self.keys}}
                          for i, s in enumerate(self.steps)]}
