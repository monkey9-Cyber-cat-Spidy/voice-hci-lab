"""Meta-command speech: words that are *about* the text rather than part of it.

"new line", "period", "delete the last sentence", "bullet this" ... These are
turned into inline **markers** (a private-use sentinel token) so that:

* pivot resolution can treat them as clause boundaries ("...new line bullet
  notify the on call, scratch that" retracts only the last bullet), and
* their position survives retractions without any offset bookkeeping.

``apply_commands`` then walks the marked text and materialises each marker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MARK = ""  # private-use char; never produced by ASR

_PUNCT = {
    "period": ".",
    "full stop": ".",
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "colon": ":",
    "semicolon": ";",
}

_COMMAND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("new_paragraph", re.compile(r"new paragraph\b", re.IGNORECASE)),
    ("new_line", re.compile(r"new line\b|line break\b", re.IGNORECASE)),
    ("delete_sentence", re.compile(r"delete (?:the )?last sentence\b", re.IGNORECASE)),
    ("delete_word", re.compile(r"delete (?:the )?last word\b", re.IGNORECASE)),
    ("bullet", re.compile(r"(?:bullet point|bullet this|make (?:this|that) a bullet|bullet)\b", re.IGNORECASE)),
    ("capitalize", re.compile(r"capitali[sz]e (?:that|this|it)\b", re.IGNORECASE)),
    ("select_all", re.compile(r"select all\b", re.IGNORECASE)),
    ("undo", re.compile(r"undo(?: that| this| it)?\b", re.IGNORECASE)),
]
_PUNCT_RE = re.compile(
    r"(" + "|".join(sorted(map(re.escape, _PUNCT), key=len, reverse=True)) + r")\b", re.IGNORECASE
)
_MARKER_RE = re.compile(MARK + r"([a-z_]+)(?:\|([^" + MARK + r"]*))?" + MARK)
_WORD_START_RE = re.compile(r"(?:^|(?<=\s))")


@dataclass(frozen=True)
class Command:
    name: str
    arg: str = ""

    def marker(self) -> str:
        return f"{MARK}{self.name}|{self.arg}{MARK}" if self.arg else f"{MARK}{self.name}{MARK}"


def is_marker(token: str) -> bool:
    return token.startswith(MARK) and token.endswith(MARK)


def extract_commands(text: str) -> str:
    """Replace command phrases in ``text`` with inline markers.

    Only matches at word starts, so "period" inside "periodic" or "bullet"
    inside "bulletin" is left alone.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        at_word_start = i == 0 or text[i - 1].isspace()
        if at_word_start:
            hit: Command | None = None
            end = i
            for name, pat in _COMMAND_PATTERNS:
                m = pat.match(text, i)
                if m:
                    hit, end = Command(name), m.end()
                    break
            if hit is None:
                m = _PUNCT_RE.match(text, i)
                if m:
                    hit, end = Command("punct", _PUNCT[m.group(1).lower()]), m.end()
            if hit is not None:
                out.append(" " + hit.marker() + " ")
                i = end
                while i < n and text[i] in " ,":
                    i += 1
                continue
        out.append(text[i])
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def strip_markers(marked: str) -> str:
    return re.sub(r"\s+", " ", _MARKER_RE.sub(" ", marked)).strip()


def apply_commands(marked: str, *, newline: str = "\n", bullet_prefix: str = "- ") -> str:
    """Materialise markers left-to-right."""
    out = ""
    pos = 0
    for m in _MARKER_RE.finditer(marked):
        out = _append_text(out, marked[pos : m.start()], newline)
        name, arg = m.group(1), m.group(2) or ""
        out = _apply_one(out, name, arg, newline, bullet_prefix)
        pos = m.end()
    out = _append_text(out, marked[pos:], newline)
    return out.strip(" ")


def _append_text(out: str, chunk: str, newline: str) -> str:
    chunk = chunk.strip()
    if not chunk:
        return out
    if not out or out[-1] in (newline, " "):
        return out + chunk
    return out + " " + chunk


def _apply_one(out: str, name: str, arg: str, newline: str, bullet_prefix: str) -> str:
    if name == "punct":
        return out.rstrip(" .,!?;:") + arg
    if name == "new_line":
        return out.rstrip(" ") + newline
    if name == "new_paragraph":
        return out.rstrip(" ") + newline + newline
    if name == "delete_sentence":
        head = out.rstrip()
        sentences = re.split(r"(?<=[.!?])\s+", head)
        return " ".join(sentences[:-1]) if len(sentences) > 1 else ""
    if name == "delete_word":
        head = out.rstrip()
        # keep a trailing newline structure intact
        lines = head.split(newline)
        words = lines[-1].split()
        lines[-1] = " ".join(words[:-1])
        return newline.join(lines)
    if name == "bullet":
        if not out or out.endswith(newline):
            return out + bullet_prefix
        lines = out.split(newline)
        if not lines[-1].startswith(bullet_prefix):
            lines[-1] = bullet_prefix + lines[-1].lstrip()
        return newline.join(lines)
    if name == "capitalize":
        lines = out.split(newline)
        words = lines[-1].split()
        if words:
            words[-1] = words[-1][:1].upper() + words[-1][1:]
            lines[-1] = " ".join(words)
        return newline.join(lines)
    # select_all / undo are OS-level: handled by the agent, not the text
    return out
