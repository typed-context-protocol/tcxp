"""Expression trees as addresses: write a rule as math, fold it upward, ask about Dark leaves.

``3 + 2y = 9`` becomes a tree (each operator is a parent; its left and right children are
what it combines) and the tree becomes one flat address, one key per node::

    !tcxp:/expr?n1=eq&n1.l=n2&n1.r=9&n2=add&n2.l=3&n2.r=n3&n3=mul&n3.l=2&n3.r=y&root=n1

* A child is a node id (``n3``), a number (``9``) or a variable (``y``).
* Variables are read from state (a context object's keys). A missing or empty one is
  **Dark**: the fold stops and reports it, so the gate asks instead of guessing.
* Folding is exact (fractions, never floats) and deterministic: the same address and
  the same state always give the same result, and every step is listed for the trace.
* ``solve`` finds the one Dark variable of a linear equation (``y = 3``) with no model.

Operators: ``add`` ``sub`` ``mul`` ``div`` and ``eq`` (true/false). Implicit
multiplication (``2y``, ``2(x+1)``) and unary minus are supported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Union

from .address import Address

__all__ = ["Node", "parse", "to_address", "from_address", "fold", "solve", "Fold", "draw", "OPS"]

OPS = {"add": "+", "sub": "-", "mul": "×", "div": "÷", "eq": "="}
_SYM = {"+": "add", "-": "sub", "*": "mul", "×": "mul", "/": "div", "÷": "div", "=": "eq"}
_NODE_ID = re.compile(r"n[0-9]+")
_VAR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUM = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


@dataclass
class Node:
    op: str
    left: "Child"
    right: "Child"


Child = Union[Node, str]   # a Node, a number written as text, or a variable name


# ---------- parsing: infix text → tree ----------
def parse(text: str) -> Child:
    """Parse ``3 + 2y = 9`` (also ``*``, ``/``, ``-``, parentheses) into a tree."""
    toks = re.findall(r"[0-9]+(?:\.[0-9]+)?|[A-Za-z_][A-Za-z0-9_]*|[-+*/×÷=()]|\S", text)
    bad = next((t for t in toks if not (_NUM.fullmatch(t) or _VAR.fullmatch(t) or t in "+-*/×÷=()")), None)
    if bad:
        raise ValueError(f"Unexpected {bad!r} in expression")
    for t in toks:
        if _NODE_ID.fullmatch(t):
            raise ValueError(f"Variable name {t!r} is reserved for node ids; rename it")
    pos = 0

    def peek() -> str:
        return toks[pos] if pos < len(toks) else ""

    def take(expected: str | None = None) -> str:
        nonlocal pos
        t = peek()
        if not t or (expected and t != expected):
            raise ValueError(f"Expected {expected or 'a value'}, found {t or 'the end'!r}")
        pos += 1
        return t

    def equation() -> Child:
        left = expr()
        if peek() == "=":
            take()
            return Node("eq", left, expr())
        return left

    def expr() -> Child:
        node = term()
        while peek() in ("+", "-"):
            node = Node(_SYM[take()], node, term())
        return node

    def term() -> Child:
        node = unary()
        while peek() in ("*", "/", "×", "÷") or (peek() and (peek() == "(" or _VAR.fullmatch(peek())
                                                              or _NUM.fullmatch(peek()))):
            op = _SYM[take()] if peek() in ("*", "/", "×", "÷") else "mul"   # 2y means 2 × y
            node = Node(op, node, unary())
        return node

    def unary() -> Child:
        if peek() == "-":
            take()
            inner = unary()
            return ("-" + inner if isinstance(inner, str) and _NUM.fullmatch(inner) and not inner.startswith("-")
                    else Node("mul", "-1", inner))
        if peek() == "(":
            take()
            inner = equation()
            take(")")
            return inner
        t = take()
        if not (_NUM.fullmatch(t) or _VAR.fullmatch(t)):
            raise ValueError(f"Expected a number or a name, found {t!r}")
        return t

    tree = equation()
    if peek():
        raise ValueError(f"Unexpected {peek()!r} after the expression")
    return tree


# ---------- tree ↔ address ----------
def to_address(tree: Child, path: str = "expr") -> Address:
    params: dict[str, str] = {}
    counter = 0

    def walk(c: Child) -> str:
        nonlocal counter
        if not isinstance(c, Node):
            return c
        counter += 1
        nid = f"n{counter}"
        params[nid] = c.op
        params[f"{nid}.l"] = walk(c.left)
        params[f"{nid}.r"] = walk(c.right)
        return nid

    params["root"] = walk(tree)
    return Address.build(path, params)


def from_address(address: Address | str) -> Child:
    a = address if isinstance(address, Address) else Address.parse(address)
    root = a.get("root")
    if root is None:
        raise ValueError("Expression address has no 'root' key")
    seen: set[str] = set()

    def build(ref: str) -> Child:
        if not _NODE_ID.fullmatch(ref):
            return ref
        if ref in seen:
            raise ValueError(f"Node {ref} appears twice (a tree has no cycles or shared nodes)")
        seen.add(ref)
        op = a.get(ref)
        if op not in OPS:
            raise ValueError(f"Node {ref} has unknown operator {op!r}")
        left, right = a.get(f"{ref}.l"), a.get(f"{ref}.r")
        if left is None or right is None:
            raise ValueError(f"Node {ref} needs both {ref}.l and {ref}.r")
        return Node(op, build(left), build(right))

    return build(root)


# ---------- folding ----------
@dataclass
class Fold:
    value: Any = None                          # Fraction, bool, or None when Dark
    dark: tuple[str, ...] = ()                 # variables with no value: ask about these
    steps: list[dict[str, str]] = field(default_factory=list)   # one row per node, bottom-up

    @property
    def complete(self) -> bool:
        return not self.dark


def _leaf(c: str, state: Mapping[str, Any]) -> Fraction | None:
    if _NUM.fullmatch(c):
        return Fraction(c)
    v = state.get(c)
    if isinstance(v, (list, tuple)):
        v = v[0] if len(v) == 1 else None
    if v in (None, ""):
        return None
    if isinstance(v, bool) or not _NUM.fullmatch(str(v)):
        raise ValueError(f"{c} = {v!r} is not a number")
    return Fraction(str(v))


def _show(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return "" if v is None else str(v)


def fold(tree: Child | Address | str, state: Mapping[str, Any] | None = None) -> Fold:
    """Evaluate bottom-up. Dark variables are collected, never guessed."""
    if isinstance(tree, (Address,)) or (isinstance(tree, str) and tree.startswith(("!tcxp:", "tcxp:"))):
        tree = from_address(tree)
    state = dict(state or {})
    out = Fold()
    dark: list[str] = []
    counter = 0

    def ev(c: Child) -> Any:
        nonlocal counter
        if not isinstance(c, Node):
            v = _leaf(c, state)
            if v is None and c not in dark:
                dark.append(c)
            return v
        counter += 1
        nid = f"n{counter}"
        lv, rv = ev(c.left), ev(c.right)
        if lv is None or rv is None:
            res = None
        elif c.op == "eq":
            res = lv == rv
        elif isinstance(lv, bool) or isinstance(rv, bool):
            raise ValueError("Can't do arithmetic on a true/false result")
        elif c.op == "add":
            res = lv + rv
        elif c.op == "sub":
            res = lv - rv
        elif c.op == "mul":
            res = lv * rv
        else:
            if rv == 0:
                raise ValueError("Division by zero")
            res = lv / rv
        out.steps.append({"node": nid, "op": c.op, "left": _show(lv) or "DARK", "right": _show(rv) or "DARK",
                          "result": _show(res) or "DARK"})
        return res

    out.value = ev(tree)
    out.dark = tuple(dark)
    return out


def solve(tree: Child | Address | str, state: Mapping[str, Any] | None = None) -> dict[str, Fraction]:
    """Solve a linear equation for its single Dark variable: ``3 + 2y = 9`` → ``{"y": 3}``."""
    if isinstance(tree, Address) or (isinstance(tree, str) and tree.startswith(("!tcxp:", "tcxp:"))):
        tree = from_address(tree)
    if not isinstance(tree, Node) or tree.op != "eq":
        raise ValueError("solve needs an equation (with '=')")
    state = dict(state or {})
    unknown = fold(tree, state).dark
    if len(unknown) != 1:
        raise ValueError(f"solve needs exactly one Dark variable; found {list(unknown) or 'none'}")
    x = unknown[0]

    def lin(c: Child) -> tuple[Fraction, Fraction]:   # value = a·x + b
        if not isinstance(c, Node):
            if c == x:
                return Fraction(1), Fraction(0)
            return Fraction(0), _leaf(c, state)  # type: ignore[return-value]
        (a1, b1), (a2, b2) = lin(c.left), lin(c.right)
        if c.op == "add":
            return a1 + a2, b1 + b2
        if c.op == "sub":
            return a1 - a2, b1 - b2
        if c.op == "mul":
            if a1 and a2:
                raise ValueError(f"{x} is multiplied by itself: not a linear equation")
            return a1 * b2 + a2 * b1, b1 * b2
        if c.op == "div":
            if a2:
                raise ValueError(f"{x} is in a divisor: not a linear equation")
            if b2 == 0:
                raise ValueError("Division by zero")
            return a1 / b2, b1 / b2
        raise ValueError("'=' can only appear once, at the top")

    (a1, b1), (a2, b2) = lin(tree.left), lin(tree.right)
    if a1 == a2:
        raise ValueError(f"{x} cancels out: the equation has no single solution")
    return {x: (b2 - b1) / (a1 - a2)}


def draw(tree: Child, state: Mapping[str, Any] | None = None) -> str:
    """The tree as indented text, Dark variables marked."""
    state = state or {}
    lines: list[str] = []

    def label(c: Child) -> str:
        if isinstance(c, Node):
            return OPS[c.op]
        if _NUM.fullmatch(c):
            return c
        v = state.get(c)
        return f"{c} = {v}" if v not in (None, "") else f"{c}  (Dark)"

    def walk(c: Child, prefix: str, last: bool, top: bool) -> None:
        lines.append(("" if top else prefix + ("└─ " if last else "├─ ")) + label(c))
        if isinstance(c, Node):
            nxt = "" if top else prefix + ("   " if last else "│  ")
            walk(c.left, nxt, False, False)
            walk(c.right, nxt, True, False)

    walk(tree, "", True, True)
    return "\n".join(lines)
