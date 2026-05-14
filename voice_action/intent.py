"""Streaming intent classification.

The classifier is called on every partial transcript. It returns a list of
``IntentHypothesis`` (compound commands like "open slack and message john"
yield two) with a confidence that *rises as slots fill in*. The speculative
executor acts on the first hypothesis whose confidence clears a threshold -
typically right after the verb and target are heard.

It is grammar-based on purpose: it costs microseconds, it is deterministic,
and the benchmark measures exactly which phrasings it misses. A learned
classifier can be dropped in behind the same ``classify`` signature.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import StrEnum

from hci_common.text import normalize_words
from thought_stream.disfluency import resolve_pivots, strip_fillers


class Intent(StrEnum):
    OPEN_APP = "open_app"
    FOCUS_WINDOW = "focus_window"
    SEND_MESSAGE = "send_message"
    SEARCH_WEB = "search_web"
    MOVE_FILE = "move_file"
    TYPE_TEXT = "type_text"
    UNDO = "undo"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


@dataclass
class IntentHypothesis:
    intent: Intent
    slots: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    complete: bool = False
    span: str = ""

    def key(self) -> tuple:
        """Identity used to decide whether a speculation is still valid."""
        return (self.intent, self.slots.get("app"), self.slots.get("recipient"),
                self.slots.get("dest"))


# Canonical app names -> aliases as users say them (and as ASR mishears them).
APP_ALIASES: dict[str, tuple[str, ...]] = {
    "slack": ("slack", "slag", "slack app"),
    "chrome": ("chrome", "google chrome", "the browser", "browser"),
    "edge": ("edge", "microsoft edge"),
    "vscode": ("vs code", "vscode", "visual studio code", "code", "the editor", "editor"),
    "terminal": ("terminal", "windows terminal", "the terminal", "powershell", "command prompt"),
    "notepad": ("notepad", "note pad"),
    "spotify": ("spotify",),
    "outlook": ("outlook", "mail", "email"),
    "excel": ("excel", "spreadsheet"),
    "word": ("word", "microsoft word"),
    "figma": ("figma",),
    "discord": ("discord",),
    "teams": ("teams", "microsoft teams"),
    "calculator": ("calculator", "calc"),
    "explorer": ("explorer", "file explorer", "files", "finder"),
    "notion": ("notion",),
    "whatsapp": ("whatsapp", "whats app"),
}
_ALIAS_INDEX = {alias: app for app, aliases in APP_ALIASES.items() for alias in aliases}
_ALIAS_LIST = sorted(_ALIAS_INDEX, key=len, reverse=True)

_OPEN_VERBS = r"(?:open|launch|start|run|fire up|bring up)"
_FOCUS_VERBS = r"(?:switch to|go to|focus|jump to|show me)"
_MSG_VERBS = r"(?:message|text|tell|dm|ping|slack)"
_SEARCH_VERBS = r"(?:search(?: the web)?(?: for)?|google|look up)"
_TYPE_VERBS = r"(?:type|write|insert|dictate)"
_MSG_SEP = r"(?:saying|that|say|:)?"
_FILL = r"(?:\s+(?:the|up|a|my))*"


def resolve_app(fragment: str) -> tuple[str | None, float]:
    """Map a spoken fragment to a canonical app name with a confidence."""
    frag = " ".join(normalize_words(fragment))
    if not frag:
        return None, 0.0
    if frag in _ALIAS_INDEX:
        return _ALIAS_INDEX[frag], 1.0
    for alias in _ALIAS_LIST:
        if frag.startswith(alias + " ") or frag == alias:
            return _ALIAS_INDEX[alias], 0.95
    first = frag.split()[0]
    close = difflib.get_close_matches(first, list(_ALIAS_INDEX), n=1, cutoff=0.8)
    if close:
        return _ALIAS_INDEX[close[0]], 0.7
    return None, 0.0


def _split_compound(text: str) -> list[str]:
    """Split "open slack and message john ..." into verb-led parts."""
    verb = rf"(?:{_OPEN_VERBS}|{_FOCUS_VERBS}|{_MSG_VERBS}|{_SEARCH_VERBS}|{_TYPE_VERBS}|move|undo|cancel)"
    parts = re.split(rf"\s+(?:and|then|and then)\s+(?={verb}\b)", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _hyp(intent: Intent, slots: dict[str, str], conf: float, complete: bool,
         span: str) -> IntentHypothesis:
    return IntentHypothesis(intent, slots, round(conf, 3), complete, span)


def _classify_one(text: str, is_last: bool) -> IntentHypothesis:
    t = text.strip()
    low = t.lower()

    if re.fullmatch(r"(?:undo(?: that| it)?|take that back|revert(?: that)?)[.!]?", low):
        return _hyp(Intent.UNDO, {}, 0.95, True, t)
    if re.fullmatch(r"(?:cancel|stop|never ?mind|abort)(?: that)?[.!]?", low):
        return _hyp(Intent.CANCEL, {}, 0.95, True, t)

    m = re.match(rf"^{_OPEN_VERBS}{_FILL}(?:\s+(?P<rest>.*))?$", low)
    if m:
        rest = m.group("rest") or ""
        app, ac = resolve_app(rest)
        if app:
            return _hyp(Intent.OPEN_APP, {"app": app}, 0.55 + 0.4 * ac, True, t)
        return _hyp(Intent.OPEN_APP, {}, 0.35 if not rest else 0.3, False, t)

    m = re.match(rf"^{_FOCUS_VERBS}{_FILL}(?:\s+(?P<rest>.*))?$", low)
    if m:
        rest = m.group("rest") or ""
        app, ac = resolve_app(rest)
        if app:
            return _hyp(Intent.FOCUS_WINDOW, {"app": app}, 0.55 + 0.4 * ac, True, t)
        return _hyp(Intent.FOCUS_WINDOW, {}, 0.35, False, t)

    m = re.match(
        rf"^{_MSG_VERBS}\s+(?P<recipient>[a-z][a-z'\-]*)"
        rf"(?:\s+(?:on|in|via)\s+(?P<app>[a-z ]+?))?"
        rf"(?:\s+{_MSG_SEP}\s*(?P<body>.+))?$",
        low,
    )
    if m:
        slots = {"recipient": m.group("recipient")}
        conf = 0.6
        if m.group("app"):
            app, _ = resolve_app(m.group("app"))
            if app:
                slots["app"] = app
                conf = 0.7
        body = (m.group("body") or "").strip()
        # recover original casing for the body from the raw text
        if body:
            idx = low.rfind(body)
            slots["body"] = t[idx: idx + len(body)] if idx >= 0 else body
            conf = 0.9
        return _hyp(Intent.SEND_MESSAGE, slots, conf, bool(body) and is_last, t)
    if re.match(rf"^{_MSG_VERBS}\b", low):
        return _hyp(Intent.SEND_MESSAGE, {}, 0.4, False, t)

    m = re.match(rf"^{_SEARCH_VERBS}(?:\s+(?P<q>.+))?$", low)
    if m:
        q = (m.group("q") or "").strip()
        if q:
            idx = low.rfind(q)
            return _hyp(Intent.SEARCH_WEB, {"query": t[idx: idx + len(q)]}, 0.85, is_last, t)
        return _hyp(Intent.SEARCH_WEB, {}, 0.4, False, t)

    m = re.match(r"^move\s+(?:this|that|the|the current)?\s*(?:file|folder|document)?"
                 r"(?:\s+(?:to|into)\s+(?P<dest>.+))?$", low)
    if m:
        dest = (m.group("dest") or "").strip()
        if dest:
            return _hyp(Intent.MOVE_FILE, {"dest": dest}, 0.85, is_last, t)
        return _hyp(Intent.MOVE_FILE, {}, 0.4, False, t)

    m = re.match(rf"^{_TYPE_VERBS}(?:\s+(?P<body>.+))?$", low)
    if m:
        body = (m.group("body") or "").strip()
        if body:
            idx = low.rfind(body)
            return _hyp(Intent.TYPE_TEXT, {"text": t[idx: idx + len(body)]}, 0.8, is_last, t)
        return _hyp(Intent.TYPE_TEXT, {}, 0.35, False, t)

    return _hyp(Intent.UNKNOWN, {}, 0.0, False, t)


class StreamingIntentClassifier:
    """Stateless prefix classifier. Call with the full partial transcript.

    Fillers are stripped and course-corrections resolved first (shared with
    Thought-Stream), so "open spotify, no wait, open slack" is classified as
    OPEN_APP(slack) and the Spotify speculation is aborted, not executed.
    """

    def __init__(self, resolve_disfluency: bool = True) -> None:
        self.resolve_disfluency = resolve_disfluency

    def classify(self, partial: str, *, final: bool = True) -> list[IntentHypothesis]:
        text = re.sub(r"\s+", " ", partial).strip().strip(".!?")
        if self.resolve_disfluency and text:
            resolved, _ = resolve_pivots(strip_fillers(text), final=final)
            # "never mind" alone is a CANCEL, not a retraction of nothing.
            text = resolved or text
        if not text:
            return []
        parts = _split_compound(text)
        return [_classify_one(p, i == len(parts) - 1) for i, p in enumerate(parts)]

    def primary(self, partial: str, *, final: bool = True) -> IntentHypothesis | None:
        hyps = self.classify(partial, final=final)
        return hyps[0] if hyps else None
