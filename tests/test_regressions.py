"""One regression test per finding from the independent review."""
import json

import pytest

from tcxp.__main__ import main
from tcxp.address import Address, AddressError
from tcxp.context import ContextObject
from tcxp.facets import Spike
from tcxp.fleet import Fleet, FleetConfig
from tcxp.registry import Registry
from tcxp.reliability import binom_cdf
from tcxp.schema import Field, Schema
from tcxp.session import Session
from tcxp.sql import Database, QueryCard, SQLError

CSV = "d,amt,name\n2024-01-05,10,a\n2024-12-30,NaN,b\n2023-06-01,1_000,c\n"


# ---------- address grammar ----------
def test_tcxp_colon_text_value_is_kept_as_text():
    a = Address.parse("!tcxp:/r?note=tcxp%3A")
    assert a.get("note") == "tcxp:" and Address.parse(str(a)) == a


@pytest.mark.parametrize("text", ["!tcxp:/r?a=café", "!tcxp:/r?a=1\n", "!tcxp:/r\n?a=1", "﻿!tcxp:/r?a=1"])
def test_raw_non_ascii_and_control_chars_are_rejected(text):
    with pytest.raises(AddressError):
        Address.parse(text)


def test_emoji_round_trips_percent_encoded():
    a = Address.build("r", {"e": "\U0001F600"})
    assert "%F0%9F%98%80" in str(a) and Address.parse(str(a)).get("e") == "\U0001F600"


# ---------- state guarantees ----------
def _ctx():
    c = ContextObject("reason/s41", params={"tax_year": ""})
    c.add_rule("Don't give the answer until the tax year is confirmed", slots={"tax year": "tax_year"})
    return c


def test_halt_is_absorbing_and_survives_save_load():
    c = _ctx()
    c.halted = "manager stop"
    assert c.decide().kind == "HALT"
    c.confirm("tax_year", "2024")
    assert c.decide().kind == "HALT"
    back = ContextObject.load(c.to_dict())
    assert back.halted == "manager stop" and back.decide().kind == "HALT"


def test_truncated_trace_is_rejected(tmp_path):
    c = _ctx()
    c.set("task", "s41", "test")
    p = Session(c, path=tmp_path / "s.json").save()
    data = json.loads(p.read_text())
    data["context"]["trace"] = data["context"]["trace"][:-1]
    data["context"]["address"] = data["context"]["trace"][-1]["address"]
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity"):
        Session.load(p)


def test_swapped_address_is_rejected(tmp_path):
    c = _ctx()
    p = Session(c, path=tmp_path / "s.json").save()
    data = json.loads(p.read_text())
    data["context"]["address"] = "!tcxp:/reason/s41?tax_year=2099"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="last snapshot"):
        Session.load(p)


def test_repeated_key_with_an_empty_value_is_dark():
    s = Schema.of("s", Field("tax_year", "int", essential=True, many=True))
    assert s.dark(Address.parse("!tcxp:/r?tax_year=2024&tax_year=")) == ("tax_year",)
    c = _ctx()
    c.address = Address.parse("!tcxp:/reason/s41?tax_year=2024&tax_year=")
    assert c.decide().kind == "ASK"


def test_spike_compare_rejects_anchor_facet():
    a, b = Spike("d", "x"), Spike("d", "y")
    with pytest.raises(ValueError):
        a.compare(b, "data")


def test_registry_has_needs_the_state_prefix():
    r = Registry()
    ptr = r.put_state({"a": 1})
    digest = str(ptr).rsplit("sha256-", 1)[1]
    assert r.has(ptr) and not r.has(f"!tcxp:/other/sha256-{digest}")


# ---------- SQL ----------
def _db():
    db = Database()
    db.load_csv("t", CSV)
    return db


def test_sql_nan_and_underscored_numbers_are_text():
    db = _db()
    assert db.query("SELECT SUM(amt) FROM t").scalar() == "10"
    assert db.query("SELECT name FROM t WHERE amt = 'NaN'").rows == [["b"]]


