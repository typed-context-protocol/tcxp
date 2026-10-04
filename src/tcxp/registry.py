"""Registry: what addresses point to, and what happens when one is triggered.

An address can point to three kinds of thing, all through one registry:

* **Data:** ``registry.put(address, resource)`` then ``registry.get(address)``.
* **A function (handler):** registered with a decorator, like an Express route::

      @registry.on("!tcxp:/reason/tax-year")
      def tax_year(params, ctx): ...

      @registry.handler("my.check")          # called as "@my.check?x=1"
      def check(params, ctx): ...

* **A state snapshot:** ``registry.put_state(obj)`` stores canonical JSON and returns
  ``!tcxp:/state/sha256-<hash>``. ``get_state`` re-hashes on the way out, so a pointer
  that resolves is proof the state was not lost or changed.

Security rule: an address can *reference* a handler. It never contains code, and
triggering an address only ever runs handlers registered here.

Built-in handlers (``@core.*``) act on the context object passed to ``trigger``:
``@core.update?key=value`` sets keys, ``@core.highlight?color=yellow`` marks the
matched text, ``@core.ask?key=tax_year`` requests a value from a person,
``@core.halt?reason=...`` stops, ``@core.log?message=...`` writes a note,
``@core.notify?message=...`` raises an alert, ``@core.approve?gate=<id>&by=<who>`` approves a
proposed gate (``tcxp.flow``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from .address import Address, AddressError, parse_query

__all__ = ["Registry", "IntegrityError", "HandlerNotFound", "parse_handler", "canonical_json", "default_registry"]

Handler = Callable[[dict[str, Any], Any], Any]


class IntegrityError(RuntimeError):
    """A stored state no longer matches the hash in its address."""


class HandlerNotFound(LookupError):
    pass


def canonical_json(obj: Any) -> str:
    """One JSON spelling per value: sorted keys, no spaces, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def parse_handler(text: str) -> tuple[str, dict[str, Any]]:
    """``"@core.update?a=1&b=x&b=y"`` → ``("core.update", {"a": "1", "b": ["x", "y"]})``."""
    if not text.startswith("@"):
        raise AddressError("Handler references start with '@'")
    name, _, query = text[1:].partition("?")
    if not name or not all(c.isalnum() or c in "._-" for c in name):
        raise AddressError(f"Invalid handler name {name!r}")
    groups = parse_query(query)
    return name, {k: (v[0] if len(v) == 1 else list(v)) for k, v in groups.items()}


