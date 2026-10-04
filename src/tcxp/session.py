"""Sessions and playback, with transport-style commands.

A session file (default ``./tcxp-session.json``) holds a context object, every state it
pointed to, and a **playhead**. Nothing it references is left out, so a session file
alone is enough to replay and verify it.

    tcxp play                   play from the playhead to the end
    tcxp play --steps 3         play three steps
    tcxp play --output json     show each state as JSON (or python, csv, sql, cpp, java, js)
    tcxp rewind                 playhead back to the start
    tcxp rewind 2               back two steps
    tcxp seek 5                 jump to step 5
    tcxp status                 where the playhead is
    tcxp reset                  delete the session

Each frame shows: step number, ISO 8601 time, what changed, and the address after it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterator

from .address import Address
from .context import ContextObject
from .convert import convert
from .pretty import paint
from .registry import Registry
from .trace import Row, Trace

__all__ = ["Session", "DEFAULT_PATH", "frame"]

DEFAULT_PATH = Path("tcxp-session.json")


class Session:
    def __init__(self, context: ContextObject, playhead: int = 0, path: Path | str = DEFAULT_PATH):
        self.context, self.playhead, self.path = context, playhead, Path(path)

    # ---------- persistence ----------
    def save(self) -> Path:
        reg = self.context.registry
        pointers = {r.address for r in self.context.trace if r.address.startswith("!tcxp:/state/sha256-")}
        states = {p: reg.get_state(p) for p in pointers}
        data = {"format": "tcxp-session/1", "playhead": self.playhead, "context": self.context.to_dict(), "states": states}
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.path

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "Session":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"No session at {p}. Run `tcxp demo` or `tcxp sim --record` first.")
        if p.is_dir():
            raise ValueError(f"{p} is a folder, not a session file")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{p} is not a tcxp session file ({exc})") from exc
        if not isinstance(data, dict) or "context" not in data:
            raise ValueError(f"{p} is not a tcxp session file (no 'context')")
        reg = Registry()
        for pointer, obj in data.get("states", {}).items():
            if str(reg.put_state(obj)) != pointer:
                raise ValueError(f"Session state for {pointer} does not match its hash")
        ctx = ContextObject.load(data["context"], reg)
        return cls(ctx, max(0, min(int(data.get("playhead", 0)), len(ctx.trace))), p)

    @classmethod
    def from_trace(cls, trace: Trace, path: Path | str = DEFAULT_PATH, name: str = "sim") -> "Session":
        ctx = ContextObject(name)
        ctx.trace = trace
        if trace.rows:
            ctx.address = ctx.resolve(trace.rows[-1].address)
        return cls(ctx, 0, path)

    @staticmethod
    def reset(path: Path | str = DEFAULT_PATH) -> bool:
        p = Path(path)
        if p.exists():
            p.unlink()
            return True
        return False

    # ---------- transport ----------
    @property
    def length(self) -> int:
        return len(self.context.trace)

    def rewind(self, steps: int | None = None) -> int:
        self.playhead = 0 if steps is None else max(0, self.playhead - steps)
        return self.playhead

    def seek(self, step: int) -> int:
        self.playhead = max(0, min(step, self.length))
        return self.playhead

    def frames(self, steps: int | None = None) -> Iterator[Row]:
        end = self.length if steps is None else min(self.length, self.playhead + steps)
        while self.playhead < end:
            row = self.context.trace.rows[self.playhead]
            self.playhead += 1
            yield row

    def play(self, steps: int | None = None, output: str = "uri", speed: float = 0.0,
             out: Any = print, color: bool | None = None) -> int:
        """Print frames from the playhead. ``speed`` is seconds between frames (0 = no pause)."""
        n = 0
        for row in self.frames(steps):
            out(frame(row, self.context, output, self.length, color))
            n += 1
            if speed:
                time.sleep(speed)
        return n


def frame(row: Row, context: ContextObject, output: str = "uri", total: int | None = None, color: bool | None = None) -> str:
    addr = context.resolve(row.address)
    head = paint(f"Step {row.index}" + (f"/{total - 1}" if total else ""), "bold", color=color)
    change = f"{row.op} {row.key}" + (f" = {row.value}" if row.value else "")
    flag = "  " + paint("learnable", "magenta", color=color) if row.learnable else ""
    body = convert(addr, output)
    body = paint(body, "cyan", color=color) if output == "uri" else body
    return f"{head}  {paint(row.time, 'dim', color=color)}  {change}  ({row.cause}){flag}\n{body}\n"
