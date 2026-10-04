"""Addresses: the only editable state in tcxp.

An Address is an immutable value, like JavaScript's ``URL`` but frozen. Editing
one returns a new Address, so every change is a value you can keep, hash and log.

Three written forms point at the same kind of thing:

=====================  ==========================================  ===========
Form                   Example                                     Meaning
=====================  ==========================================  ===========
virtual                ``!tcxp:/temperature/meaning/celsius``      In-memory pointer. Not an address; nothing is hosted.
tcxp                   ``tcxp://registry.example/handlers/join``   A real protocol address, resolved through a registry.
https (carrier)        ``https://example.com/tcxp/handlers/join``  The same address in a form any browser or tool accepts.
=====================  ==========================================  ===========

``!tcxp:/`` is notation, not URI syntax (a URI must start with a letter). When a
virtual pointer has to pass through a standard URI tool, ``to_uri()`` writes it as
``tcxp:/...`` (single slash: no host), and ``Address.parse`` reads that back as virtual.

Canonical form (``str(address)``) is the core guarantee: the same state always
produces exactly the same string. Keys are sorted; repeated keys keep their order
(that is how lists are written); values are percent-encoded the same way every time.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

__all__ = ["Address", "AddressError", "encode", "decode", "is_address_text", "parse_query",
           "format_query", "MAX_INLINE", "VIRTUAL_PREFIX"]

VIRTUAL_PREFIX = "!tcxp:/"
MAX_INLINE = 2000  # characters; above this, store the state and point to it by hash

_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_VALUE_SAFE = _UNRESERVED | frozenset("!:/@")
_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_SEG_RE = re.compile(r"^[A-Za-z0-9._~\-]+$")
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+(:[0-9]+)?$")


class AddressError(ValueError):
    """Raised when text is not a valid tcxp address."""


def encode(text: str, safe: frozenset = _VALUE_SAFE) -> str:
    """Percent-encode ``text`` the one canonical way (UTF-8, uppercase hex)."""
    out = []
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AddressError("Text contains an invalid Unicode character (a lone surrogate)") from exc
    for byte in raw:
        ch = chr(byte)
        out.append(ch if byte < 128 and ch in safe else f"%{byte:02X}")
    return "".join(out)


def decode(text: str) -> str:
    """Strict percent-decoding. ``+`` is a literal plus sign, never a space."""
    raw = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "%":
            pair = text[i + 1:i + 3]
            if len(pair) != 2 or not all(c in "0123456789abcdefABCDEF" for c in pair):
                raise AddressError(f"Bad percent-encoding near {text[i:i + 3]!r}")
            raw.append(int(pair, 16))
            i += 3
        else:
            raw.extend(ch.encode("utf-8"))
            i += 1
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AddressError("Percent-encoded bytes are not valid UTF-8") from exc


def is_address_text(value: str) -> bool:
    """True when a value is itself a tcxp address (a pointer), not plain text."""
    return isinstance(value, str) and (value.startswith(VIRTUAL_PREFIX) or value.startswith("tcxp:"))


def _canonical_pointer(text: str) -> str:
    """A value that parses as a tcxp address is a pointer, stored canonically; anything else stays text."""
    if is_address_text(text):
        try:
            return str(Address.parse(text))
        except AddressError:
            return text
    return text


def parse_query(query: str) -> dict[str, tuple[str, ...]]:
    """Parse ``a=1&b=x&b=y`` into ``{"a": ("1",), "b": ("x", "y")}``. Keys keep their value order."""
    groups: dict[str, list[str]] = {}
    if not query:
        return {}
    for part in query.split("&"):
        if part == "":
            raise AddressError("Empty parameter (two '&' in a row, or a trailing '&')")
        key, sep, value = part.partition("=")
        key = decode(key)
        if not _KEY_RE.fullmatch(key):
            raise AddressError(f"Key {key!r} may only use letters, digits, '_', '.', '-'")
        value = decode(value) if sep else ""
        value = _canonical_pointer(value)  # nested pointers are stored canonically; other text is kept as is
        groups.setdefault(key, []).append(value)
    return {k: tuple(v) for k, v in groups.items()}


def format_query(params: Iterable[tuple[str, tuple[str, ...]]]) -> str:
    return "&".join(f"{k}={encode(v)}" for k, vals in params for v in vals)


def _to_text(value: Any) -> str:
    if isinstance(value, Address):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return repr(value) if not value.is_integer() else str(int(value))
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    text = "" if value is None else str(value)
    return _canonical_pointer(text)


@dataclass(frozen=True)
class Address:
    """An immutable, canonical tcxp address.

    >>> a = Address.parse("!tcxp:/reason?tax_year=&task=section_41")
    >>> a.with_(tax_year=2024).get("tax_year")
    '2024'
    """

    form: str = "virtual"              # "virtual" | "tcxp" | "https"
    path: tuple[str, ...] = ()
    params: tuple[tuple[str, tuple[str, ...]], ...] = ()
    authority: str = ""                # host for tcxp:// ; host[/prefix] for https

    # ---------- construction ----------
    @classmethod
    def parse(cls, text: str) -> "Address":
        """Read any of the three forms. Raises AddressError on anything else."""
        if not isinstance(text, str):
            raise AddressError("Address text must be a string")
        if "#" in text:
            raise AddressError("Fragments ('#') are not part of tcxp state")
        bad = next((c for c in text if not 0x21 <= ord(c) <= 0x7E), None)
        if bad is not None:
            raise AddressError(f"Character U+{ord(bad):04X} must be percent-encoded "
                               "(addresses contain only printable ASCII; spaces, controls and non-ASCII are encoded)")
        rest, _, query = text.partition("?")
        if rest.startswith(VIRTUAL_PREFIX) or (rest.startswith("tcxp:/") and not rest.startswith("tcxp://")):
            body = rest[len("!tcxp:"):] if rest.startswith("!") else rest[len("tcxp:"):]
            if body.startswith("//"):
                raise AddressError("A virtual pointer has no host: use '!tcxp:/path', not '!tcxp://'")
            form, authority, path = "virtual", "", body[1:]
        elif rest.startswith("tcxp://"):
            authority, _, path = rest[len("tcxp://"):].partition("/")
            if not authority or not _HOST_RE.fullmatch(authority):
                raise AddressError(f"Invalid host {authority!r}")
            form = "tcxp"
        elif rest.startswith("https://"):
            hostpart, marker, path = rest[len("https://"):].partition("/tcxp/")
            if not marker and rest.endswith("/tcxp"):
                hostpart, path = rest[len("https://"):-len("/tcxp")], ""
            elif not marker:
                raise AddressError("An https carrier address must contain '/tcxp/'")
            host = hostpart.split("/", 1)[0]
            if not host or not _HOST_RE.fullmatch(host):
                raise AddressError(f"Invalid host {host!r}")
            form, authority = "https", hostpart
        else:
            raise AddressError("Expected '!tcxp:/', 'tcxp:/', 'tcxp://' or 'https://…/tcxp/'")
        segments = tuple(s for s in path.split("/")) if path else ()
        if path.endswith("/"):
            raise AddressError("Paths cannot end with '/'")
        for seg in segments:
            if not _SEG_RE.fullmatch(seg):
                raise AddressError(f"Path segment {seg!r} may only use letters, digits, '.', '_', '~', '-'")
        groups = parse_query(query)
        return cls(form, segments, tuple(sorted(groups.items())), authority)

    @classmethod
    def build(cls, path: str | Iterable[str] = "", params: Mapping[str, Any] | None = None,
              form: str = "virtual", authority: str = "") -> "Address":
        """Build from parts: ``Address.build("reason/section-41", {"tax_year": 2024})``."""
        segs = tuple(s for s in (path.split("/") if isinstance(path, str) else path) if s)
        addr = cls.parse(cls._prefix(form, authority) + "/".join(segs))
        return addr.with_(**(params or {})) if params else addr

    # ---------- canonical text ----------
    @staticmethod
    def _prefix(form: str, authority: str) -> str:
        if form == "virtual":
            return VIRTUAL_PREFIX
        if form == "tcxp":
            return f"tcxp://{authority}/"
        if form == "https":
            return f"https://{authority}/tcxp/"
        raise AddressError(f"Unknown form {form!r}")

    def __str__(self) -> str:
        text = self._prefix(self.form, self.authority) + "/".join(self.path)
        return text + ("?" + format_query(self.params) if self.params else "")

    def __repr__(self) -> str:
        return f"Address({str(self)!r})"

    def to_uri(self) -> str:
        """A string every standard URI parser accepts (virtual becomes ``tcxp:/...``)."""
        text = str(self)
        return "tcxp:/" + text[len(VIRTUAL_PREFIX):] if self.form == "virtual" else text

    @property
    def is_virtual(self) -> bool:
        return self.form == "virtual"

    @property
    def path_text(self) -> str:
        return "/".join(self.path)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(str(self).encode("utf-8")).hexdigest()

    def __len__(self) -> int:
        return len(str(self))

    # ---------- reading ----------
    def _lookup(self) -> dict[str, tuple[str, ...]]:
        return dict(self.params)

    def get(self, key: str, default: Any = None) -> Any:
        """First value for ``key``; ``default`` when the key is absent."""
        vals = self._lookup().get(key)
        return vals[0] if vals else default

    def get_all(self, key: str) -> tuple[str, ...]:
        return self._lookup().get(key, ())

    def __contains__(self, key: str) -> bool:
        return key in self._lookup()

    def keys(self) -> tuple[str, ...]:
        return tuple(k for k, _ in self.params)

    def to_dict(self) -> dict[str, Any]:
        """``{key: value}`` for single values, ``{key: [values]}`` for repeated keys."""
        return {k: (v[0] if len(v) == 1 else list(v)) for k, v in self.params}

    # ---------- editing (always returns a new Address) ----------
    def with_(self, **values: Any) -> "Address":
        """Set keys. ``None`` removes a key; a list writes repeated keys; ``[]`` or ``""`` means Dark."""
        return self.set_many(values)

    def set(self, key: str, value: Any) -> "Address":
        return self.set_many({key: value})

    def set_many(self, values: Mapping[str, Any]) -> "Address":
        groups = self._lookup()
        for key, value in values.items():
            if not _KEY_RE.fullmatch(key):
                raise AddressError(f"Key {key!r} may only use letters, digits, '_', '.', '-'")
            if value is None:
                groups.pop(key, None)
            elif isinstance(value, (list, tuple)):
                groups[key] = tuple(_to_text(v) for v in value) or ("",)
            else:
                groups[key] = (_to_text(value),)
        return Address(self.form, self.path, tuple(sorted(groups.items())), self.authority)

    def without(self, *keys: str) -> "Address":
        return self.set_many({k: None for k in keys})

    def at(self, path: str | Iterable[str]) -> "Address":
        """Same parameters, different path."""
        segs = tuple(s for s in (path.split("/") if isinstance(path, str) else path) if s)
        return Address.parse(self._prefix(self.form, self.authority) + "/".join(segs)).set_many(self.to_dict())

    def to_form(self, form: str, authority: str = "") -> "Address":
        """Rewrite in another form, e.g. virtual → https carrier."""
        if form != "virtual" and not authority:
            raise AddressError("tcxp:// and https:// forms need a host")
        return Address(form, self.path, self.params, authority if form != "virtual" else "")
