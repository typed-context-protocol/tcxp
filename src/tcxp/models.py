"""Real model checkers: Jev (TypeSafe) and Claude (Anthropic).

Standard library only (``urllib``), so they work in Colab with nothing extra installed.
Keys come from the arguments or the environment: ``JEV_API_KEY`` and ``ANTHROPIC_API_KEY``.
Both return the same ``Answer`` shape as every other rung of the ladder. Network or
API errors come back as an Answer with ``error`` set, so the ladder simply moves on.

Prices are per million tokens and editable. Jev: $0.042 input, output free (from its
docs). Claude defaults are for Haiku 4.5 ($1 / $5); set them for the model you use.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .ladder import NOT_STATED, Answer, Question

__all__ = ["JevChecker", "ClaudeChecker"]


def _post(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> tuple[int, Any, float]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            payload: Any = json.loads(text)
        except ValueError:
            payload = {"error": text}
        return exc.code, payload, (time.perf_counter() - t0) * 1000
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": str(exc)}, (time.perf_counter() - t0) * 1000


def _err(payload: Any) -> str:
    if isinstance(payload, dict):
        e = payload.get("error")
        if isinstance(e, dict):
            return e.get("message", json.dumps(e))
        return str(e or payload.get("detail") or payload)
    return str(payload)


class JevChecker:
    """Ask Jev a Noul (yes/no) or Choice question about ``Question.text``."""

    def __init__(self, api_key: str | None = None, model: str = "jev-latest", name: str = "jev",
                 price_in: float = 0.042, timeout: float = 30.0,
                 url: str = "https://api.typesafe.ai/v1/systemone"):
        self.api_key = api_key or os.environ.get("JEV_API_KEY", "")
        self.model, self.name, self.price_in, self.timeout, self.url = model, name, price_in, timeout, url

    def check(self, q: Question) -> Answer:
        if not self.api_key:
            return Answer(None, 0.0, self.name, error="No Jev key: pass api_key or set JEV_API_KEY")
        state: dict[str, Any] = {"request": q.text}
        if q.context:
            state["context"] = q.context
        if q.kind == "bool":
            question = {"type": "noul", "instructions": q.ask or "Is this true?"}
        else:
            question = {"type": "choice", "instructions": q.ask or "Which option applies?",
                        "criteria": {o: q.descriptions.get(o, o) for o in q.options}}
        status, payload, ms = _post(self.url, {"Authorization": f"Bearer {self.api_key}"},
                                    {"model": self.model, "state": state, "questions": {"q": question}}, self.timeout)
        if status != 200:
            return Answer(None, 0.0, self.name, ms, error=f"HTTP {status}: {_err(payload)}", raw=payload)
        a = payload["answers"]["q"]
        tin = payload.get("usage", {}).get("input_tokens", 0)
        if q.kind == "bool":
            p = float(a["noul"])
            value, conf = p >= 0.5, max(p, 1 - p)
        else:
            value, conf = a["choice"], float(a["confidence"])
        return Answer(value, conf, self.name, ms, tin, payload.get("usage", {}).get("output_tokens", 0),
                      tin * self.price_in / 1e6, raw=payload)


class ClaudeChecker:
    """Ask Claude the same question and parse a JSON reply ``{"value": ..., "confidence": 0-1}``."""

    def __init__(self, api_key: str | None = None, model: str = "claude-haiku-4-5-20251001", name: str = "claude",
                 price_in: float = 1.0, price_out: float = 5.0, timeout: float = 60.0,
                 url: str = "https://api.anthropic.com/v1/messages"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model, self.name, self.price_in, self.price_out, self.timeout, self.url = model, name, price_in, price_out, timeout, url

    def check(self, q: Question) -> Answer:
        if not self.api_key:
            return Answer(None, 0.0, self.name, error="No Claude key: pass api_key or set ANTHROPIC_API_KEY")
        if q.kind == "bool":
            space = 'true or false'
        else:
            space = " | ".join(f'"{o}"' for o in q.options)
        system = (f"Answer the question about the user's request. Reply with only JSON: "
                  f'{{"value": {space}, "confidence": a number from 0 to 1}}.')
        if q.context:
            system += "\n\nRules from the context object:\n" + q.context
        user = f"Request: {q.text}\n\nQuestion: {q.ask}"
        body = {"model": self.model, "max_tokens": 60, "system": system, "messages": [{"role": "user", "content": user}]}
        status, payload, ms = _post(self.url, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, body, self.timeout)
        if status != 200:
            return Answer(None, 0.0, self.name, ms, error=f"HTTP {status}: {_err(payload)}", raw=payload)
        text = "".join(c.get("text", "") for c in payload.get("content", []))
        usage = payload.get("usage", {})
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cost = tin * self.price_in / 1e6 + tout * self.price_out / 1e6
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            parsed = json.loads(text[start:end])
            value, conf = parsed.get("value"), float(parsed.get("confidence", 0.5))
        except (ValueError, TypeError):
            return Answer(None, 0.0, self.name, ms, tin, tout, cost, error=f"Unparseable reply: {text[:80]}", raw=payload)
        if q.kind == "choice" and value not in q.options:
            value = NOT_STATED if NOT_STATED in q.options else value
        return Answer(value, conf, self.name, ms, tin, tout, cost, raw=payload)
