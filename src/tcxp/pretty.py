"""Terminal output: tables, highlights, Lit/Dark coloring.

Color is on in a terminal or a Jupyter/Colab notebook, off when output is piped.
Force it with ``TCXP_COLOR=1`` or turn it off with ``NO_COLOR=1``.

* Lit values: green.  Dark values and missing SQL slots: white on black.
* Sensor matches in your text: highlighted in the sensor's color (yellow by default).
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Iterable, Sequence

from .address import Address
from .facets import FACETS

__all__ = ["use_color", "paint", "highlight", "table", "show_address", "show_card", "show_trace", "show_verdict", "strip"]

_CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "blue": "34", "magenta": "35",
          "cyan": "36", "white": "37", "bg_yellow": "43;30", "bg_cyan": "46;30", "bg_green": "42;30",
          "bg_red": "41;97", "bg_magenta": "45;97", "dark": "40;97"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def use_color() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("TCXP_COLOR") == "0":
        return False
    if os.environ.get("TCXP_COLOR") == "1":
        return True
    return sys.stdout.isatty() or "ipykernel" in sys.modules


def paint(text: str, *styles: str, color: bool | None = None) -> str:
    if not (use_color() if color is None else color) or not styles:
        return text
    codes = ";".join(_CODES[s] for s in styles if s in _CODES)
    return f"\x1b[{codes}m{text}\x1b[0m" if codes else text


def strip(text: str) -> str:
    return _ANSI.sub("", text)


def highlight(text: str, spans: Iterable[dict[str, Any] | tuple[int, int, str]], color: bool | None = None) -> str:
    """Highlight character spans: ``[(start, end, "yellow"), ...]`` or highlight dicts."""
    marks = []
    for s in spans:
        start, end, c = (s["start"], s["end"], s.get("color", "yellow")) if isinstance(s, dict) else s
        if 0 <= start < end:
            marks.append((start, end, c))
    marks.sort()
    out, pos = [], 0
    for start, end, c in marks:
        if start < pos:
            continue
        out.append(text[pos:start])
        out.append(paint(text[start:end], f"bg_{c}" if f"bg_{c}" in _CODES else "bg_yellow", color=color))
        pos = end
    out.append(text[pos:])
    return "".join(out)


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]], color: bool | None = None) -> str:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max([len(h)] + [len(strip(r[i])) for r in rows]) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(c + " " * (w - len(strip(c))) for c, w in zip(cells, widths)).rstrip()
    head = line([paint(h, "bold", color=color) for h in headers])
    rule = "  ".join("─" * w for w in widths)
    return "\n".join([head, rule] + [line(r) for r in rows])


def _status(key: str, value: str, essential: Sequence[str]) -> str:
    base, _, facet = key.rpartition(".")
    if facet in FACETS and base:
        return "LIT" if value else "DARK"
    if key in essential:
        return "LIT" if value else "DARK"
    return ""


def show_address(address: Address | str, essential: Sequence[str] = (), color: bool | None = None) -> str:
    """The address, then one row per key with Lit/Dark status where it applies."""
    a = address if isinstance(address, Address) else Address.parse(address)
    rows = []
    for key, vals in a.params:
        for v in vals:
            st = _status(key, v, essential)
            shown = v if v else "(empty)"
            if st == "LIT":
                shown, st = paint(shown, "green", color=color), paint("LIT", "green", "bold", color=color)
            elif st == "DARK":
                shown, st = paint(" " + shown + " ", "dark", color=color), paint("DARK", "dark", color=color)
            rows.append([key, shown, st])
    return paint(str(a), "dim", color=color) + "\n" + table(["key", "value", "status"], rows, color=color)


def show_card(card: Any, state: dict[str, Any], color: bool | None = None) -> str:
    """The SQL template with filled slots in green and missing slots white on black."""
    filled = card.fill(state)

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name in filled:
            return paint(f"'{filled[name]}'", "green", color=color)
        return paint(f" :{name} ", "dark", color=color)
    sql = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", sub, card.template)
    missing = card.missing(state)
    status = paint("ready to run", "green", color=color) if not missing else \
        paint("missing " + ", ".join(missing), "dark", color=color)
    return f"{paint(card.title, 'bold', color=color)}  ({status})\n  {sql}"


def show_verdict(verdict: Any, color: bool | None = None) -> str:
    style = {"ACT": ("bg_green",), "ASK": ("bg_yellow",), "HALT": ("bg_red",)}.get(verdict.kind, ())
    return paint(f" {verdict.kind} ", *style, color=color) + " " + str(verdict.message or verdict)


def show_trace(trace: Any, last: int | None = None, color: bool | None = None) -> str:
    rows = trace.rows[-last:] if last else trace.rows
    out = []
    for r in rows:
        value = (r.value[:38] + "…") if len(r.value) > 39 else r.value
        flag = paint("learnable", "magenta", color=color) if r.learnable else ""
        out.append([str(r.index), r.time, r.op, r.key, value or paint("(empty)", "dim", color=color), r.cause, flag])
    return table(["#", "time", "op", "key", "value", "cause", ""], out, color=color)