class Registry:
    def __init__(self, with_core: bool = True):
        self._resources: dict[str, Any] = {}
        self._states: dict[str, str] = {}
        self._named: dict[str, Handler] = {}
        self._routes: list[tuple[tuple[str, ...], Handler]] = []
        if with_core:
            _install_core(self)

    # ---------- data ----------
    def put(self, address: Address | str, resource: Any) -> Address:
        addr = address if isinstance(address, Address) else Address.parse(address)
        self._resources[str(addr)] = resource
        return addr

    def get(self, address: Address | str, default: Any = None) -> Any:
        key = str(address if isinstance(address, Address) else Address.parse(address))
        if key.startswith("!tcxp:/state/sha256-"):
            return self.get_state(key)
        return self._resources.get(key, default)

    def has(self, address: Address | str) -> bool:
        key = str(address if isinstance(address, Address) else Address.parse(address))
        prefix = "!tcxp:/state/sha256-"
        return key in self._resources or (key.startswith(prefix) and key[len(prefix):] in self._states)

    def addresses(self, prefix: str = "") -> list[str]:
        return sorted(a for a in self._resources if a.startswith(prefix))

    # ---------- content-addressed state ----------
    def put_state(self, obj: Any) -> Address:
        text = canonical_json(obj)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._states[digest] = text
        return Address.parse(f"!tcxp:/state/sha256-{digest}")

    def get_state(self, address: Address | str) -> Any:
        text = str(address)
        prefix = "!tcxp:/state/sha256-"
        if not text.startswith(prefix):
            raise AddressError("Not a state pointer")
        digest = text[len(prefix):]
        if digest not in self._states:
            raise KeyError(f"No state stored for {text}")
        stored = self._states[digest]
        if hashlib.sha256(stored.encode("utf-8")).hexdigest() != digest:
            raise IntegrityError(f"State for {text} has changed since it was stored")
        return json.loads(stored)

    # ---------- handlers ----------
    def handler(self, name: str) -> Callable[[Handler], Handler]:
        """Register a named handler, called as ``@name?key=value``."""
        def deco(fn: Handler) -> Handler:
            self._named[name] = fn
            return fn
        return deco

    def on(self, pattern: str) -> Callable[[Handler], Handler]:
        """Register a handler for a virtual path pattern; ``*`` matches one segment."""
        if pattern.startswith("@"):
            return self.handler(pattern[1:])
        segs = Address.parse(pattern.replace("*", "x-wildcard-x")).path
        segs = tuple("*" if s == "x-wildcard-x" else s for s in segs)

        def deco(fn: Handler) -> Handler:
            self._routes.append((segs, fn))
            return fn
        return deco

    def _route(self, addr: Address) -> Handler | None:
        for segs, fn in self._routes:
            if len(segs) == len(addr.path) and all(s == "*" or s == p for s, p in zip(segs, addr.path)):
                return fn
        return None

    def trigger(self, target: Address | str, context: Any = None, **extra: Any) -> Any:
        """Run what an address or ``@handler`` reference points to. Returns the handler's result."""
        if isinstance(target, str) and target.startswith("@"):
            name, params = parse_handler(target)
            fn = self._named.get(name)
            if fn is None:
                raise HandlerNotFound(f"No handler registered for @{name}")
            return fn({**params, **extra}, context)
        addr = target if isinstance(target, Address) else Address.parse(target)
        fn = self._route(addr)
        if fn is None:
            if self.has(addr):
                return self.get(addr)
            raise HandlerNotFound(f"Nothing registered at {addr}")
        return fn({**addr.to_dict(), **extra}, context)

    def handlers(self) -> list[str]:
        return sorted("@" + n for n in self._named) + sorted("!tcxp:/" + "/".join(s) for s, _ in self._routes)


def _install_core(reg: Registry) -> None:
    @reg.handler("core.update")
    def _update(params: dict[str, Any], ctx: Any) -> Any:
        cause = params.pop("_cause", "@core.update")
        params.pop("_spike", None)
        return ctx.update(params, cause=cause)

    @reg.handler("core.highlight")
    def _highlight(params: dict[str, Any], ctx: Any) -> Any:
        spike = params.get("_spike")
        mark = {"color": params.get("color", "yellow"), "start": getattr(spike, "start", -1),
                "end": getattr(spike, "end", -1), "sensor": getattr(spike, "sensor", "")}
        ctx.highlights.append(mark)
        return mark

    @reg.handler("core.ask")
    def _ask(params: dict[str, Any], ctx: Any) -> Any:
        keys = params.get("key", [])
        keys = [keys] if isinstance(keys, str) else keys
        for k in keys:
            if k not in ctx.asks:
                ctx.asks.append(k)
        return keys

    @reg.handler("core.halt")
    def _halt(params: dict[str, Any], ctx: Any) -> Any:
        ctx.halted = params.get("reason", "halted")
        return ctx.halted

    @reg.handler("core.notify")
    def _notify(params: dict[str, Any], ctx: Any) -> Any:
        msg = "ALERT: " + params.get("message", "")
        ctx.notes.append(msg)
        return msg

    @reg.handler("core.approve")
    def _approve(params: dict[str, Any], ctx: Any) -> Any:
        """Approve a proposed gate: calling this is the approval, and the trace records who."""
        from dataclasses import replace
        gid, by = params.get("gate", ""), params.get("by", "")
        if not by:
            raise ValueError("@core.approve needs by=<who approved>")
        for i, g in enumerate(ctx.reason):
            if getattr(g, "id", None) == gid and hasattr(g, "approved_by"):
                ctx.reason[i] = replace(g, status="approved", approved_by=by)
                ctx.trace.append("trigger", "gate", str(ctx.reason[i].address()), f"person:{by}", ctx.snapshot())
                return ctx.reason[i]
        raise LookupError(f"No gate {gid!r} to approve")

    @reg.handler("core.log")
    def _log(params: dict[str, Any], ctx: Any) -> Any:
        ctx.notes.append(params.get("message", ""))
        return params.get("message", "")


default_registry = Registry()
