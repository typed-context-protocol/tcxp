"""The ``tcxp`` command (also ``python -m tcxp``).

    tcxp version [--output json]
    tcxp demo [--ladder] [--session FILE]
    tcxp play [--steps N] [--output FORMAT] [--speed SECONDS]
    tcxp roll [--speed 1] [--steps N] [--past 3] [--future 2] [--export frames.json]
    tcxp sequencer play | rewind | seek N | status | reset
    tcxp rewind [N]   |   tcxp seek N   |   tcxp status   |   tcxp reset
    tcxp sim [--address ADDR] [--gate] [--compare] [--record] [--employees N ...]
    tcxp bench [--real] [--details]
    tcxp sql "SELECT ..." --csv name=file.csv [--param key=value]
    tcxp convert ADDRESS --output FORMAT
    tcxp budget --steps 6 --cost 50000 --tolerated 100 --volume 40 --answered 90
    tcxp learn
    tcxp fleet [--observatrons 10000] [--no-share] [--drift-epoch 5] [--real --limit 200] [-o json]

Formats: uri, json, dict, csv, sql, python, js, cpp, java.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from dataclasses import fields

from . import __uri__, __version__
from .convert import FORMATS, convert


def _cmd_version(a: argparse.Namespace) -> int:
    print(convert(__uri__, a.output))
    return 0


def _cmd_demo(a: argparse.Namespace) -> int:
    from .demo import run
    run(session_path=a.session, show_ladder=a.ladder)
    return 0


def _session(a: argparse.Namespace):
    from .session import Session
    return Session.load(a.session)


def _cmd_play(a: argparse.Namespace) -> int:
    s = _session(a)
    if s.playhead >= s.length:
        print(f"At the end ({s.length} steps). Use `tcxp rewind` to start again.")
        return 0
    s.play(a.steps, a.output, a.speed)
    s.save()
    print(f"playhead: {s.playhead}/{s.length}")
    return 0


def _cmd_roll(a: argparse.Namespace) -> int:
    import json as _json
    from .roll import Roll, steps_from_session
    s = _session(a)
    roll = Roll(steps_from_session(s), past=a.past, future=a.future)
    if a.export:
        from pathlib import Path
        Path(a.export).write_text(_json.dumps(roll.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Exported {len(roll.steps)} frames to {a.export}")
        return 0
    if s.playhead >= s.length:
        s.rewind()
    s.playhead = roll.play(s.playhead, a.steps, a.speed)
    s.save()
    print(f"playhead: {s.playhead}/{s.length}")
    return 0


def _cmd_sequencer(a: argparse.Namespace) -> int:
    return {"play": _cmd_roll, "rewind": _cmd_rewind, "seek": _cmd_seek, "status": _cmd_status,
            "reset": _cmd_reset}[a.action](a)


def _cmd_rewind(a: argparse.Namespace) -> int:
    s = _session(a)
    s.rewind(a.n)
    s.save()
    print(f"playhead: {s.playhead}/{s.length}")
    return 0


def _cmd_seek(a: argparse.Namespace) -> int:
    if a.n is None:
        raise ValueError("seek needs a step number, e.g. `tcxp seek 5`")
    s = _session(a)
    s.seek(a.n)
    s.save()
    print(f"playhead: {s.playhead}/{s.length}")
    return 0


def _cmd_status(a: argparse.Namespace) -> int:
    s = _session(a)
    problems = s.context.trace.verify(s.context.registry)
    print(f"session: {s.path}\nplayhead: {s.playhead}/{s.length}\naddress: {s.context.address}\n"
          f"trace: {'intact' if not problems else '; '.join(problems)}")
    return 0 if not problems else 1


def _cmd_reset(a: argparse.Namespace) -> int:
    from .session import Session
    print("Session deleted." if Session.reset(a.session) else "No session to delete.")
    return 0


def _cmd_sim(a: argparse.Namespace) -> int:
    from .sim import STORIES, Organization, SimConfig, story
    from .pretty import table
    kw = {f.name: getattr(a, f.name) for f in fields(SimConfig) if getattr(a, f.name, None) is not None}
    if a.story == "list":
        print(table(["story", "what it simulates"], [[k, d] for k, (d, _) in STORIES.items()]))
        print("\nRun one with: tcxp sim --story launch --compare   (any flag overrides the story's setting)")
        return 0
    if a.address:
        cfg = SimConfig.from_address(a.address)
    elif a.story:
        cfg = story(a.story, **kw)
        print(STORIES[a.story][0])
    else:
        cfg = SimConfig(**kw)
    configs = [(cfg.__class__(**{**cfg.__dict__, "gate": False}), "no gate"),
               (cfg.__class__(**{**cfg.__dict__, "gate": True}), "gate")] if a.compare else [(cfg, "gate" if cfg.gate else "no gate")]
    rows, last = [], None
    for c, label in configs:
        res = Organization(c).run()
        m = res.metrics
        rows.append([label, m["decisions"], m["silent_errors"], f"{m['accuracy']:.1%}", m["asks"],
                     f"{m['regret']:,.0f}", f"{m['ask_cost']:,.0f}", f"{m['total_cost']:,.0f}", m["hops"], m["dark_hops"]])
        last = res
        print(convert(c.to_address(), "uri"))
    print(table(["run", "decisions", "silent errors", "accuracy", "asks", "regret", "ask cost", "total", "hops", "dark hops"], rows))
    if cfg.teams and last is not None:                  # where the silent errors started
        runs = [(label, Organization(c).run()) for c, label in configs] if a.compare else [(configs[0][1], last)]
        trows = []
        for label, res in runs:
            for r in res.by_team():
                trows.append([label, r["team"], r["decisions"], r["silent_errors"], f"{r['accuracy']:.1%}", r["asks"],
                              f"{r['regret']:,.0f}"])
        print("\nBy the team where each decision started:")
        print(table(["run", "team", "decisions", "silent errors", "accuracy", "asks", "regret"], trows))
    if a.record and last is not None:
        from .session import Session
        s = Session.from_trace(last.to_trace(), a.session)
        s.save()
        print(f"Recorded {s.length} hops to {s.path}. Replay with: tcxp play --steps 10")
    return 0


def _spark(hist: list[int]) -> str:
    import math
    bars, top = "▁▂▃▄▅▆▇█", math.log1p(max(hist) or 1)
    return "".join(bars[min(7, int(math.log1p(v) / top * 7.999))] if v else " " for v in hist)   # log scale


def _cmd_fleet(a: argparse.Namespace) -> int:
    from .fleet import ARMS, Fleet, FleetConfig
    from .pretty import paint, table
    kw = {k: v for k, v in {"observatrons": a.observatrons, "requests_per": a.requests_per, "epochs": a.epochs,
                            "drift_epoch": a.drift_epoch, "seed": a.seed}.items() if v is not None}
    if a.no_share:
        kw["share"] = False
    cfg = FleetConfig.from_address(a.address) if a.address else FleetConfig(**kw)
    res = Fleet(cfg, "real" if a.real else "simulated", a.limit).run()
    if a.output == "json":
        print(json.dumps({"config": str(cfg.to_address()), "totals": [res.totals(x) for x in ARMS], "delta": res.delta(),
                          "epochs": {x: [vars(e) for e in res.epochs[x]] for x in ARMS}}, indent=2))
        return 0
    print(paint(str(cfg.to_address()), "dim"))
    print(f"{len(res.epochs[ARMS[0]]) and sum(e.n for e in res.epochs[ARMS[0]]):,} requests across {cfg.observatrons:,} Observatrons, "
          f"{'one shared guard' if cfg.share else 'a separate guard per Observatron'}\n")
    rows = []
    for x in ARMS:
        t = res.totals(x)
        rows.append([x, f"{t['accuracy']:.2%}", f"{t['silent_errors']:,}", f"{t['asks']:,}", f"${t['model_cost']:,.2f}",
                     f"${t['regret']:,.0f}", f"${t['risk_taken']:,.0f}", f"${t['total_cost']:,.0f}"])
    print(table(["arm", "accuracy", "silent errors", "asks", "model cost", "regret (realized)", "risk taken (predicted)", "total cost"], rows))
    d = res.delta()
    print(f"\nWith typed context objects vs. the LLM alone: accuracy {d['accuracy']:+.2%}, silent errors {d['silent_errors']:+,.0f}, "
          f"total cost {d['total_cost']:+,.0f}")
    t = res.totals("context_learning")
    print(f"Guard acted alone on {t['guard_acted']:,} requests at {t['guard_accuracy']:.2%} accuracy; "
          f"on never-seen phrasings {t['guard_novel_acted']:,} at {t['guard_novel_accuracy']:.2%}. "
          f"Vetoes: {t['vetoes']} ({t['vetoes_right']} right). Labels learned: {t['labels']:,}.\n")
    erows = []
    for e in res.epochs["context_learning"]:
        acted = e.by.get("guard", 0)
        erows.append([e.epoch, e.n, f"{acted / e.n:.0%}" if e.n else "–",
                      f"{e.guard_confident_right / e.guard_confident:.1%}" if e.guard_confident else "–",
                      f"{e.guard_novel_right}/{e.guard_novel}" if e.guard_novel else "–", e.silent_errors,
                      e.by.get("jev", 0) + e.by.get("llm", 0), _spark(e.hist)])
    print(table(["epoch", "requests", "guard coverage", "guard accuracy", "new phrasings right", "silent errors",
                 "model calls", "guard confidence 0→1"], erows))
    if not a.real:
        print("\nSimulated Jev/LLM rungs use declared assumptions (tcxp.bench). Requests are synthetic templates; "
              "treat accuracy on them as an upper bound.")
    return 0


def _cmd_flow(a: argparse.Namespace) -> int:
    from .flow import repl
    lines = None
    if a.query:
        lines = [*(f":card {c}" for c in (a.card or [])), *([":approve all"] if a.card and a.approve else []), a.query]
    elif a.card:
        lines = [*(f":card {c}" for c in a.card)]
    repl(lines, cards=not a.empty, approve=not a.proposed, session_path=a.session)
    return 0


def _cmd_expr(a: argparse.Namespace) -> int:
    from .expr import draw, fold, from_address, parse, solve, to_address
    from .pretty import paint, table
    text = a.expression
    tree = from_address(text) if text.startswith(("!tcxp:", "tcxp:")) else parse(text)
    state: dict[str, str] = {}
    for p in a.set or []:
        k, eq, v = p.partition("=")
        if not eq or not k:
            raise ValueError(f"--set expects name=value, got {p!r}")
        state[k] = v
    addr = to_address(tree)
    f = fold(tree, state)
    solved = solve(tree, state) if a.solve and f.dark else {}
    if a.output == "json":
        print(json.dumps({"address": str(addr), "value": f.steps[-1]["result"] if f.steps and f.complete else (None if f.value is None else str(f.value)),
                          "dark": list(f.dark), "steps": f.steps,
                          "solved": {k: str(v) for k, v in solved.items()}}, indent=2))
        return 0
    print(paint(str(addr), "dim"))
    print()
    print(draw(tree, state))
    print()
    if f.steps:
        print(table(["node", "op", "left", "right", "result"],
                    [[r["node"], r["op"], r["left"], r["right"], r["result"]] for r in f.steps]))
        print()
    if f.dark:
        print(f"Dark: {', '.join(f.dark)}. The fold stops here: ask for {'it' if len(f.dark) == 1 else 'them'} instead of guessing.")
        for k, v in solved.items():
            shown = str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator} ({float(v):g})"
            print(f"Solved without a model: {k} = {shown}")
    else:
        print(f"Result: {f.steps[-1]['result'] if f.steps else f.value}")
    return 0


def _docs_path() -> Path:
    from importlib import resources
    p = Path(str(resources.files("tcxp") / "web" / "index.html"))
    if not p.is_file():
        raise FileNotFoundError("The docs page isn't bundled in this install. Run `python tools/build_docs.py`.")
    return p


def _cmd_docs(a: argparse.Namespace) -> int:
    page = _docs_path()
    if a.path:
        print(page.parent / "flow" / "index.html" if a.flow else page)
        return 0
    import functools
    import http.server
    import threading
    import webbrowser

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(page.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/{'flow/index.html' if a.flow else 'index.html'}"
    print(f"tcxp docs at {url}  (Ctrl+C to stop)")
    if not a.no_open:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _cmd_bench(a: argparse.Namespace) -> int:
    from .bench import CASES, run_bench
    from .pretty import table
    rows = run_bench("real" if a.real else "simulated", seed=a.seed)
    print(table(["arm", "correct", "silent errors", "extra asks", "errors", "time (ms)", "tokens", "cost ($)", "source"],
                [[r.arm, f"{r.correct}/{len(CASES)}", r.silent_errors, r.extra_asks, r.errors, f"{r.ms:,.0f}", r.tokens,
                  f"{r.cost:.6f}", "simulated" if r.simulated else ("code" if r.arm == "code" else "real")] for r in rows]))
    if a.details:
        for r in rows:
            print(f"\n{r.arm}")
            for d in r.details:
                print(f"  {d['outcome']:<12} {d['verdict']} {str(d['value']):<10} by {d['decided_by']:<6} {d['case']}")
    if not a.real:
        print("\nSimulated rungs use the declared assumptions in tcxp.bench.SIM_JEV and SIM_LLM. Run with --real for API calls.")
    return 0


def _cmd_sql(a: argparse.Namespace) -> int:
    from .sql import Database
    from .pretty import table
    db = Database()
    for spec in a.csv or []:
        name, eq, path = spec.partition("=")
        if not eq or not name or not path:
            raise ValueError(f"--csv expects name=path.csv, got {spec!r}")
        db.load_csv_file(name, path)
    if not a.csv:                                   # no files given: the bundled sample table
        from importlib import resources
        db.load_csv("payroll", (resources.files("tcxp") / "data" / "payroll.csv").read_text(encoding="utf-8"))
    params = {}
    for p in a.param or []:
        k, eq, v = p.partition("=")
        if not eq or not k:
            raise ValueError(f"--param expects slot=value, got {p!r}")
        params[k] = v
    res = db.query(a.query, params)
    print(table(res.columns, res.rows))
    return 0


def _cmd_convert(a: argparse.Namespace) -> int:
    print(convert(a.address, a.output))
    return 0


def _cmd_budget(a: argparse.Namespace) -> int:
    from .reliability import budget
    b = budget(a.steps, a.cost, a.tolerated, a.volume, a.answered, a.floor, a.confidence, a.failures)
    print(json.dumps({"error_you_can_afford": b.e2e, "error_per_step": b.per_step, "verified_cases_per_step": b.cases,
                      "weeks": b.weeks, "recommendation": b.recommendation}, indent=2))
    return 0


def _cmd_learn(a: argparse.Namespace) -> int:
    from .bench import CASES
    from .learn import SoftmaxPerceptron, examples_from_trace, reliability_curve
    from .pretty import table
    # training phrasings are deliberately different from the 10 held-out benchmark requests
    train = [("Pull the QRE numbers for tax year 2023", "stated"), ("Credit estimate for FY25 please", "stated"),
             ("Prepare the 2024 filing figures for research wages", "stated"),
             ("For the 2023 return, list qualified wages", "stated"), ("Tax year 2025: what is our research spend?", "stated"),
             ("Use fiscal year 2024 for the R&D credit", "stated"),
             ("What can we write off for research?", "not_stated"), ("Estimate our research credit", "not_stated"),
             ("Which wages count toward the R&D credit?", "not_stated"),
             ("Our Beacon project began in 2024, what qualifies?", "not_stated"),
             ("How much did engineering cost us?", "not_stated"), ("What did we spend on prototypes this year?", "not_stated")]
    try:
        from .session import Session
        s = Session.load(a.session)
        texts, labels = examples_from_trace(s.context.trace, "tax_year")
        train += [(t, "stated") for t in texts]
        print(f"Added {len(texts)} confirmed example(s) from {s.path}")
    except FileNotFoundError:
        pass
    test = [(t, "not_stated" if y == "not_stated" else "stated") for t, y in CASES]
    curve = reliability_curve(train, test, ["stated", "not_stated"])
    print(table(["examples per class", "accuracy", "accuracy when confident", "coverage"],
                [[k, f"{e.accuracy:.0%}", "–" if e.confident_accuracy is None else f"{e.confident_accuracy:.0%}", f"{e.coverage:.0%}"]
                 for k, e in curve]))
    print("\nHeld-out test: the 10 benchmark requests. Treat small-sample numbers as a shape, not a promise.")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows writes piped output in the locale code page (cp1252), which can't encode `→`.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8", errors="replace")
    from .session import DEFAULT_PATH
    p = argparse.ArgumentParser(prog="tcxp", description=f"tcxp {__version__}: the Typed ConteXt Protocol")
    p.add_argument("--session", default=str(DEFAULT_PATH), help="session file (default: ./tcxp-session.json)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--session", default=argparse.SUPPRESS, help="session file (default: ./tcxp-session.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    _add = sub.add_parser
    sub.add_parser = lambda *a, **k: _add(*a, parents=[common], **k)  # every command accepts --session

    s = sub.add_parser("version", help="print the library version as an address")
    s.add_argument("--output", "-o", default="uri", choices=FORMATS)
    s.set_defaults(fn=_cmd_version)

    s = sub.add_parser("demo", help="the Section 41 terminal demo")
    s.add_argument("--ladder", action="store_true", help="also show the code → Jev → LLM ladder (simulated)")
    s.set_defaults(fn=_cmd_demo)

    s = sub.add_parser("play", help="play the session from the playhead")
    s.add_argument("--steps", type=int, default=None)
    s.add_argument("--output", "-o", default="uri", choices=FORMATS)
    s.add_argument("--speed", type=float, default=0.0, help="seconds between frames")
    s.set_defaults(fn=_cmd_play)

    def _roll_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("--speed", type=float, default=1.0, help="seconds per step (default 1)")
        s.add_argument("--steps", type=int, default=None, help="how many steps to play")
        s.add_argument("--past", type=int, default=3, help="past columns shown")
        s.add_argument("--future", type=int, default=2, help="upcoming columns shown")
        s.add_argument("--export", help="write the roll frames to a JSON file instead of playing")

    s = sub.add_parser("roll", help="play the session as a context roll (a piano roll for addresses)")
    _roll_args(s)
    s.set_defaults(fn=_cmd_roll)

    s = sub.add_parser("sequencer", help="sequencer-style alias: sequencer play|rewind|seek N|status|reset")
    s.add_argument("action", choices=["play", "rewind", "seek", "status", "reset"])
    s.add_argument("n", nargs="?", type=int, default=None)
    _roll_args(s)
    s.set_defaults(fn=_cmd_sequencer)

    s = sub.add_parser("rewind", help="move the playhead back (to the start, or N steps)")
    s.add_argument("n", nargs="?", type=int, default=None)
    s.set_defaults(fn=_cmd_rewind)

    s = sub.add_parser("seek", help="move the playhead to step N")
    s.add_argument("n", type=int)
    s.set_defaults(fn=_cmd_seek)

    sub.add_parser("status", help="playhead, current address, and whether the trace is intact").set_defaults(fn=_cmd_status)
    sub.add_parser("reset", help="delete the session file").set_defaults(fn=_cmd_reset)

    s = sub.add_parser("sim", help="run the organization simulator",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       description="Simulate an organization handing decisions between people and agents.\n"
                                   "Settings never stick between runs: each command starts from the defaults (or a story).\n"
                                   "Each hand-off can lose the format of a fact (e.g. MM/DD vs DD/MM). Without the\n"
                                   "gate, the next person guesses; with it, they ask. Unset flags use the defaults.",
                       epilog="examples:\n"
                              "  tcxp sim --story list                                named scenarios\n"
                              "  tcxp sim --story launch --compare                    6,000 people in three teams\n"
                              "  tcxp sim --teams sales:300:0.4,ops:100:0.1 --compare your own teams\n"
                              "  tcxp sim --compare                                   same organization, with and without the gate\n"
                              "  tcxp sim --employees 200 --agents 40 --ambiguity 0.5 --cost-error 25000 --compare\n"
                              "  tcxp sim --address '!tcxp:/sim/org?employees=200&gate=true'   the whole setup as one address\n"
                              "  tcxp sim --tasks 1 --steps-min 6 --steps-max 6 --ambiguity 1 --record && tcxp roll")
    s.add_argument("--address", help="a !tcxp:/sim/org?... address (overrides the flags)")
    s.add_argument("--compare", action="store_true", help="run with and without the gate")
    s.add_argument("--record", action="store_true", help="save the hops as a session for tcxp play")
    s.add_argument("--story", metavar="NAME", help="start from a named scenario; 'list' shows them all")
    from .sim import HELP as _SIM_HELP, SimConfig as _SimConfig
    for f in fields(_SimConfig):
        h = f"{_SIM_HELP.get(f.name, '')} (default: {f.default})"
        if f.type in ("bool", bool):   # --gate / --no-gate
            s.add_argument(f"--{f.name.replace('_', '-')}", dest=f.name, action=argparse.BooleanOptionalAction,
                           default=None, help=h)
        elif f.type in ("str", str):
            s.add_argument(f"--{f.name.replace('_', '-')}", dest=f.name, metavar="SPEC", help=h.replace("(default: )", ""))
        else:
            s.add_argument(f"--{f.name.replace('_', '-')}", dest=f.name, type=float if f.type in ("float", float) else int,
                           metavar="N", help=h)
    s.set_defaults(fn=_cmd_sim)

    s = sub.add_parser("bench", help="benchmark code, Jev and LLM arms on the tax-year question")
    s.add_argument("--real", action="store_true", help="call Jev and Claude (needs JEV_API_KEY and ANTHROPIC_API_KEY)")
    s.add_argument("--details", action="store_true")
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=_cmd_bench)

    s = sub.add_parser("sql", help="run a tcxp-sql/0.1 query over CSV files")
    s.add_argument("query")
    s.add_argument("--csv", action="append", help="name=path.csv (repeatable; default: the sample table 'payroll')")
    s.add_argument("--param", action="append", help="slot=value (repeatable)")
    s.set_defaults(fn=_cmd_sql)

    s = sub.add_parser("convert", help="convert an address to another format")
    s.add_argument("address")
    s.add_argument("--output", "-o", default="json", choices=FORMATS)
    s.set_defaults(fn=_cmd_convert)

    s = sub.add_parser("budget", help="verified examples needed before automating a decision")
    for name, typ, default in (("steps", int, 1), ("cost", float, None), ("tolerated", float, None), ("volume", float, 0.0),
                               ("answered", float, 100.0), ("floor", float, 95.0), ("confidence", float, 0.95), ("failures", int, 0)):
        s.add_argument(f"--{name}", type=typ, default=default, required=default is None)
    s.set_defaults(fn=_cmd_budget)

    sub.add_parser("learn", help="train the perceptron and print its reliability curve").set_defaults(fn=_cmd_learn)

    s = sub.add_parser("fleet", help="many Observatrons: inference, cost and risk with and without context objects",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       description="Run the same requests through four setups: LLM alone, Jev alone, typed context,\n"
                                   "and typed context with perceptron guards that learn from confirmed answers.",
                       epilog="examples:\n"
                              "  tcxp fleet                                   10,000 Observatrons, 10 epochs\n"
                              "  tcxp fleet --observatrons 500 --epochs 4 --drift-epoch 2\n"
                              "  tcxp fleet --real --limit 50                 real Jev and Claude calls (needs keys)\n"
                              "  tcxp fleet -o json > fleet.json")
    s.add_argument("--address", help="a !tcxp:/sim/fleet?... address (overrides the flags)")
    s.add_argument("--observatrons", type=int, metavar="N", help="independent agents, each with its own context object (default: 10000)")
    s.add_argument("--requests-per", type=int, dest="requests_per", metavar="N", help="requests per Observatron per epoch (default: 3)")
    s.add_argument("--epochs", type=int, metavar="N", help="rounds of requests; guards learn between rounds (default: 10)")
    s.add_argument("--drift-epoch", type=int, dest="drift_epoch", help="epoch when new phrasings start (-1 = never)")
    s.add_argument("--seed", type=int, metavar="N", help="random seed (default: 7)")
    s.add_argument("--no-share", action="store_true", help="a separate guard per Observatron")
    s.add_argument("--real", action="store_true", help="call Jev and Claude (use --limit to cap spend)")
    s.add_argument("--limit", type=int, help="only the first N requests")
    s.add_argument("--output", "-o", choices=["table", "json"], default="table")
    s.set_defaults(fn=_cmd_fleet)

    s = sub.add_parser("flow", help="decision flow: query box, reasoning cards, gates (interactive)",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       description="Type a query and watch it go through gates. Each gate is one yes/no question\n"
                                   "compiled from a reasoning card written in plain language. Starts with the\n"
                                   "manager's Section 41 cards; :card adds more, :approve approves them.",
                       epilog="examples:\n"
                              "  tcxp flow                                         interactive\n"
                              "  tcxp flow 'What should I deduct for Section 41 US-based QREs we paid yesterday?'\n"
                              "  tcxp flow --card 'If the query contains ASAP, alert that it is urgent' --approve 'Need this ASAP for tax year 2024'\n"
                              "  tcxp flow --empty --card 'Test: known(tax_year) and country = \"US\"' 'US wages please'")
    s.add_argument("query", nargs="?", help="run one query and exit (omit for interactive)")
    s.add_argument("--card", action="append", metavar="SENTENCE", help="add a reasoning card first (repeatable)")
    s.add_argument("--approve", action="store_true", help="approve the cards given with --card")
    s.add_argument("--empty", action="store_true", help="start with no cards")
    s.add_argument("--proposed", action="store_true", help="leave the starting cards proposed (shown, not acted on)")
    s.set_defaults(fn=_cmd_flow)

    s = sub.add_parser("expr", help="a rule as an expression tree: fold it upward, ask about Dark leaves",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog="examples:\n"
                              "  tcxp expr '3 + 2y = 9'                 y is Dark: the fold stops and says so\n"
                              "  tcxp expr '3 + 2y = 9' --set y=3       folds to true, step by step\n"
                              "  tcxp expr '3 + 2y = 9' --solve         y = 3, with no model\n"
                              "  tcxp expr '!tcxp:/expr?n1=add&n1.l=2&n1.r=x&root=n1' --set x=5")
    s.add_argument("expression", help="infix math (3 + 2y = 9) or an !tcxp:/expr address")
    s.add_argument("--set", action="append", metavar="NAME=VALUE", help="give a variable a value (repeatable)")
    s.add_argument("--solve", action="store_true", help="solve a linear equation for its one Dark variable")
    s.add_argument("--output", "-o", choices=["table", "json"], default="table")
    s.set_defaults(fn=_cmd_expr)

    s = sub.add_parser("docs", help="open the animated docs in your browser (served locally)")
    s.add_argument("--port", type=int, default=0, help="port to serve on (default: any free port)")
    s.add_argument("--no-open", action="store_true", help="don't open a browser; just serve")
    s.add_argument("--path", action="store_true", help="print the docs file path and exit")
    s.add_argument("--flow", action="store_true", help="open the interactive decision-flow page instead")
    s.set_defaults(fn=_cmd_docs)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except BrokenPipeError:  # output piped to `head` and closed early
        try:
            sys.stdout = open(os.devnull, "w")   # nothing left to flush at exit
        except OSError:
            pass
        return 0
    except (OSError, ValueError, KeyError, LookupError) as exc:   # user mistakes: a clear message, no traceback
        msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(f"tcxp: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
