import json
from pathlib import Path

import pytest

from tcxp import ContextObject
from tcxp.__main__ import main
from tcxp.flow import (APPROVED, CardNotUnderstood, Gate, TQLError, compile_card, describe, draw_flow, evaluate,
                       flow_demo, format_tql, parse_tql)

V = json.loads((Path(__file__).parent.parent / "conformance" / "tql_vectors.json").read_text())


@pytest.mark.parametrize("v", V["valid"], ids=lambda v: f'{v["test"]}|{v["state"]}')
def test_tql_vectors(v):
    assert format_tql(parse_tql(v["test"])) == v["canonical"]
    r, dark = evaluate(v["test"], V["states"][v["state"]])
    assert r == v["result"] and list(dark) == v["dark"]


@pytest.mark.parametrize("t", V["invalid"])
def test_tql_rejects(t):
    with pytest.raises(TQLError):
        parse_tql(t)


@pytest.mark.parametrize("c", V["cards"], ids=lambda c: c["card"][:40])
def test_card_vectors(c):
    assert str(compile_card(c["card"]).gate.address()) == c["address"]


@pytest.mark.parametrize("c", V["attach"], ids=lambda c: c["card"][:40])
def test_attach_vectors(c):
    r = compile_card(c["card"], [Gate.from_address(V["base_gate"])])
    assert str(r.gate.address()) == c["address"] and r.new == c["new"]


def test_cards_that_are_not_understood_and_proposer():
    with pytest.raises(CardNotUnderstood):
        compile_card("Be careful with dates")
    with pytest.raises(CardNotUnderstood):
        compile_card("If false, do something nice")           # no gate to attach to, and no action
    g = compile_card("Be careful with dates", proposer=lambda t: {"test": "known(date_format)",
                                                                  "if_false": ["@core.ask?key=date_format"]}).gate
    assert g.test == "known(date_format)" and g.status == "proposed" and g.by == "proposer"
    with pytest.raises(TQLError):                              # a model's proposal is validated like typing
        compile_card("x", proposer=lambda t: {"test": "rm -rf /"})


def test_gate_round_trip_and_validation():
    g = Gate("tax-year-required", "known( tax_year )", if_false=("@core.ask?key=tax_year",), card="c", by="m")
    assert g.test == "known(tax_year)" and Gate.from_address(g.address()) == g
    for bad in [dict(id="Bad", test="known(x)"), dict(id="x", test="nope"), dict(id="x", test="known(x)", if_true=("rm",))]:
        with pytest.raises(ValueError):
            Gate(**bad)


def _flow():
    f = flow_demo()
    ids = [f.add_card(t, by="manager").id for t in ("For Section 41 tax preparation, require the tax year.",
                                                    "If false, alert that it's halted and you cannot proceed.",
                                                    "If the query contains yesterday, highlight it.")]
    return f, ids


def test_proposed_gates_are_shown_not_acted_on():
    f, _ = _flow()
    r = f.run("What should I deduct for Section 41 US-based QREs we paid yesterday?")
    gate_ids = {g.id for g in f.gates}
    assert not r.stopped_at and not r.alerts and not r.asks and [s.fired for s in r.steps] == [False, False]
    assert not [h for h in r.highlights if h["sensor"] in gate_ids]       # sensors may highlight; gates didn't
    assert [s.branch for s in r.steps] == ["false", "true"]


def test_approved_flow_asks_alerts_halts_then_passes():
    f, ids = _flow()
    for gid in dict.fromkeys(ids):
        f.approve(gid, "manager")
    assert all(g.status == APPROVED and g.approved_by == "manager" for g in f.gates)
    r = f.run("What should I deduct for Section 41 US-based QREs we paid yesterday?")
    assert r.stopped_at == "tax-year-required" and r.asks == ["tax_year"] and r.halted
    assert r.alerts == ["ALERT: it's halted and you cannot proceed"]
    q = "What should I deduct for Section 41 US-based QREs we paid yesterday for tax year 2024?"
    r = f.run(q)
    at = q.index("yesterday")
    assert r.passed and [(h["start"], h["end"]) for h in r.highlights if h["sensor"] == "mentions-yesterday"] == [(at, at + 9)]
    out = draw_flow(f, r, color=False)
    assert "SUM(wages) = 99000" in out and "◀ taken" in out


def test_flow_persists_in_the_context_object_and_trace():
    f, ids = _flow()
    f.approve(ids[0], "manager")
    back = ContextObject.load(f.ctx.to_dict())
    gates = [g for g in back.reason if isinstance(g, Gate)]
    assert [g.id for g in gates] == [g.id for g in f.gates] and gates[0].approved
    assert any(r.op == "trigger" and r.key == "gate" and r.cause == "person:manager" for r in f.ctx.trace.rows)
    assert back.decide().missing == ("tax_year",)              # the governor checks rules and schema, not gates


def test_unknown_follows_false_and_asks_for_the_dark_key():
    f = flow_demo()
    g = f.add_card('Test: country = "US"', by="m")
    f.approve(g.id, "m")
    r = f.run("hello")
    assert r.steps[0].result is None and r.steps[0].dark == ("country",) and r.asks == ["country"] and r.stopped_at


def test_approve_requires_a_person_and_a_real_gate():
    f, ids = _flow()
    with pytest.raises(ValueError):
        f.ctx.call("@core.approve?gate=tax-year-required")
    with pytest.raises(LookupError):
        f.approve("no-such-gate", "manager")


def test_describe():
    assert describe("@core.ask?key=tax_year") == "ask for tax_year"
    assert describe("@core.highlight?word=last%20quarter") == 'highlight "last quarter"'


def test_cli_flow(capsys, tmp_path):
    s = str(tmp_path / "f.json")
    assert main(["flow", "What should I deduct for Section 41 US-based QREs we paid yesterday?", "--session", s]) == 0
    out = capsys.readouterr().out
    assert "stops here" in out and "ask for: tax_year" in out
    assert main(["flow", "--card", "If the query contains ASAP, alert that it is urgent", "--approve",
                 "Need this ASAP for tax year 2024 US-based QREs", "--session", s]) == 0
    assert "ALERT: it is urgent" in capsys.readouterr().out
    assert main(["roll", "--steps", "1", "--speed", "0", "--session", s]) == 0
