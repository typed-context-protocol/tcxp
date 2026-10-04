"""Schema: what makes tcxp *typed*.

A Schema declares, for each key: its type, its allowed values (the answer space),
whether it is essential to a decision, a default and a plain description.
Parsing checks values against the schema. Invalid values are reported, never guessed.

Types: ``str``, ``int``, ``float``, ``bool``, ``date`` (ISO 8601 ``YYYY-MM-DD``),
``address`` (a tcxp pointer), ``handler`` (an ``@name`` reference).
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .address import Address, is_address_text

__all__ = ["Field", "Schema", "Problem", "SchemaError", "TYPES"]

TYPES = ("str", "int", "float", "bool", "date", "address", "handler")


class SchemaError(ValueError):
    """Raised for a schema that cannot work (unknown type, bad default)."""


@dataclass(frozen=True)
class Problem:
    key: str
    message: str

    def __str__(self) -> str:
        return f"{self.key}: {self.message}"


@dataclass(frozen=True)
class Field:
    name: str
    type: str = "str"
    values: tuple[str, ...] = ()      # the declared answer space; empty = any value of the type
    essential: bool = False           # a decision cannot be made while this is Dark
    default: Any = None
    description: str = ""
    many: bool = False                # repeated keys allowed (a list)

    def __post_init__(self) -> None:
        if self.type not in TYPES:
            raise SchemaError(f"{self.name}: unknown type {self.type!r}; use one of {TYPES}")

    def coerce(self, text: str) -> Any:
        """Turn the address text into a typed Python value, or raise ValueError."""
        if text == "":
            return None
        t = self.type
        if t == "str":
            value: Any = text
        elif t == "int":
            if not re.fullmatch(r"-?[0-9]+", text):
                raise ValueError("expected a whole number like 2024")
            value = int(text)
        elif t == "float":
            if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?", text):
                raise ValueError("expected a finite decimal number")
            value = float(text)
        elif t == "bool":
            if text not in ("true", "false"):
                raise ValueError("expected 'true' or 'false'")
            value = text == "true"
        elif t == "date":
            value = _dt.date.fromisoformat(text)
            if value.isoformat() != text:
                raise ValueError("expected YYYY-MM-DD")
        elif t == "address":
            if not is_address_text(text):
                raise ValueError("expected a tcxp address")
            value = Address.parse(text)
        else:  # handler
            if not text.startswith("@"):
                raise ValueError("expected a handler reference starting with '@'")
            value = text
        if self.values and text not in self.values:
            raise ValueError(f"not in the declared answer space {list(self.values)}")
        return value


@dataclass
class Schema:
    name: str
    fields: dict[str, Field] = field(default_factory=dict)

    @classmethod
    def of(cls, name: str, *fields: Field) -> "Schema":
        return cls(name, {f.name: f for f in fields})

    def add(self, f: Field) -> "Schema":
        self.fields[f.name] = f
        return self

    @property
    def essential(self) -> tuple[str, ...]:
        return tuple(n for n, f in self.fields.items() if f.essential)

    def problems(self, address: Address) -> list[Problem]:
        """Every value that does not fit its declared type or answer space."""
        out = []
        for key, f in self.fields.items():
            vals = address.get_all(key)
            if len(vals) > 1 and not f.many:
                out.append(Problem(key, "repeated, but the schema allows one value"))
            for v in vals:
                try:
                    f.coerce(v)
                except ValueError as exc:
                    out.append(Problem(key, f"{v!r} is not valid: {exc}"))
        return out

    def coerce(self, address: Address) -> dict[str, Any]:
        """Typed values for every declared key (defaults fill absent keys). Raises on problems."""
        probs = self.problems(address)
        if probs:
            raise ValueError("; ".join(map(str, probs)))
        out: dict[str, Any] = {}
        for key, f in self.fields.items():
            vals = address.get_all(key)
            if f.many:
                out[key] = [f.coerce(v) for v in vals if v != ""]
            else:
                out[key] = f.coerce(vals[0]) if vals else f.default
        return out

    def dark(self, address: Address) -> tuple[str, ...]:
        """Essential keys that are absent, empty or invalid: what still has to be known."""
        bad = {p.key for p in self.problems(address)}
        return tuple(k for k in self.essential
                     if not address.get_all(k) or any(v == "" for v in address.get_all(k)) or k in bad)

    def to_address(self) -> Address:
        """The schema itself as an address, so it can be shared by link."""
        params: dict[str, Any] = {}
        for n, f in self.fields.items():
            params[n] = f.type + ("[]" if f.many else "")
            if f.values:
                params[f"{n}.values"] = list(f.values)
            if f.essential:
                params[f"{n}.essential"] = True
        return Address.build(f"schema/{self.name}", params)

    @classmethod
    def from_address(cls, address: Address) -> "Schema":
        name = address.path[-1] if address.path else "schema"
        d = address.to_dict()
        s = cls(name)
        for key, val in d.items():
            if "." in key:
                continue
            typ, many = (val[:-2], True) if str(val).endswith("[]") else (val, False)
            vals = address.get_all(f"{key}.values")
            s.add(Field(key, typ, tuple(v for v in vals if v), address.get(f"{key}.essential") == "true", many=many))
        return s

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "fields": [vars(f) | {"values": list(f.values)} for f in self.fields.values()]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Schema":
        return cls.of(data["name"], *(Field(**(f | {"values": tuple(f.get("values", ()))})) for f in data["fields"]))
