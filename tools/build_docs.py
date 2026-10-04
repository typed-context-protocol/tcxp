"""Build the animated docs (docs/index.html) from the library's real output.

Every scene is produced by running the actual command or API call and capturing its
colored output (and, for the context roll, its frames). Re-run this after changing the
library and the docs can't drift from what the code does:

    python tools/build_docs.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tcxp import __version__  # noqa: E402
from tcxp.demo import run as demo_run  # noqa: E402
from tcxp.roll import Roll, steps_from_session  # noqa: E402
from tcxp.session import Session  # noqa: E402
from tcxp.sim import Organization, SimConfig  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="tcxp-docs-"))
SESSION = TMP / "demo.json"
ENV = {**os.environ, "TCXP_COLOR": "1", "PYTHONPATH": str(ROOT / "src")}


def sh(cmd: list[str], shown: str | None = None) -> dict:
    res = subprocess.run([sys.executable, "-m", "tcxp", *cmd], capture_output=True, text=True, env=ENV, cwd=TMP)
    if res.returncode not in (0,):
        raise SystemExit(f"Command failed: tcxp {' '.join(cmd)}\n{res.stderr}")
    return {"cmd": shown or "tcxp " + " ".join(cmd), "out": res.stdout.rstrip("\n")}


def demo_transcript() -> dict:
    out: list[str] = []
    demo_run(["What should I deduct for Section 41 US-based QREs?", ":quit"], answer=lambda p: "2024",
             session_path=SESSION, color=True, out=out.append)
    text = "\n".join(out).replace(str(SESSION), "./tcxp-session.json")
    return {"cmd": "tcxp demo", "out": text}


def roll_frames(session_path: Path) -> dict:
    return Roll(steps_from_session(Session.load(session_path)), past=3, future=2).to_dict()


def build() -> list[dict]:
    scenes = []
    scenes.append({"id": "version", "title": "The library knows its own address",
                   "caption": "Even the version is a virtual tcxp address you can parse.",
                   "terminal": [sh(["version"]), sh(["version", "-o", "json"])]})
    scenes.append({"id": "convert", "title": "One state, every format",
                   "caption": "The same keys and values as JSON, C++, Java or SQL.",
                   "terminal": [sh(["convert", "!tcxp:/reason?tax_year=2024&task=section_41_qre", "-o", "json"],
                                   "tcxp convert '!tcxp:/reason?tax_year=2024&task=section_41_qre' -o json"),
                                sh(["convert", "!tcxp:/reason?tax_year=2024&task=section_41_qre", "-o", "cpp"],
                                   "tcxp convert '!tcxp:/reason?tax_year=2024&task=section_41_qre' -o cpp")]})
    scenes.append({"id": "observatron", "title": "The Observatron catches the missing tax year",
                   "caption": "Sensors fire as you type. The manager’s rule asks before answering.",
                   "terminal": [demo_transcript()]})
    scenes.append({"id": "roll", "title": "The context roll: a piano roll for state",
                   "caption": "Every step is an address. Values light up when they change.",
                   "terminal": [{"cmd": "tcxp sequencer play", "out": ""}], "roll": roll_frames(SESSION)})
    scenes.append({"id": "sim", "title": "Simulate an organization’s hand-offs",
                   "caption": "Same people, paths and truth. Only the gate differs.",
                   "terminal": [sh(["sim", "--compare"])]})
    wave = TMP / "wave.json"
    cfg = SimConfig(employees=12, agents=3, tasks=1, decisions_per_task=1, cycles=1, steps_min=6, steps_max=6,
                    ambiguity=1.0, seed=11)
    Session.from_trace(Organization(cfg).run().to_trace(), wave).save()
    scenes.append({"id": "wave", "title": "Watch a misreading propagate",
                   "caption": "With the format Dark, each guess becomes the next person’s intent.",
                   "terminal": [{"cmd": "tcxp sim --ambiguity 1 --tasks 1 --steps-min 6 --steps-max 6 --record && tcxp roll",
                                 "out": ""}], "roll": roll_frames(wave)})
    scenes.append({"id": "stories", "title": "Simulated stories: describe an organization, run it",
                   "caption": "Three 2,000-person teams, each misreading at its own rate.",
                   "terminal": [sh(["sim", "--story", "launch", "--compare"])]})
    scenes.append({"id": "flow", "title": "Reasoning cards become gates",
                   "caption": "A manager writes a sentence. It becomes a yes/no question.",
                   "terminal": [sh(["flow", "What should I deduct for Section 41 US-based QREs we paid yesterday?",
                                    "--session", str(TMP / "flow.json")],
                                   "tcxp flow 'What should I deduct for Section 41 US-based QREs we paid yesterday?'")]})
    scenes.append({"id": "expr", "title": "A rule as an expression tree",
                   "caption": "Fold upward. A missing leaf stops the fold and asks.",
                   "terminal": [sh(["expr", "3 + 2y = 9", "--solve"], "tcxp expr '3 + 2y = 9' --solve"),
                                sh(["expr", "3 + 2y = 9", "--set", "y=3"], "tcxp expr '3 + 2y = 9' --set y=3")]})
    scenes.append({"id": "bench", "title": "Code, Jev and an LLM, with and without context",
                   "caption": "Context turns silent errors into questions. Simulated rungs, declared assumptions.",
                   "terminal": [sh(["bench"])]})
    csv = TMP / "payroll.csv"
    csv.write_text((ROOT / "src" / "tcxp" / "data" / "payroll.csv").read_text())
    scenes.append({"id": "sql", "title": "A tiny SQL engine over your CSV",
                   "caption": "Versioned dialect, every value a string, slots filled from context.",
                   "terminal": [sh(["sql", "SELECT COUNT(*), SUM(wages) FROM payroll WHERE country = 'US' AND pay_date BETWEEN :start_date AND :end_date",
                                    "--csv", "payroll=payroll.csv", "--param", "start_date=2024-01-01", "--param", "end_date=2024-12-31"],
                                   "tcxp sql \"SELECT COUNT(*), SUM(wages) FROM payroll WHERE country = 'US' AND pay_date BETWEEN :start_date AND :end_date\" "
                                   "--csv payroll=payroll.csv --param start_date=2024-01-01 --param end_date=2024-12-31")]})
    scenes.append({"id": "budget", "title": "How many examples before automating?",
                   "caption": "Chain length and the cost of one error set the number.",
                   "terminal": [sh(["budget", "--steps", "6", "--cost", "50000", "--tolerated", "100", "--volume", "40", "--answered", "90"])]})
    scenes.append({"id": "learn", "title": "A perceptron learns from confirmed answers",
                   "caption": "Trains in milliseconds and is tested on requests it never saw.",
                   "terminal": [sh(["learn", "--session", str(SESSION)], "tcxp learn")]})
    scenes.append({"id": "fleet", "title": "10,000 Observatrons, with and without context",
                   "caption": "Same requests for every arm. Guard dogs learn; phrasing drifts at epoch 5.",
                   "terminal": [sh(["fleet", "--observatrons", "10000"])]})
    scenes.append({"id": "play", "title": "Rewind, seek and replay any step",
                   "caption": "Transport controls for the trace, in any output format.",
                   "terminal": [sh(["rewind", "--session", str(SESSION)], "tcxp rewind"),
                                sh(["seek", "12", "--session", str(SESSION)], "tcxp seek 12"),
                                sh(["play", "--steps", "1", "-o", "java", "--session", str(SESSION)], "tcxp play --steps 1 -o java")]})
    for s in scenes:
        for t in s["terminal"]:
            t["out"] = t["out"].replace(str(SESSION), "./tcxp-session.json").replace(str(TMP), ".")
    return scenes


def main() -> None:
    scenes = build()
    template = (ROOT / "tools" / "docs_template.html").read_text(encoding="utf-8")
    data = json.dumps({"version": __version__, "scenes": scenes}, ensure_ascii=False).replace("</", "<\\/")
    body = template.replace("__SCENES__", data).replace("__VERSION__", __version__)
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"></head><body>\n"
        + body + "\n</body></html>\n", encoding="utf-8")
    (out / "artifact.html").write_text(body, encoding="utf-8")
    web = ROOT / "src" / "tcxp" / "web"            # shipped in the wheel for `tcxp docs`
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text((out / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote docs/index.html with {len(scenes)} scenes")


if __name__ == "__main__":
    main()
