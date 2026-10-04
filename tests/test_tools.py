import math

import pytest

from tcxp.bench import CASES, OPTIONS, detect_tax_year, run_bench
from tcxp.demo import run as demo_run
from tcxp.ladder import NOT_STATED, CodeChecker, Ladder, Question, SimulatedChecker
from tcxp.learn import SoftmaxPerceptron, reliability_curve
from tcxp.reliability import budget, cases_needed, end_to_end_error, per_step_error, recommend, weeks_to
from tcxp.session import Session
from tcxp.sim import Organization, SimConfig
from tcxp.sql import Database, QueryCard, SQLError, tax_year_bounds

CSV = "name,country,day,amount\na,US,2024-01-05,10\nb,CA,2024-02-01,20\nc,US,2025-01-01,30\nd,US,2024-12-31,5\n"


# ---------- reliability (same expected values as the published calculator's suite) ----------
@pytest.mark.parametrize("e,conf,f,n", [(0.02, .95, 0, 149), (0.0005, .95, 0, 5990), (0.001, .95, 0, 2995),
                                        (0.01, .95, 0, 299), (0.1, .95, 0, 29), (0.2, .95, 0, 14),
                                        (0.01, .95, 1, 473), (0.01, .95, 2, 628), (0.01, .99, 0, 459), (0.01, .90, 0, 230)])
def test_cases_needed(e, conf, f, n):
    assert cases_needed(e, conf, f) == n


def test_reliability_pieces():
    assert end_to_end_error(100, 200, 95) == 0.05
    e = per_step_error(0.01, 10)
    assert abs(e - 0.0010045) < 1e-6 and cases_needed(e) == 2981
    assert weeks_to(10, 0, 50) == math.inf and recommend(math.inf) == "No volume to learn from"
    assert [recommend(w) for w in (3, 20, 100)] == ["Automate within a month", "Gate it and collect",
                                                     "Keep a person on it, or split it"]
    b = budget(6, 50000, 100, 40, 90)
    assert b.cases == 8979 and abs(b.weeks - 249.4) < 0.1


# ---------- sql ----------
def test_sql_dialect():
    db = Database()
    db.load_csv("t", CSV)
    assert db.registry.get("!tcxp:/sql/table/t").name == "t"
    assert db.query("SELECT SUM(amount) FROM t WHERE country = 'US'").scalar() == "45"
    r = db.query("SELECT name FROM t WHERE day BETWEEN :s AND :e AND amount >= 10", {"s": "2024-01-01", "e": "2024-12-31"})
    assert r.rows == [["a"], ["b"]]
    assert db.query("SELECT COUNT(*), MIN(amount), MAX(amount) FROM t").rows == [["4", "5", "30"]]
    for bad in ["DELETE FROM t", "SELECT * FROM t ORDER BY name", "SELECT * FROM nope", "SELECT zz FROM t",
                "SELECT * FROM t WHERE day = :missing"]:
        with pytest.raises(SQLError):
            db.query(bad)


def test_query_card_slots():
    card = QueryCard("c", "US", "SELECT SUM(amount) FROM t WHERE country = :country AND day BETWEEN :start_date AND :end_date",
                     derive=tax_year_bounds)
    assert card.slots == ["country", "start_date", "end_date"]
    assert card.missing({"country": "US"}) == ["start_date", "end_date"]
    state = {"country": "US", "tax_year": "2024"}
    assert card.missing(state) == []
    db = Database()
    db.load_csv("t", CSV)
    assert card.run(db, state).scalar() == "15"
    assert "end_date=2024-12-31" in str(card.address(state))
    with pytest.raises(SQLError):
        card.run(db, {"country": "US"})


# ---------- simulator ----------
def test_sim_is_reproducible_from_its_address():
    c = SimConfig(employees=10, agents=2, tasks=5, cycles=2, seed=7)
    assert SimConfig.from_address(c.to_address()) == c
    a, b = Organization(c).run(), Organization(c.to_address()).run()
    assert a.hops == b.hops and a.metrics == b.metrics


