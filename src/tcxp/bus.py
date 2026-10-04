"""A tiny event bus (publish / subscribe), like the one you would use in JavaScript.

    bus = EventBus()
    off = bus.on("spike", lambda event: print(event))
    bus.emit("spike", {"sensor": "tax-year"})
    off()   # unsubscribe

Subscribe to ``"*"`` to hear every topic; those handlers receive
``{"topic": ..., "payload": ...}``. Handlers run in the order they subscribed.
"""
from __future__ import annotations

from typing import Any, Callable

__all__ = ["EventBus"]

Handler = Callable[[Any], None]


class EventBus:
    def __init__(self, keep_history: bool = False):
        self._subs: dict[str, list[Handler]] = {}
        self.history: list[tuple[str, Any]] | None = [] if keep_history else None

    def on(self, topic: str, handler: Handler) -> Callable[[], None]:
        self._subs.setdefault(topic, []).append(handler)

        def off() -> None:
            if handler in self._subs.get(topic, []):
                self._subs[topic].remove(handler)
        return off

    def once(self, topic: str, handler: Handler) -> Callable[[], None]:
        def wrapper(payload: Any) -> None:
            off()
            handler(payload)
        off = self.on(topic, wrapper)
        return off

    def emit(self, topic: str, payload: Any = None) -> None:
        if self.history is not None:
            self.history.append((topic, payload))
        for h in list(self._subs.get(topic, [])):
            h(payload)
        if topic != "*":
            for h in list(self._subs.get("*", [])):
                h({"topic": topic, "payload": payload})

    def clear(self) -> None:
        self._subs.clear()
