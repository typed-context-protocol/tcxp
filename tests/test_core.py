import pytest

from tcxp import (ACT, ASK, DARK, HALT, LIT, MATCH, NO_MATCH, Address, ContextObject, Equivalences, EventBus,
                  Field, Governor, IntegrityError, Observatron, Registry, Rule, Schema, Sensor, Spike, dark_count,
                  spikes_in)
from tcxp.convert import FORMATS, convert, from_csv, from_dict, from_json, to_csv, to_dict, to_json
from tcxp.governor import RuleCompileError
from tcxp.registry import HandlerNotFound, parse_handler


# ---------- schema ----------
def test_schema_types_and_answer_space():
    s = Schema.of("t", Field("tax_year", "int", ("2023", "2024"), essential=True), Field("on", "bool"),
                  Field("d", "date"), Field("ptr", "address"))
    good = Address.build("x", {"tax_year": 2024, "on": True, "d": "2024-01-31", "ptr": "!tcxp:/a"})
    assert s.problems(good) == []
    typed = s.coerce(good)
    assert typed["tax_year"] == 2024 and typed["on"] is True and str(typed["ptr"]) == "!tcxp:/a"
    bad = good.with_(tax_year=2030, d="01/31/2024", on="yes")
    assert {p.key for p in s.problems(bad)} == {"tax_year", "d", "on"}
    assert s.dark(good.with_(tax_year="")) == ("tax_year",)
    assert s.dark(bad) == ("tax_year",)           # invalid counts as not known
    round_trip = Schema.from_address(s.to_address())
    assert round_trip.fields["tax_year"].values == ("2023", "2024") and round_trip.fields["tax_year"].essential


# ---------- facets ----------
def test_spike_lit_dark_and_match():
    a = Spike("date", "05/04/2026", structure=("!tcxp:/schema/date/mm-dd-yyyy",))
    b = Spike("date", "05/04/2026", structure=("tcxp:/schema/date/mm-dd-yyyy",))     # same pointer, other spelling
    c = Spike("date", "05/04/2026", structure=("!tcxp:/schema/date/dd-mm-yyyy",))
    assert a.dark == ("meaning", "environment") and a.lit == ("structure",)
    assert a.compare(b, "structure") == MATCH
    assert a.compare(c, "structure") == NO_MATCH
    assert a.compare(c, "meaning") == DARK
    eq = Equivalences([("!tcxp:/schema/date/mm-dd-yyyy", "!tcxp:/schema/date/us")])
    d = Spike("date", "x", structure=("!tcxp:/schema/date/us",))
    assert a.compare(d, "structure") == NO_MATCH and a.compare(d, "structure", eq) == MATCH


def test_spikes_round_trip_through_address():
    s = Spike("tax_year", "2024", meaning=("!tcxp:/tax/us/tax-year",))
    addr = Address.build("r", s.to_params())
    assert spikes_in(addr) == [Spike("tax_year", "2024", meaning=("!tcxp:/tax/us/tax-year",))]
    assert dark_count(addr) == 2


# ---------- bus ----------
def test_event_bus():
    bus, seen, every = EventBus(keep_history=True), [], []
    off = bus.on("spike", seen.append)
    bus.on("*", every.append)
    bus.emit("spike", 1)
    off()
    bus.emit("spike", 2)
    assert seen == [1] and every == [{"topic": "spike", "payload": 1}, {"topic": "spike", "payload": 2}]
    assert len(bus.history) == 2


# ---------- registry ----------
def test_registry_data_state_and_handlers():
    reg = Registry()
    reg.put("!tcxp:/data/x", {"v": 1})
    assert reg.get("!tcxp:/data/x") == {"v": 1}
    p = reg.put_state({"b": 1, "a": [1, 2]})
    assert str(p).startswith("!tcxp:/state/sha256-") and reg.get_state(p) == {"a": [1, 2], "b": 1}
    assert reg.put_state({"a": [1, 2], "b": 1}) == p                       # same content, same pointer
    reg._states[str(p).rsplit("-", 1)[1]] = '{"tampered":true}'
    with pytest.raises(IntegrityError):
        reg.get_state(p)

    @reg.on("!tcxp:/reason/*")
    def route(params, ctx):
        return ("route", params)

    @reg.handler("my.add")
    def add(params, ctx):
        return int(params["a"]) + int(params["b"])

    assert reg.trigger("!tcxp:/reason/tax-year?x=1") == ("route", {"x": "1"})
    assert reg.trigger("@my.add?a=2&b=3") == 5
    with pytest.raises(HandlerNotFound):
        reg.trigger("@nope")
    assert parse_handler("@core.update?a=1&b=x&b=y") == ("core.update", {"a": "1", "b": ["x", "y"]})


