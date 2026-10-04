from fractions import Fraction

import pytest

from tcxp.__main__ import main
from tcxp.expr import draw, fold, from_address, parse, solve, to_address
from tcxp.sim import STORIES, Organization, SimConfig, parse_teams, story


# ---------- stories and teams ----------
def test_default_sim_is_unchanged_by_teams_support():
    m = Organization(SimConfig()).run().metrics
    g = Organization(SimConfig(gate=True)).run().metrics
    assert (m["silent_errors"], m["hops"], g["asks"], g["silent_errors"]) == (23, 770, 36, 0)


def test_every_story_runs_and_round_trips_through_its_address():
    for name in STORIES:
        cfg = story(name)
        assert SimConfig.from_address(cfg.to_address()) == cfg
        assert Organization(cfg).run().metrics["decisions"] > 0


def test_story_overrides_and_team_breakdown():
    cfg = story("launch", tasks=5, gate=True)
    assert cfg.tasks == 5 and cfg.gate and "employees" not in str(cfg.to_address())
    res = Organization(story("launch", tasks=5)).run()
    teams = {r["team"] for r in res.by_team()}
    assert teams <= {"marketing", "engineering", "product"} and sum(r["decisions"] for r in res.by_team()) == 45


def test_team_ambiguity_drives_errors():
    calm = Organization(SimConfig(teams="a:50:0,b:50:0", tasks=20)).run().metrics
    noisy = Organization(SimConfig(teams="a:50:1,b:50:1", tasks=20)).run().metrics
    assert calm["silent_errors"] == 0 and calm["dark_hops"] == 0 and noisy["silent_errors"] > 0


@pytest.mark.parametrize("spec", ["a:0:0.1", "a:5:1.5", "a:5", "a:5:0.1,a:5:0.2", "bad name:5:0.1", "a:1:0.1"])
def test_bad_teams_are_rejected(spec):
    with pytest.raises(ValueError):
        SimConfig(teams=spec)


def test_parse_teams():
    assert parse_teams("x:2:0.5, y:3:0") == [("x", 2, 0.5), ("y", 3, 0.0)]


def test_cli_story_list_and_unknown(capsys, tmp_path):
    assert main(["sim", "--story", "list"]) == 0
    assert "launch" in capsys.readouterr().out
    assert main(["sim", "--story", "nope", "--session", str(tmp_path / "s")]) == 2
    assert main(["sim", "--story", "startup", "--compare"]) == 0
    assert "By the team" in capsys.readouterr().out


# ---------- expression trees ----------
def test_expression_round_trip_and_fold():
    t = parse("3 + 2y = 9")
    a = to_address(t)
    assert str(a) == "!tcxp:/expr?n1=eq&n1.l=n2&n1.r=9&n2=add&n2.l=3&n2.r=n3&n3=mul&n3.l=2&n3.r=y&root=n1"
    assert from_address(a) == t and str(to_address(from_address(a))) == str(a)
    dark = fold(a)
    assert dark.value is None and dark.dark == ("y",) and not dark.complete
    ok = fold(a, {"y": "3"})
    assert ok.value is True and [s["result"] for s in ok.steps] == ["6", "9", "true"]
    assert fold(a, {"y": "4"}).value is False


@pytest.mark.parametrize("text,var,value", [("3 + 2y = 9", "y", 3), ("2(x+1) = 10", "x", 4), ("x/4 = 2.5", "x", 10),
                                            ("-3 + y = 0", "y", 3), ("1/3 = z", "z", Fraction(1, 3)),
                                            ("2*(3 - k) = k", "k", 2)])
def test_solve_linear(text, var, value):
    assert solve(parse(text)) == {var: Fraction(value)}


@pytest.mark.parametrize("text", ["x*x = 4", "a*b = 6", "3 = 3", "x - x = 1", "4/x = 2"])
def test_solve_refuses_what_it_cannot_do_exactly(text):
    with pytest.raises(ValueError):
        solve(parse(text))


def test_fold_reads_context_state_and_rejects_bad_input():
    t = parse("hours * rate")
    assert fold(t, {"hours": "40", "rate": "12.5"}).value == Fraction(500)
    assert fold(t, {"hours": "40", "rate": ""}).dark == ("rate",)     # empty value is Dark
    with pytest.raises(ValueError):
        fold(t, {"hours": "forty", "rate": "1"})
    with pytest.raises(ValueError):
        fold(parse("1/x"), {"x": "0"})
    for bad in ["3 + ", "n2 + 1", "3 $ 4", "(1 + 2"]:
        with pytest.raises(ValueError):
            parse(bad)
    with pytest.raises(ValueError):
        from_address("!tcxp:/expr?n1=add&n1.l=n1&n1.r=2&root=n1")   # a cycle
    assert "(Dark)" in draw(t)


def test_cli_expr(capsys):
    assert main(["expr", "3 + 2y = 9", "--solve"]) == 0
    out = capsys.readouterr().out
    assert "Dark: y" in out and "y = 3" in out
    assert main(["expr", "3 + 2y = 9", "--set", "y=3", "-o", "json"]) == 0
    assert '"value": "true"' in capsys.readouterr().out


# ---------- intent map ----------
def test_intent_gate_registry_and_persistence():
    from tcxp import ContextObject, Intent, IntentNotAllowed
    from tcxp.learn import examples_from_trace
    from tcxp.registry import HandlerNotFound

    ctx = ContextObject("reason/s41", params={"tax_year": ""})

    @ctx.registry.handler("sql.run")
    def run(params, c):
        return "ran " + params.get("card", "")

    with pytest.raises(IntentNotAllowed):                    # registered, but not meant
        ctx.call("@sql.run?card=us-wages")
    assert ctx.trace.rows[-1].op == "refuse"
    ctx.add_intent("us-wages", means={"task": "section_41_qre"}, allows=["sql.*"], by="manager",
                   text="What should I deduct for Section 41 US-based QREs?")
    assert ctx.get("task") == "section_41_qre"
    assert ctx.call("@sql.run?card=us-wages") == "ran us-wages"
    with pytest.raises(HandlerNotFound):                     # meant, but not registered
        ctx.call("@sql.drop")
    ctx.call("@core.log?message=hi")                         # core acts on the object itself: always allowed
    assert examples_from_trace(ctx.trace.rows, "intent") == (["What should I deduct for Section 41 US-based QREs?"], ["us-wages"])
    back = ContextObject.load(ctx.to_dict())
    assert back.intent == ctx.intent and back.allowed("sql.run") and not back.allowed("email.send")
    it = ctx.intent[0]
    assert Intent.from_address(it.address()) == it and str(it.address()).startswith("!tcxp:/intent/us-wages?allows=@sql.%2A")


@pytest.mark.parametrize("bad", [dict(id="Bad Id"), dict(id="x", allows=("rm -rf",)), dict(id="x", allows=("a..b",))])
def test_intent_rejects_bad_ids_and_handler_names(bad):
    from tcxp import Intent
    with pytest.raises(ValueError):
        Intent(**bad)
