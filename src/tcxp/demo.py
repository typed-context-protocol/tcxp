"""The Section 41 terminal demo.

Type a question such as "What should I deduct for Section 41 US-based QREs?".
On every line you see:

1. your text with sensor matches highlighted,
2. the context object's state (Lit in green, Dark in white on black),
3. the SQL card with its filled and missing slots,
4. the Governor's verdict.

When the manager's rule needs the tax year, the demo asks you. Your answer is
recorded as a learnable trace row, the card runs against ``payroll.csv``, and the
session is saved for ``tcxp play``.

Commands: ``:address [format]``, ``:trace``, ``:summary``, ``:rule <sentence>``, ``:ladder``, ``:help``, ``:quit``.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Callable, Iterable

from .address import Address
from .bench import ASK, CONTEXT_RULES, OPTIONS, SIM_JEV, SIM_LLM, detect_tax_year
from .bus import EventBus
from .context import ContextObject, Observatron, Sensor
from .convert import convert
from .governor import Rule
from .ladder import NOT_STATED, CodeChecker, Ladder, Question, SimulatedChecker
from .pretty import highlight, paint, show_address, show_card, show_trace, show_verdict
from .schema import Field, Schema
from .session import DEFAULT_PATH, Session
from .sql import Database, QueryCard, tax_year_bounds

__all__ = ["section41", "run", "MANAGER_RULE"]

MANAGER_RULE = "Don't give the answer until the tax year is confirmed"
_YEAR = r"(20\d{2})"


def section41(registry=None) -> tuple[ContextObject, Observatron, Database, QueryCard]:
    """Build the demo: sensors, schema, the manager's rule, the payroll table and the SQL card."""
    schema = Schema.of("section-41",
                       Field("task", values=("section_41_qre",), description="What kind of request this is"),
                       Field("tax_year", "int", ("2023", "2024", "2025"), essential=True, description="Tax year the answer is for"),
                       Field("country", values=("US", "CA"), description="Where the employees work"))
    sensors = [
        Sensor("task", "deduct|deduction|credit|section 41|r&d|qre|qres|qualified research", kind="keyword", key="task",
               meaning=("!tcxp:/tax/us/irc-41",),
               actions=("@core.update?task=section_41_qre&task.meaning=!tcxp:/tax/us/irc-41", "@core.highlight?color=yellow"),
               description="A Section 41 R&D question"),
        Sensor("country-us", "us-based|us based|in the us|united states|u.s.|us employees", kind="keyword", key="country",
               meaning=("!tcxp:/geo/iso-3166/US",),
               actions=("@core.update?country=US&country.meaning=!tcxp:/geo/iso-3166/US", "@core.highlight?color=cyan")),
        Sensor("tax-year", r"\b(?:tax\s*year|fiscal\s*year|tax\s*return|return|filing)\s*(?:of|for|is|:)?\s*'?" + _YEAR + r"\b",
               key="tax_year", structure=("!tcxp:/schema/year/yyyy",),
               actions=("@core.update?tax_year={1}&tax_year.structure=!tcxp:/schema/year/yyyy", "@core.highlight?color=green")),
        Sensor("tax-year-before", r"\b" + _YEAR + r"\s+(?:tax\s*year|tax\s*return|return|filing)\b", key="tax_year",
               actions=("@core.update?tax_year={1}&tax_year.structure=!tcxp:/schema/year/yyyy", "@core.highlight?color=green")),
        Sensor("fiscal-short", r"\bFY\s?'?(\d{2})\b", key="tax_year",
               actions=("@core.update?tax_year=20{1}&tax_year.structure=!tcxp:/schema/year/yyyy", "@core.highlight?color=green")),
        Sensor("relative-date", "yesterday|last year|this year|last month|last quarter", kind="keyword", key="relative",
               actions=("@core.update?relative={0}", "@core.highlight?color=red",
                        "@core.log?message=relative%20date:%20needs%20a%20reference%20date")),
        Sensor("project-year", r"\b(?:started|launched|began|kicked off)\b[^.?!]*?\b" + _YEAR + r"\b", key="project_year",
               actions=("@core.update?project_year={1}", "@core.highlight?color=magenta",
                        "@core.log?message=a%20project%20year%20is%20not%20the%20tax%20year")),
    ]
    ctx = ContextObject("reason/section-41", schema, sensors, registry=registry,
                        params={"task": "", "country": "", "tax_year": "", "tax_year.meaning": "!tcxp:/tax/us/tax-year",
                                "tax_year.structure": "", "tax_year.environment": ""})
    ctx.add_rule(Rule.compile(MANAGER_RULE, by="manager", slots={"tax year": "tax_year"}))
    db = Database(ctx.registry)
    db.load_csv("payroll", resources.files("tcxp").joinpath("data/payroll.csv").read_text(encoding="utf-8"))
    card = QueryCard("us-wages", "US wages in the tax year",
                     "SELECT SUM(wages) FROM payroll WHERE country = :country AND pay_date BETWEEN :start_date AND :end_date",
                     derive=tax_year_bounds)
    return ctx, Observatron(ctx, "query", EventBus(keep_history=True)), db, card


