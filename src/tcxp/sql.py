"""A tiny, versioned SQL simulator over CSV files, plus SQL query cards.

Dialect ``tcxp-sql/0.1`` (deliberately small; later versions add to it):

    SELECT <items> FROM <table> [WHERE <cond> [AND <cond>]...]
    items : *  |  column [, column]  |  SUM(col) | COUNT(*) | COUNT(col) | MIN(col) | MAX(col)
    cond  : column (= | != | < | > | <= | >=) value  |  column BETWEEN value AND value
    value : 'text'  |  number  |  :slot

Every stored value is a string. Comparisons are numeric when both sides look like
numbers, otherwise text (so ISO dates like 2024-01-31 compare correctly).
Anything outside the dialect raises ``SQLError`` naming the dialect.

Tables load from CSV and register at ``!tcxp:/sql/table/<name>``.

A **QueryCard** is a SQL template with ``:slots``. Slots are filled from the context
object's state (directly, or derived: tax_year → start_date and end_date). Missing
slots are what the terminal highlights and what the gate asks about.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .address import Address
from .registry import Registry

__all__ = ["DIALECT", "SQLError", "Table", "Database", "Result", "QueryCard", "tax_year_bounds"]

DIALECT = "tcxp-sql/0.1"


class SQLError(ValueError):
    pass


@dataclass
class Table:
    name: str
    columns: list[str]
    rows: list[dict[str, str]]

    @classmethod
    def from_csv(cls, name: str, source: str | Path) -> "Table":
        text = Path(source).read_text(encoding="utf-8") if isinstance(source, Path) or (
            isinstance(source, str) and "\n" not in source and Path(source).exists()) else str(source)
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for n, r in enumerate(reader, start=2):
            if None in r:
                raise SQLError(f"CSV for table {name!r}, line {n}: more values than columns")
            rows.append({k.strip(): (v or "").strip() for k, v in r.items()})
        return cls(name, [c.strip() for c in (reader.fieldnames or [])], rows)


@dataclass
class Result:
    columns: list[str]
    rows: list[list[str]]
    sql: str

    def scalar(self) -> str:
        return self.rows[0][0] if self.rows and self.rows[0] else ""


_TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<slot>:[A-Za-z_][A-Za-z0-9_]*)|"
                    r"(?P<op><=|>=|!=|=|<|>|,|\(|\)|\*)|(?P<word>[A-Za-z_][A-Za-z0-9_]*))")


def _tokens(sql: str) -> list[tuple[str, str]]:
    out, pos, sql = [], 0, sql.strip().rstrip(";")
    while pos < len(sql):
        m = _TOKEN.match(sql, pos)
        if not m or m.end() == pos:
            raise SQLError(f"{DIALECT}: unexpected text at {sql[pos:pos + 12]!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
    return out


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _num(v: str) -> float | None:
    """Plain decimal numbers only: 'NaN', 'inf', '1_000' and '1e3' are text."""
    return float(v) if _NUMBER.fullmatch(v) else None


def _cmp(a: str, op: str, b: str) -> bool:
    na, nb = _num(a), _num(b)
    x, y = (na, nb) if na is not None and nb is not None else (a, b)
    return {"=": x == y, "!=": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(round(v, 6))


class Database:
    def __init__(self, registry: Registry | None = None):
        self.registry = registry or Registry()
        self.tables: dict[str, Table] = {}

    def load_csv_file(self, name: str, path: str | Path) -> Address:
        """Load a CSV from a file path; a missing file is an error (never read as CSV text)."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"No CSV file at {p}")
        return self.load_csv(name, p)

    def load_csv(self, name: str, source: str | Path) -> Address:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise SQLError(f"Table name {name!r} must be letters, digits and '_'")
        t = Table.from_csv(name, source)
        self.tables[name] = t
        return self.registry.put(f"!tcxp:/sql/table/{name}", t)

    def query(self, sql: str, params: Mapping[str, Any] | None = None) -> Result:
        params = dict(params or {})
        toks = _tokens(sql)
        i = 0

        def peek(n: int = 0) -> tuple[str, str]:
            return toks[i + n] if i + n < len(toks) else ("end", "")

        def take(kind: str | None = None, value: str | None = None) -> str:
            nonlocal i
            k, v = peek()
            if (kind and k != kind) or (value and v.upper() != value):
                raise SQLError(f"{DIALECT}: expected {value or kind}, found {v or 'end of query'!r}")
            i += 1
            return v

        def literal() -> str:
            k, v = peek()
            take()
            if k == "str":
                return v[1:-1].replace("''", "'")
            if k == "num":
                return v
            if k == "slot":
                name = v[1:]
                if params.get(name) in (None, ""):
                    raise SQLError(f"Slot :{name} is empty")
                return str(params[name])
            raise SQLError(f"{DIALECT}: expected a value, found {v!r}")

        take("word", "SELECT")
        items: list[tuple[str, str]] = []
        while True:
            k, v = peek()
            if v == "*":
                take()
                if items or peek()[1] == ",":
                    raise SQLError(f"{DIALECT}: '*' can't be combined with other columns")
                items.append(("*", "*"))
            elif k == "word" and v.upper() in ("SUM", "COUNT", "MIN", "MAX") and peek(1)[1] == "(":
                take()
                take("op", "(")
                col = take("op", "*") if peek()[1] == "*" else take("word")
                take("op", ")")
                if col == "*" and v.upper() != "COUNT":
                    raise SQLError(f"{DIALECT}: {v.upper()}(*) is not allowed; name a column")
                items.append((v.upper(), col))
            elif k == "word" and v.upper() != "FROM":
                items.append(("col", take("word")))
            else:
                raise SQLError(f"{DIALECT}: expected a column or aggregate, found {v!r}")
            if peek()[1] == ",":
                take()
                continue
            break
        take("word", "FROM")
        tname = take("word")
        if tname not in self.tables:
            raise SQLError(f"No table {tname!r}. Load it with Database.load_csv.")
        table = self.tables[tname]
        conds: list[Callable[[dict[str, str]], bool]] = []
        if peek()[1].upper() == "WHERE":
            take()
            while True:
                col = take("word")
                if col not in table.columns:
                    raise SQLError(f"Table {tname!r} has no column {col!r}")
                if peek()[1].upper() == "BETWEEN":
                    take()
                    lo = literal()
                    take("word", "AND")
                    hi = literal()
                    conds.append(lambda r, c=col, lo=lo, hi=hi: _cmp(r[c], ">=", lo) and _cmp(r[c], "<=", hi))
                else:
                    op = take("op")
                    if op not in ("=", "!=", "<", ">", "<=", ">="):
                        raise SQLError(f"{DIALECT}: unsupported operator {op!r}")
                    val = literal()
                    conds.append(lambda r, c=col, op=op, val=val: _cmp(r[c], op, val))
                if peek()[1].upper() == "AND":
                    take()
                    continue
                break
        if peek()[0] != "end":
            raise SQLError(f"{DIALECT} supports only SELECT … FROM … WHERE … AND …; found {peek()[1]!r}")
        rows = [r for r in table.rows if all(c(r) for c in conds)]
        for kind, col in items:
            if col != "*" and col not in table.columns:
                raise SQLError(f"Table {tname!r} has no column {col!r}")
        if any(k in ("SUM", "COUNT", "MIN", "MAX") for k, _ in items):
            out = []
            for kind, col in items:
                vals = [r[col] for r in rows] if col != "*" else [""] * len(rows)
                nums = [n for n in (_num(v) for v in vals) if n is not None]
                if kind == "COUNT":
                    out.append(str(len([v for v in vals if col == "*" or v != ""])))
                elif kind == "SUM":
                    out.append(_fmt(sum(nums)))
                elif kind in ("MIN", "MAX"):
                    pick = min if kind == "MIN" else max
                    if nums and len(nums) == len([v for v in vals if v != ""]):
                        out.append(_fmt(pick(nums)))
                    else:                                   # text (e.g. ISO dates): compare as text
                        texts = [v for v in vals if v != ""]
                        out.append(pick(texts) if texts else "")
                else:
                    raise SQLError(f"{DIALECT}: mixing columns and aggregates needs GROUP BY (not in 0.1)")
            return Result([f"{k}({c})" for k, c in items], [out], sql)
        cols = table.columns if items == [("*", "*")] else [c for _, c in items]
        return Result(cols, [[r[c] for c in cols] for r in rows], sql)


