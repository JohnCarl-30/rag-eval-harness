from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "our",
        "how",
        "what",
        "when",
        "does",
        "with",
        "from",
        "this",
        "that",
        "have",
        "has",
        "was",
        "into",
        "your",
        "about",
        "a",
        "an",
        "to",
        "of",
        "in",
        "on",
        "is",
        "or",
    }
)


def tokenize(text: str) -> set[str]:
    return {tok for tok in _TOKEN.findall(text.lower()) if tok not in _STOP and len(tok) > 1}


def overlap(numerator: set[str], denominator: set[str]) -> float:
    if not denominator:
        return 0.0
    return round(len(numerator & denominator) / len(denominator), 4)
