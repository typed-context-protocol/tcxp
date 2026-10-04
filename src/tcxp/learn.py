"""Small learned models that train in milliseconds, from confirmed answers.

``SoftmaxPerceptron`` classifies text (which card, which task, does it state a tax
year) using hashed word and word-pair features. Pure Python, no dependencies.

Its probabilities plug into the same gate as Jev's: confident answers can act,
the rest are asked. ``as_checker()`` makes it a rung on the ladder.

Training data comes from the trace: rows a person confirmed (``learnable=True``)
are labeled examples. ``examples_from_trace`` collects them.

``reliability_curve`` answers "how much data until it's reliable?": it trains on
the first k examples per class and tests on held-out examples it never saw.
"""
from __future__ import annotations

import math
import random
import re
import zlib
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .ladder import Answer, Question

__all__ = ["SoftmaxPerceptron", "Evaluation", "examples_from_trace", "reliability_curve", "confidence_of"]


def confidence_of(probs: Sequence[float]) -> float:
    """How concentrated a distribution is: 0 when flat, 1 when all on one option."""
    n = len(probs)
    return (max(probs) - 1 / n) / (1 - 1 / n) if n > 1 else 1.0


@dataclass(frozen=True)
class Evaluation:
    n: int
    accuracy: float
    confident_accuracy: float | None
    coverage: float


class SoftmaxPerceptron:
    """Multiclass softmax perceptron with sparse weights (cheap enough for thousands of instances)."""

    def __init__(self, classes: Sequence[str], dim: int = 1024, epochs: int = 40, lr: float = 0.5, seed: int = 7):
        self.classes = list(classes)
        self.dim, self.epochs, self.lr, self.seed = dim, epochs, lr, seed
        self.W: list[dict[int, float]] = [{} for _ in self.classes]
        self.b = [0.0] * len(self.classes)
        self.n_trained = 0

    def features(self, text: str) -> dict[int, float]:
        toks = re.findall(r"[a-z0-9%$&/]+", text.lower())
        idx = {zlib.crc32(f"w:{t}".encode()) % self.dim for t in toks}
        idx |= {zlib.crc32(f"b:{a}_{b}".encode()) % self.dim for a, b in zip(toks, toks[1:])}
        idx |= {zlib.crc32(f"y:{bool(re.search(r'20[0-9]{2}|fy ?[0-9]{2}', text.lower()))}".encode()) % self.dim}
        scale = 1 / math.sqrt(len(idx) or 1)
        return {i: scale for i in idx}

    def _scores(self, x: dict[int, float]) -> list[float]:
        return [self.b[c] + sum(self.W[c].get(i, 0.0) * v for i, v in x.items()) for c in range(len(self.classes))]

    @staticmethod
    def _softmax(z: list[float]) -> list[float]:
        m = max(z)
        e = [math.exp(v - m) for v in z]
        s = sum(e)
        return [v / s for v in e]

    def _step(self, x: dict[int, float], y: int, lr: float) -> None:
        p = self._softmax(self._scores(x))
        for c in range(len(self.classes)):
            g = p[c] - (1.0 if c == y else 0.0)
            self.b[c] -= lr * g
            row = self.W[c]
            for i, v in x.items():
                row[i] = row.get(i, 0.0) - lr * g * v

    def fit(self, texts: Sequence[str], labels: Sequence[str]) -> "SoftmaxPerceptron":
        data = [(self.features(t), self.classes.index(y)) for t, y in zip(texts, labels) if y in self.classes]
        rng = random.Random(self.seed)
        for _ in range(self.epochs):
            rng.shuffle(data)
            for x, y in data:
                self._step(x, y, self.lr)
        self.n_trained += len(data)
        return self

    def partial_fit(self, text: str, label: str, passes: int = 3) -> "SoftmaxPerceptron":
        """Learn from one new confirmed example right away (online)."""
        if label in self.classes:
            x, y = self.features(text), self.classes.index(label)
            for _ in range(passes):
                self._step(x, y, self.lr)
            self.n_trained += 1
        return self

    def predict_proba(self, text: str) -> dict[str, float]:
        return dict(zip(self.classes, self._softmax(self._scores(self.features(text)))))

    def predict(self, text: str) -> tuple[str, float]:
        p = self.predict_proba(text)
        best = max(p, key=p.get)
        return best, confidence_of(list(p.values()))

    def evaluate(self, texts: Sequence[str], labels: Sequence[str], threshold: float = 0.6) -> Evaluation:
        right = conf = conf_right = 0
        for t, y in zip(texts, labels):
            guess, c = self.predict(t)
            right += guess == y
            if c >= threshold:
                conf += 1
                conf_right += guess == y
        n = len(texts)
        return Evaluation(n, right / n if n else 0.0, conf_right / conf if conf else None, conf / n if n else 0.0)

    def as_checker(self, name: str = "perceptron"):
        model = self

        class _Checker:
            def __init__(self) -> None:
                self.name = name

            def check(self, q: Question) -> Answer | None:
                if not model.n_trained:
                    return None
                value, c = model.predict(q.text)
                if q.options and value not in q.options:
                    return None
                return Answer(value, c, name)
        return _Checker()


def examples_from_trace(rows: Iterable[Any], key: str | None = None) -> tuple[list[str], list[str]]:
    """Labeled examples: (features text, confirmed value) from learnable trace rows."""
    texts, labels = [], []
    for r in rows:
        if getattr(r, "learnable", False) and (key is None or r.key == key) and r.features:
            texts.append(r.features)
            labels.append(r.value)
    return texts, labels


def reliability_curve(train: Sequence[tuple[str, str]], test: Sequence[tuple[str, str]], classes: Sequence[str],
                      ks: Iterable[int] | None = None, threshold: float = 0.6) -> list[tuple[int, Evaluation]]:
    """Train on the first k examples per class, test on held-out examples, for each k."""
    per: dict[str, list[str]] = {c: [] for c in classes}
    for t, y in train:
        if y in per:
            per[y].append(t)
    max_k = max((len(v) for v in per.values()), default=0)
    out = []
    for k in (ks or range(1, max_k + 1)):
        texts = [t for c in classes for t in per[c][:k]]
        labels = [c for c in classes for _ in per[c][:k]]
        m = SoftmaxPerceptron(classes).fit(texts, labels)
        out.append((k, m.evaluate([t for t, _ in test], [y for _, y in test], threshold)))
    return out