def test_sql_star_misuse_is_an_error():
    with pytest.raises(SQLError):
        _db().query("SELECT *, name FROM t")
    with pytest.raises(SQLError):
        _db().query("SELECT SUM(*) FROM t")


def test_sql_max_on_dates_compares_as_text():
    assert _db().query("SELECT MAX(d), MIN(d) FROM t").rows == [["2024-12-30", "2023-06-01"]]


def test_sql_csv_extra_fields_and_bad_table_name():
    with pytest.raises(SQLError, match="more values"):
        Database().load_csv("t", "a,b\n1,2,3\n")
    with pytest.raises(SQLError):
        Database().load_csv("bad name", "a\n1\n")


def test_sql_missing_csv_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        Database().load_csv_file("t", tmp_path / "nope.csv")


def test_query_card_ignores_list_values():
    card = QueryCard("c", "c", "SELECT name FROM t WHERE name = :name")
    assert card.missing({"name": ["a", "b"]}) == ["name"]


# ---------- schema and statistics ----------
@pytest.mark.parametrize("typ,text", [("int", "1_000"), ("int", " 7"), ("float", "nan"), ("float", "inf"), ("float", "1_0.5")])
def test_schema_rejects_loose_numbers(typ, text):
    with pytest.raises(ValueError):
        Field("x", typ).coerce(text)


def test_binom_cdf_edges():
    assert binom_cdf(10, 0.1, -1) == 0.0
    assert binom_cdf(10, 0.1, 10) == 1.0
    assert binom_cdf(10, 0.0, 0) == 1.0
    assert binom_cdf(10, 1.0, 3) == 0.0


# ---------- fleet ----------
def test_fleet_validates_config_and_honours_limit_zero():
    with pytest.raises(ValueError):
        FleetConfig(epochs=0)
    with pytest.raises(ValueError):
        FleetConfig(trap_rate=1.5)
    f = Fleet(FleetConfig(observatrons=10, epochs=1), limit=0)
    assert f.requests == []


# ---------- CLI: errors exit 2 with a message, never a traceback ----------
@pytest.mark.parametrize("argv", [
    ["seek"],
    ["sql", "SELECT * FROM payroll", "--param", "x"],
    ["sql", "SELECT * FROM t", "--csv", "tpath"],
    ["sql", "SELECT * FROM t", "--csv", "t=/no/such/file.csv"],
])
def test_cli_bad_input_exits_cleanly(argv, tmp_path, capsys):
    try:
        code = main(argv + ["--session", str(tmp_path / "s.json")])
    except SystemExit as exc:          # argparse usage errors
        code = exc.code
    err = capsys.readouterr().err
    assert code == 2 and "Traceback" not in err and err.strip()


def test_cli_sim_flags_can_be_turned_off(capsys):
    assert main(["sim", "--tasks", "1", "--cycles", "1", "--gate", "--no-share-resolutions"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert "gate=true" in first and "share_resolutions=false" in first
    assert main(["sim", "--tasks", "1", "--cycles", "1", "--no-gate"]) == 0
    assert "gate=false" in capsys.readouterr().out.splitlines()[0]


# ---------- packaging ----------
def test_cli_sql_defaults_to_sample_table(capsys):
    assert main(["sql", "SELECT SUM(wages) FROM payroll WHERE country = 'US' AND pay_date BETWEEN :s AND :e",
                 "--param", "s=2024-01-01", "--param", "e=2024-12-31"]) == 0
    assert "99000" in capsys.readouterr().out


def test_cli_docs_path_points_at_bundled_page(capsys):
    assert main(["docs", "--path"]) == 0
    from pathlib import Path
    page = Path(capsys.readouterr().out.strip())
    assert page.name == "index.html" and "<!doctype html>" in page.read_text(encoding="utf-8")[:200].lower()
