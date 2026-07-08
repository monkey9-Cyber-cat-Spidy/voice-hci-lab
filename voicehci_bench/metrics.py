"""HCI metrics."""

from __future__ import annotations

import difflib
import statistics

from hci_common.text import normalize_words, word_error_rate


def correction_overhead(output: str, gold: str) -> tuple[int, float]:
    """Keystrokes a human needs to turn ``output`` into ``gold``, and that
    count per gold character (the Correction Overhead Rate).

    Human edit model: for each differing span (difflib opcode) the user pays
    one navigation press (click / Home / arrow burst) plus one press per
    deleted character and one per inserted character. Capitalising a letter
    therefore costs 3 (navigate, backspace, type), not a full retype.
    """
    if output == gold:
        return 0, 0.0
    sm = difflib.SequenceMatcher(None, output, gold, autojunk=False)
    cost = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        cost += 1 + (i2 - i1) + (j2 - j1)
    denom = max(1, len(gold))
    return cost, round(cost / denom, 4)


def intent_drift(output: str, retracted: list[str], required: list[str]) -> bool | None:
    """True when the retracted thought leaked (or the corrected one is missing)."""
    if not retracted and not required:
        return None
    words = set(normalize_words(output))
    leaked = any(t.lower() in words for t in retracted)
    missing = any(t.lower() not in words for t in required)
    return leaked or missing


def wer(output: str, gold: str) -> float:
    return round(word_error_rate(output, gold), 4)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    k = (len(vs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return round(vs[lo] + (vs[hi] - vs[lo]) * (k - lo), 3)


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0