def _ladder() -> Ladder:
    return Ladder([CodeChecker("code", lambda q: (detect_tax_year(q.text), 1.0) if detect_tax_year(q.text) else None),
                   SimulatedChecker("jev", **SIM_JEV), SimulatedChecker("llm", **SIM_LLM)], 0.8)


def run(lines: Iterable[str] | None = None, answer: Callable[[str], str] | None = None,
        session_path: Path | str = DEFAULT_PATH, color: bool | None = None, out: Callable[[str], None] = print,
        show_ladder: bool = False) -> ContextObject:
    """Run the demo. ``lines`` and ``answer`` make it scriptable (tests); otherwise it reads the terminal."""
    ctx, obs, db, card = section41()
    interactive = lines is None
    ask = answer or (lambda prompt: input(prompt))
    source = iter(lines) if lines is not None else None
    out(paint("tcxp Section 41 demo", "bold", color=color) + "  (type a question; :help for commands; :quit to exit)")
    out(paint("Manager's rule: ", "dim", color=color) + MANAGER_RULE + "\n  " + str(ctx.reason[0].address()))
    session = Session(ctx, 0, session_path)
    while True:
        try:
            line = input(paint("\nquery> ", "bold", color=color)) if interactive else next(source)
        except (EOFError, StopIteration, KeyboardInterrupt):
            break
        line = line.strip()
        if not interactive:
            out(paint("\nquery> ", "bold", color=color) + line)   # echo scripted input like a terminal would
        if not line:
            continue
        if line.startswith(":"):
            cmd, _, arg = line[1:].partition(" ")
            if cmd in ("quit", "q", "exit"):
                break
            if cmd == "address":
                out(convert(ctx.address, arg or "uri"))
            elif cmd == "trace":
                out(show_trace(ctx.trace, 15, color))
            elif cmd == "summary":
                out(str(ctx.trace.summary()))
            elif cmd == "rule":
                r = ctx.add_rule(arg, by="manager", slots={"tax year": "tax_year", "country": "country"})
                out("Rule added: " + str(r.address()))
            elif cmd == "ladder":
                show_ladder = not show_ladder
                out(f"Ladder display {'on' if show_ladder else 'off'}")
            else:
                out(__doc__.strip().splitlines()[-1])
            continue
        o = obs.feed(line)
        out("\n" + highlight(line, o.highlights, color))
        for note in ctx.notes[-2:]:
            out(paint("  note: " + note, "dim", color=color))
        ctx.notes.clear()
        out(show_address(ctx.address, ctx.schema.essential, color))
        out(show_card(card, ctx.address.to_dict(), color))
        out(show_verdict(o.verdict, color))
        if show_ladder:
            res = _ladder().run(Question("q", line, ASK, "choice", OPTIONS, context=CONTEXT_RULES))
            steps = ", ".join(f"{a.source}={a.value}@{a.confidence:.2f}" for a in res.steps)
            out(paint(f"  ladder (simulated rungs): {steps} → {res.verdict} by {res.decided_by}", "dim", color=color))
        if o.verdict.kind == "ASK" and "tax_year" in o.verdict.missing:
            prompt = paint("  Which tax year is this for? [2023/2024/2025] > ", "bold", color=color)
            reply = ask(prompt).strip()
            if not interactive:
                out(prompt + reply)
            if reply:
                try:
                    ctx.confirm("tax_year", int(reply), by="you", features=line)
                    ctx.set("tax_year.structure", ["!tcxp:/schema/year/yyyy"], "person:you")
                except ValueError:
                    out("  Not a year; still Dark.")
                v = ctx.decide("answer")
                out(show_verdict(v, color))
        if ctx.decision[-1].kind == "ACT" and not card.missing(ctx.address.to_dict()):
            res = card.run(db, ctx.address.to_dict())
            out(paint("  result: ", "bold", color=color) + paint(f"{res.columns[0]} = {res.scalar()}", "green", color=color)
                + paint(f"   ({card.address(ctx.address.to_dict())})", "dim", color=color))
        session.save()
    session.save()
    out(paint(f"\nSession saved to {session.path}. Replay it with: tcxp play", "dim", color=color))
    return ctx