def test_sim_gate_is_the_only_difference():
    base = dict(employees=20, agents=5, tasks=10, cycles=3, ambiguity=0.5, seed=3)
    off, on = Organization(SimConfig(**base)).run(), Organization(SimConfig(gate=True, **base)).run()
    assert [h.receiver for h in off.hops] == [h.receiver for h in on.hops]    # same paths
    assert on.metrics["silent_errors"] == 0 and on.metrics["dark_hops"] == 0
    assert off.metrics["silent_errors"] > 0 and on.metrics["asks"] > 0
    assert on.metrics["total_cost"] < off.metrics["total_cost"]


def test_sim_interpretation_becomes_intent():
    res = Organization(SimConfig(employees=5, agents=0, tasks=3, cycles=1, ambiguity=1.0, seed=1)).run()
    for prev, nxt in zip(res.hops, res.hops[1:]):
        if (prev.task, prev.decision) == (nxt.task, nxt.decision):
            assert nxt.intent == prev.read
    assert res.to_trace().verify() == []


def test_sim_rejects_bad_config():
    with pytest.raises(ValueError):
        SimConfig(steps_min=5, steps_max=2)


# ---------- ladder + bench ----------
def test_ladder_order_and_ask():
    q = Question("q", "for tax year 2024", kind="choice", options=OPTIONS, truth="2024")
    code = CodeChecker("code", lambda q: (detect_tax_year(q.text), 1.0) if detect_tax_year(q.text) else None)
    never = SimulatedChecker("llm", accuracy=0.0, calibrated=True, seed=1)
    assert Ladder([code, never]).run(q).decided_by == "code"
    q2 = Question("q2", "how much can I deduct", kind="choice", options=OPTIONS, truth=NOT_STATED)
    assert Ladder([code]).run(q2).verdict == "ASK"


def test_simulated_checker_is_deterministic():
    q = Question("q", "x", kind="choice", options=OPTIONS, truth="2024")
    s = SimulatedChecker("llm", seed=4)
    assert s.check(q) == s.check(q)


def test_bench_simulated():
    rows = {r.arm: r for r in run_bench("simulated")}
    assert rows["code"].correct == 9 and rows["code"].silent_errors == 0 and rows["code"].extra_asks == 1
    for r in rows.values():
        assert r.correct + r.silent_errors + r.extra_asks + r.errors == len(CASES)
    assert rows["ladder"].silent_errors <= rows["llm_alone"].silent_errors


def test_bench_real_without_keys_reports_errors(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rows = {r.arm: r for r in run_bench("real", arms=("jev_alone",))}
    assert rows["jev_alone"].errors == len(CASES)


# ---------- learn ----------
def test_perceptron_learns_and_curve_runs():
    train = [("tax year 2024 credit", "stated"), ("FY25 numbers", "stated"), ("for the 2023 return", "stated"),
             ("what can I deduct", "not_stated"), ("research credit estimate", "not_stated"), ("project began in 2024", "not_stated")]
    m = SoftmaxPerceptron(["stated", "not_stated"]).fit(*zip(*train))
    assert m.predict("tax year 2025 wages")[0] == "stated"
    curve = reliability_curve(train, [("tax year 2023", "stated"), ("deduct for research", "not_stated")], ["stated", "not_stated"])
    assert [k for k, _ in curve] == [1, 2, 3]


# ---------- demo + session ----------
def test_demo_script_and_playback(tmp_path):
    path = tmp_path / "s.json"
    out = []
    ctx = demo_run(["What should I deduct for Section 41 US-based QREs?", ":quit"], answer=lambda p: "2024",
                   session_path=path, color=False, out=out.append)
    text = "\n".join(out)
    assert "ASK" in text and "SUM(wages) = 99000" in text
    assert ctx.get("tax_year") == "2024" and any(r.learnable for r in ctx.trace)
    s = Session.load(path)
    assert s.context.trace.verify(s.context.registry) == []
    frames = []
    assert s.play(steps=2, out=frames.append, color=False) == 2 and s.playhead == 2
    assert s.rewind() == 0 and s.seek(999) == s.length
    assert Session.reset(path) and not path.exists()