# ---------- governor ----------
def test_rule_compile_and_address_round_trip():
    r = Rule.compile("Don't give the answer until the tax year is confirmed", by="manager", slots={"tax year": "tax_year"})
    assert (r.when, r.require, r.verdict) == ("answer", ("tax_year",), ASK)
    assert Rule.from_address(r.address()) == r
    n = Rule.compile("Never pay the vendor until the client's fiscal year end is confirmed")
    assert n.verdict == HALT and n.when == "commit" and n.require == ("client_fiscal_year_end",)
    with pytest.raises(RuleCompileError):
        Rule.compile("Please be careful")


def test_governor_verdicts_and_halt_absorbs():
    g = Governor([Rule("r1", "answer", ("tax_year",)), Rule("r2", "answer", ("client",), HALT)])
    state = Address.build("r", {"tax_year": "", "client": ""})
    v = g.evaluate(state, "answer")
    assert v.kind == HALT and set(v.missing) == {"tax_year", "client"}
    assert g.evaluate(state.with_(client="acme"), "answer").kind == ASK
    assert g.evaluate(state.with_(client="acme", tax_year=2024), "answer").kind == ACT
    assert g.evaluate(state, "other").kind == ACT
    assert "kind=HALT" in str(v.address())


# ---------- context object + observatron ----------
def _ctx():
    return ContextObject("reason/t", observe=[
        Sensor("task", "deduct|section 41", ("@core.update?task=s41", "@core.highlight"), kind="keyword", key="task"),
        Sensor("year", r"\btax year (20\d\d)\b", ("@core.update?tax_year={1}",), key="tax_year")],
        reason=[Rule("r1", "answer", ("tax_year",))], params={"tax_year": ""}, clock=lambda: "T")


def test_observatron_flow():
    ctx = _ctx()
    bus = EventBus(keep_history=True)
    obs = Observatron(ctx, bus=bus)
    o = obs.feed("What should I deduct for section 41?")
    assert o.verdict.kind == ASK and o.asks == ["tax_year"]
    assert [s.data for s in o.spikes] == ["deduct", "section 41"] and len(o.highlights) == 2
    assert ctx.get("task") == "s41"
    o = obs.feed("deduct for tax year 2024")
    assert o.verdict.kind == ACT and ctx.get("tax_year") == "2024"
    topics = [t for t, _ in bus.history]
    assert topics[0] == "mount" and "spike" in topics and topics[-1] == "decision"
    assert ctx.trace.verify(ctx.registry) == []


def test_debounce():
    obs = Observatron(_ctx(), debounce_ms=300)
    obs.keystroke("ded", 0)
    assert obs.tick(100) is None
    obs.keystroke("deduct", 150)
    assert obs.tick(400) is None and obs.tick(450).text == "deduct"


def test_confirm_is_learnable_and_save_load():
    ctx = _ctx()
    Observatron(ctx).feed("deduct")
    row = ctx.confirm("tax_year", 2024, by="you")
    assert row.learnable and row.features == "deduct" and row.cause == "person:you"
    p = ctx.save()
    back = ContextObject.load(p, ctx.registry)
    assert back.address == ctx.address and len(back.trace) == len(ctx.trace)


def test_long_state_becomes_pointer_and_verifies():
    ctx = ContextObject("r", inline_limit=60)
    ctx.set("text", "x" * 200, "test")
    last = ctx.trace.rows[-1]
    assert last.address.startswith("!tcxp:/state/sha256-")
    assert ctx.resolve(last.address).get("text") == "x" * 200
    assert ctx.trace.verify(ctx.registry) == []
    assert ctx.trace.verify(Registry()) != []            # pointer can't resolve elsewhere: reported, not hidden


def test_trace_tamper_detected():
    ctx = _ctx()
    ctx.set("a", 1, "t")
    ctx.set("a", 2, "t")
    from dataclasses import replace
    ctx.trace.rows[1] = replace(ctx.trace.rows[1], value="999")
    assert any("changed" in p for p in ctx.trace.verify())


def test_trace_summary_and_exports():
    ctx = _ctx()
    ctx.set("a", 1, "t")
    ctx.set("a", 2, "t")
    s = ctx.trace.summary()
    assert s["changed"]["a"] == {"from": "1", "to": "2", "edits": 2}
    assert ctx.trace.to_csv().splitlines()[0].startswith("index,time,op,key,value")


# ---------- convert ----------
def test_conversions_round_trip():
    a = Address.parse("!tcxp:/r?b=2&b=1&q=what%20now%3F&e=")
    assert from_json(to_json(a)) == a
    assert from_dict(to_dict(a)) == a
    assert from_csv(to_csv(a), "r") == a
    for fmt in FORMATS:
        assert convert(a, fmt)
    assert "std::map" in convert(a, "cpp") and "Map.ofEntries" in convert(a, "java")
    assert "INSERT INTO tcxp_state" in convert(a, "sql")
    with pytest.raises(ValueError):
        convert(a, "xml")
