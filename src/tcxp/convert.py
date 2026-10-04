"""Convert an address's key-value pairs to and from other formats.

Everything in tcxp resolves to keys and values, so every format below is the same
table written a different way. Repeated keys (lists) stay lists.

    to_json(addr)      from_json(text, path=...)
    to_dict(addr)      from_dict(d, path=...)
    to_csv(addr)       from_csv(text, path=...)     # columns: key,value (one row per value)
    to_sql(addr)       CREATE TABLE + INSERT rows (key, position, value)
    to_python(addr)    a Python dict literal
    to_js(addr)        a JavaScript object literal
    to_cpp(addr)       std::map<std::string, std::vector<std::string>>
    to_java(addr)      Map<String, List<String>>
    convert(addr, fmt) any of: uri, json, dict, csv, sql, python, js, cpp, java

Round trips through JSON, dict and CSV return exactly the same canonical address.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Mapping

from .address import Address

__all__ = ["to_dict", "from_dict", "to_json", "from_json", "to_csv", "from_csv", "to_sql",
           "to_python", "to_js", "to_cpp", "to_java", "convert", "FORMATS"]

FORMATS = ("uri", "json", "dict", "csv", "sql", "python", "js", "cpp", "java")


def _addr(a: Address | str) -> Address:
    return a if isinstance(a, Address) else Address.parse(a)


def to_dict(a: Address | str) -> dict[str, Any]:
    """``{"address": "...", "path": "...", "params": {key: value or [values]}}``."""
    a = _addr(a)
    return {"address": str(a), "form": a.form, "authority": a.authority, "path": a.path_text, "params": a.to_dict()}


def from_dict(d: Mapping[str, Any], path: str | None = None) -> Address:
    if "address" in d and path is None:
        return Address.parse(d["address"])
    params = d.get("params", d)
    base = Address.build(path if path is not None else d.get("path", ""), form=d.get("form", "virtual"),
                         authority=d.get("authority", ""))
    return base.set_many({k: v for k, v in params.items()})


def to_json(a: Address | str, indent: int | None = 2) -> str:
    return json.dumps(to_dict(a), indent=indent, ensure_ascii=False)


def from_json(text: str, path: str | None = None) -> Address:
    return from_dict(json.loads(text), path)


def _pairs(a: Address) -> list[tuple[str, str]]:
    return [(k, v) for k, vals in a.params for v in vals]


def to_csv(a: Address | str) -> str:
    a = _addr(a)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["key", "value"])
    w.writerows(_pairs(a))
    return buf.getvalue()


def from_csv(text: str, path: str = "") -> Address:
    rows = list(csv.reader(io.StringIO(text)))
    groups: dict[str, list[str]] = {}
    for key, value in rows[1:]:
        groups.setdefault(key, []).append(value)
    return Address.build(path).set_many({k: (v if len(v) > 1 else v[0]) for k, v in groups.items()})


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def to_sql(a: Address | str, table: str = "tcxp_state") -> str:
    a = _addr(a)
    lines = [f"CREATE TABLE IF NOT EXISTS {table} (address TEXT, key TEXT, position INTEGER, value TEXT);"]
    for k, vals in a.params:
        for i, v in enumerate(vals):
            lines.append(f"INSERT INTO {table} (address, key, position, value) VALUES "
                         f"({_sql_str(str(a))}, {_sql_str(k)}, {i}, {_sql_str(v)});")
    return "\n".join(lines)


def _lit(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def to_python(a: Address | str) -> str:
    return "{\n" + "".join(f"    {_lit(k)}: {_lit(v) if not isinstance(v, list) else '[' + ', '.join(map(_lit, v)) + ']'},\n"
                            for k, v in _addr(a).to_dict().items()) + "}"


def to_js(a: Address | str) -> str:
    a = _addr(a)
    body = "".join(f"  {_lit(k)}: {_lit(v) if not isinstance(v, list) else '[' + ', '.join(map(_lit, v)) + ']'},\n"
                   for k, v in a.to_dict().items())
    return f"// {a}\nconst state = {{\n{body}}};"


def to_cpp(a: Address | str) -> str:
    a = _addr(a)
    rows = "".join(f"    {{{_lit(k)}, {{{', '.join(map(_lit, vals))}}}}},\n" for k, vals in a.params)
    return (f"// {a}\n#include <map>\n#include <string>\n#include <vector>\n\n"
            f"const std::map<std::string, std::vector<std::string>> state = {{\n{rows}}};")


def to_java(a: Address | str) -> str:
    a = _addr(a)
    rows = ",\n".join(f"    Map.entry({_lit(k)}, List.of({', '.join(map(_lit, vals))}))" for k, vals in a.params)
    return (f"// {a}\nimport java.util.List;\nimport java.util.Map;\n\n"
            f"Map<String, List<String>> state = Map.ofEntries(\n{rows}\n);")


def convert(a: Address | str, fmt: str = "uri") -> str:
    fmt = fmt.lower()
    if fmt == "uri":
        return str(_addr(a))
    table = {"json": to_json, "dict": lambda x: repr(to_dict(x)), "csv": to_csv, "sql": to_sql,
             "python": to_python, "js": to_js, "cpp": to_cpp, "java": to_java}
    if fmt not in table:
        raise ValueError(f"Unknown format {fmt!r}; use one of {FORMATS}")
    return table[fmt](a)
