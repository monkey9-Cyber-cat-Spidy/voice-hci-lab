"""Small text utilities shared across projects."""

from __future__ import annotations

import re
from collections.abc import Sequence

_WORD_RE = re.compile(r"[a-z0-9']+")


def normalize_words(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, punctuation stripped."""
    return _WORD_RE.findall(text.lower())


def levenshtein(a: Sequence, b: Sequence) -> int:
    """Edit distance over any sequences (chars or words)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def word_error_rate(hyp: str, ref: str) -> float:
    ref_words = normalize_words(ref)
    hyp_words = normalize_words(hyp)
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return levenshtein(hyp_words, ref_words) / len(ref_words)
