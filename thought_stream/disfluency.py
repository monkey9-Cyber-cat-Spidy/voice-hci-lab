"""Disfluency handling: filler removal and course-correction ("pivot") resolution.

Humans speak in a stream of thought:

    "send an update saying the deployment is ready ... actually wait,
     make that delayed until 4 PM"

Verbatim dictation types both the retracted and the corrected thought. A
destructive rewrite throws the whole field away. We want the *final intent*
with a surgical edit. The heuristics here are deliberately rule-based: they
run in microseconds, are deterministic (testable), and the benchmark tells
us exactly which patterns they miss.

Two classes of pivot phrase:

* **hard** pivots are unambiguous edit instructions ("make that", "change
  that to", "I mean", "no wait", "scratch that"). They always fire.
* **soft** pivots are words that are *usually* content ("no", "actually",
  "wait", "sorry", "rather"). They fire only if the correction can be aligned
  to the last clause by a structural strategy (restart / anchor /
  complement); otherwise they are left in the text. This is what stops
  "there is no way" or "it's actually fine" from being mangled.

Replacement strategies, tried in order:

1. **restart** - the correction repeats the opening words of the last clause
   ("send it to john ... no, send it to jane"): replace from the divergence
   point.
2. **anchor** - the correction starts with a preposition/copula that occurs in
   the last clause ("to john at four ... no wait, to jane at four").
3. **complement** - replace what follows the last copula/preposition ("the
   deployment is ready" -> "is delayed until 4 PM").
4. **tail** - a short correction (<= 2 words) replaces the same number of
   trailing words ("at four ... I mean five").
5. **clause** - replace the whole last clause.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .commands import MARK

_FILLERS = {"um", "uh", "uhm", "umm", "er", "erm", "hmm", "mm", "ah"}

_HARD_PIVOTS = [
    r"no wait", r"wait no", r"make that", r"make it", r"change that to", r"change it to",
    r"i mean", r"let'?s say", r"correction",
]
_SOFT_PIVOTS = [r"actually", r"wait", r"sorry", r"no", r"rather"]
_DELETE_PIVOTS = [
    r"scratch that", r"never ?mind that", r"never ?mind", r"delete that", r"forget that",
    r"strike that", r"ignore that",
]

_ALL_PIVOTS = _HARD_PIVOTS + _SOFT_PIVOTS
# One or more pivot words in a row ("actually wait make that"), each followed
# by a word boundary so "no" never matches inside "notify".
_REPLACE_RE = re.compile(
    r"(?:^|(?<=\s))(?:(?:" + "|".join(_ALL_PIVOTS) + r")(?![a-z'])[,.]?\s*)+", re.IGNORECASE
)
_DELETE_RE = re.compile(
    r"(?:^|(?<=\s))(?:" + "|".join(_DELETE_PIVOTS) + r")(?![a-z'])[,.]?", re.IGNORECASE
)
_HARD_RE = re.compile(r"\b(?:" + "|".join(_HARD_PIVOTS) + r")\b", re.IGNORECASE)
_FILLER_RE = re.compile(
    r"(?:(?<=^)|(?<=\s))(?:" + "|".join(sorted(_FILLERS, key=len, reverse=True))
    + r")[,.]?(?=\s|$)",
    re.IGNORECASE,
)
_VERB_COPULAS = {"is", "are", "was", "were", "be", "been", "being", "am", "should", "will",
                 "would", "can", "could", "says", "saying", "said", "about"}
_PREPS = {"to", "at", "on", "in", "by", "for", "until", "till", "from", "with", "as", "of"}
_COPULAS = _VERB_COPULAS | _PREPS
_VALUE_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "noon", "midnight", "monday", "tuesday", "wednesday",
                "thursday", "friday", "saturday", "sunday", "today", "tomorrow", "tonight",
                "am", "pm", "january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december", "week", "month"}


def _looks_like_value(word: str) -> bool:
    """Numbers, times, dates: things people correct one token at a time."""
    w = _norm(word)
    return bool(w) and (w[0].isdigit() or w in _VALUE_WORDS)
# Clause boundaries: sentence punctuation, commas, conjunctions, and command markers.
_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?;])\s+|\s*,\s*|\s+(?:and|but|then|so|because)\s+|\s*" + MARK + r"[^" + MARK + r"]*"
    + MARK + r"\s*",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
_TRAILING_JOIN_RE = re.compile(r"(?:[,;]|\s+(?:and|but|then|so|because))\s*$", re.IGNORECASE)


def strip_fillers(text: str) -> str:
    out = _FILLER_RE.sub("", text)
    out = _WS_RE.sub(" ", out)
    out = re.sub(r"\s+([,.!?;:])", r"\1", out)
    return out.strip()


@dataclass(frozen=True)
class PivotEvent:
    kind: str  # "replace" | "delete"
    pivot: str  # the trigger phrase
    retracted: str  # text that was removed
    replacement: str  # text that took its place ("" for delete)
    strategy: str  # how the replace span was chosen


_STRUCTURAL = {"restart", "anchor", "complement"}


def _last_clause_span(text: str) -> tuple[int, int]:
    last = 0
    for m in _CLAUSE_SPLIT_RE.finditer(text):
        last = m.end()
    return last, len(text)


def _norm(w: str) -> str:
    return w.lower().strip(".,!?;:")


def _apply_replace(prefix: str, correction: str, pivot: str) -> tuple[str, PivotEvent]:
    prefix = prefix.rstrip()
    cs, ce = _last_clause_span(prefix)
    clause = prefix[cs:ce]
    cw = clause.split()
    rw = correction.split()
    lcw = [_norm(w) for w in cw]
    lrw = [_norm(w) for w in rw]

    # 1) restart
    k = 0
    while k < min(len(lcw), len(lrw)) and lcw[k] == lrw[k]:
        k += 1
    if k >= 1 and (k >= 2 or len(lrw) >= 3 or len(lcw) <= 3):
        new_clause = " ".join(cw[:k] + rw[k:])
        return prefix[:cs] + new_clause, PivotEvent(
            "replace", pivot, " ".join(cw[k:]), " ".join(rw[k:]), "restart")

    # 2) anchor on a copula/preposition the correction opens with
    if lrw and lrw[0] in _COPULAS:
        for idx in range(len(lcw) - 1, 0, -1):
            if lcw[idx] == lrw[0]:
                new_clause = " ".join(cw[:idx] + rw)
                return prefix[:cs] + new_clause, PivotEvent(
                    "replace", pivot, " ".join(cw[idx:]), correction, "anchor")

    # 3) complement swap. Prefer the verb copula ("is on hold" -> "is merged")
    #    unless the last preposition introduces a *value* ("at four" -> "at five").
    v = next((i for i in range(len(lcw) - 2, -1, -1) if lcw[i] in _VERB_COPULAS), None)
    pidx = next((i for i in range(len(lcw) - 2, -1, -1) if lcw[i] in _PREPS), None)
    anchor = None
    if pidx is not None and (v is None or pidx > v) and (
            v is None or _looks_like_value(cw[pidx + 1]) or lrw[0] in _PREPS):
        anchor = pidx
    elif v is not None:
        anchor = v
    elif pidx is not None:
        anchor = pidx
    if anchor is not None:
        new_clause = " ".join(cw[: anchor + 1] + rw)
        return prefix[:cs] + new_clause, PivotEvent(
            "replace", pivot, " ".join(cw[anchor + 1:]), correction, "complement")

    # 4) tail swap
    if 0 < len(rw) <= 2 and len(cw) > len(rw):
        new_clause = " ".join(cw[: len(cw) - len(rw)] + rw)
        return prefix[:cs] + new_clause, PivotEvent(
            "replace", pivot, " ".join(cw[len(cw) - len(rw):]), correction, "tail")

    # 5) whole clause
    return prefix[:cs] + correction, PivotEvent("replace", pivot, clause, correction, "clause")


def _is_hard(pivot: str) -> bool:
    return bool(_HARD_RE.search(pivot))


def resolve_pivots(text: str, *, final: bool = True) -> tuple[str, list[PivotEvent]]:
    """Resolve all pivots left-to-right. Returns (clean_text, events).

    ``text`` may contain command markers (see commands.MARK); they act as
    clause boundaries and are otherwise carried through untouched.

    With ``final=False`` (streaming partials) a trailing pivot whose
    correction is still short (< 2 words for hard pivots, < 3 for soft) is
    *deferred*: the pivot and its partial correction are hidden and the text
    before it is returned unchanged. Applying too early picks the wrong span
    and costs a visible double rewrite.
    """
    events: list[PivotEvent] = []
    text = _WS_RE.sub(" ", text).strip()
    start = 0
    while True:
        md = _DELETE_RE.search(text, start)
        mr = _REPLACE_RE.search(text, start)
        cands = [m for m in (md, mr) if m]
        if not cands:
            break
        m = min(cands, key=lambda x: x.start())
        # Drop the comma/conjunction that led into the pivot so the clause
        # span is computed on real content ("..., second point, never mind").
        before = _TRAILING_JOIN_RE.sub("", text[: m.start()].rstrip())
        after = text[m.end():].lstrip()

        if m is md:
            cs, ce = _last_clause_span(before)
            retracted = before[cs:ce]
            new_before = _TRAILING_JOIN_RE.sub("", before[:cs].rstrip()).rstrip()
            events.append(PivotEvent("delete", m.group(0).strip(" ,."), retracted, "", "clause"))
            text = (new_before + " " + after).strip()
            start = len(new_before)
            continue

        pivot = m.group(0).strip(" ,.")
        hard = _is_hard(pivot)
        if not before:
            # Leading pivot word with nothing to correct: drop hard ones, keep soft.
            if hard:
                text = after
                continue
            start = m.end()
            continue

        nxt = [x for x in (_DELETE_RE.search(after), _REPLACE_RE.search(after)) if x]
        cut = min(x.start() for x in nxt) if nxt else len(after)
        correction = after[:cut].strip()
        rest = after[cut:]

        if not correction:
            if hard:
                text = (before + " " + rest).strip()
            else:
                start = m.end()
            continue

        if not final and not rest and len(correction.split()) < (2 if hard else 3):
            # Trailing pivot, correction still forming: hide it for now.
            text = before
            break

        new_text, ev = _apply_replace(before, correction, pivot)
        if not hard and ev.strategy not in _STRUCTURAL:
            # Soft pivot that does not align structurally: treat as content.
            start = m.end()
            continue
        events.append(ev)
        text = (new_text + " " + rest).strip() if rest else new_text
        start = len(new_text)
    return text, events