def tax_year_bounds(state: Mapping[str, Any]) -> dict[str, str]:
    """Derive calendar-year start and end dates from ``tax_year``."""
    y = str(state.get("tax_year") or "")
    return {"start_date": f"{y}-01-01", "end_date": f"{y}-12-31"} if re.fullmatch(r"\d{4}", y) else {}


@dataclass
class QueryCard:
    """A SQL template whose ``:slots`` are filled from state."""

    id: str
    title: str
    template: str
    derive: Callable[[Mapping[str, Any]], Mapping[str, str]] | None = None
    descriptions: dict[str, str] = field(default_factory=dict)

    @property
    def slots(self) -> list[str]:
        return list(dict.fromkeys(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", self.template)))

    def fill(self, state: Mapping[str, Any]) -> dict[str, str]:
        values = {k: str(v) for k, v in state.items() if v not in (None, "") and not isinstance(v, (list, tuple))}
        if self.derive:
            values.update({k: v for k, v in self.derive(values).items() if v})
        return {s: values[s] for s in self.slots if s in values}

    def missing(self, state: Mapping[str, Any]) -> list[str]:
        filled = self.fill(state)
        return [s for s in self.slots if s not in filled]

    def address(self, state: Mapping[str, Any]) -> Address:
        filled = self.fill(state)
        return Address.build(f"sql/card/{self.id}", {"dialect": DIALECT, **{s: filled.get(s, "") for s in self.slots}})

    def run(self, db: Database, state: Mapping[str, Any]) -> Result:
        miss = self.missing(state)
        if miss:
            raise SQLError(f"Can't run: missing {', '.join(':' + m for m in miss)}")
        return db.query(self.template, self.fill(state))
