import json
from pathlib import Path

import pytest

from tcxp.address import Address, AddressError, decode, encode

VECTORS = json.loads((Path(__file__).parent.parent / "conformance" / "vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("v", VECTORS["valid"], ids=lambda v: v["input"])
def test_valid_vectors(v):
    a = Address.parse(v["input"])
    assert str(a) == v["canonical"]
    assert a.to_uri() == v["uri"]
    assert (a.form, a.authority, a.path_text) == (v["form"], v["authority"], v["path"])
    assert [[k, list(vals)] for k, vals in a.params] == v["params"]
    assert str(Address.parse(str(a))) == v["canonical"]          # canonical form is a fixed point
    assert str(Address.parse(a.to_uri())) == str(a) or a.form != "virtual"


@pytest.mark.parametrize("v", VECTORS["invalid"], ids=lambda v: v["input"])
def test_invalid_vectors(v):
    with pytest.raises(AddressError):
        Address.parse(v["input"])


def test_same_state_same_string():
    a = Address.parse("!tcxp:/r?b=2&a=1")
    b = Address.build("r", {"a": 1, "b": 2})
    assert str(a) == str(b) and a == b and hash(a) == hash(b) and a.sha256 == b.sha256


def test_editing_returns_new_value():
    a = Address.parse("!tcxp:/r?tax_year=")
    b = a.with_(tax_year=2024)
    assert a.get("tax_year") == "" and b.get("tax_year") == "2024"
    assert b.without("tax_year").keys() == ()
    assert a.with_(x=None) == a


def test_lists_and_dark():
    a = Address.build("r", {"m": ["!tcxp:/a", "!tcxp:/b"], "e": []})
    assert a.get_all("m") == ("!tcxp:/a", "!tcxp:/b")
    assert a.get("e") == ""
    assert str(a) == "!tcxp:/r?e=&m=!tcxp:/a&m=!tcxp:/b"


def test_typed_values_are_written_one_way():
    a = Address.build("r", {"t": True, "f": 2.5, "i": 3.0, "n": 7})
    assert a.to_dict() == {"f": "2.5", "i": "3", "n": "7", "t": "true"}


def test_encode_decode_roundtrip():
    for s in ["what happened yesterday?", "café", "a+b", "x&y=z", "日本"]:
        assert decode(encode(s)) == s


def test_forms_convert():
    a = Address.parse("!tcxp:/handlers/join?mode=strict")
    assert str(a.to_form("https", "example.com")) == "https://example.com/tcxp/handlers/join?mode=strict"
    assert str(a.to_form("tcxp", "registry.example")) == "tcxp://registry.example/handlers/join?mode=strict"
    with pytest.raises(AddressError):
        a.to_form("https")
