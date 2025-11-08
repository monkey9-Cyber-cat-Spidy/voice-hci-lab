"""Contextual style mirroring.

The same utterance should land differently in Slack than in a Google Doc or
a terminal. We inspect the active window (app name / title / control kind)
and pick a StyleProfile. Keep this table-driven so it is obvious what the
engine does and trivially extensible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AppContext:
    app_name: str = ""  # process/executable or product name, e.g. "Slack"
    window_title: str = ""
    control_kind: str = "text"  # "text" | "code" | "terminal" | "search" | "url"

    @property
    def key(self) -> str:
        return (self.app_name or self.window_title).lower()


@dataclass(frozen=True)
class StyleProfile:
    name: str
    capitalize_sentences: bool = True
    terminal_punctuation: bool = True  # add trailing period to statements
    newline: str = "\n"
    bullet_prefix: str = "- "
    lowercase_all: bool = False
    collapse_newlines: bool = False  # chat apps: Enter sends; use shift+enter semantics
    tone: str = "neutral"
    notes: tuple[str, ...] = field(default_factory=tuple)


CASUAL = StyleProfile(
    "casual-chat", capitalize_sentences=True, terminal_punctuation=False, bullet_prefix="• ",
    tone="conversational", notes=("no trailing period on single sentences",),
)
PROFESSIONAL = StyleProfile(
    "professional-doc", capitalize_sentences=True, terminal_punctuation=True, bullet_prefix="- ",
    tone="professional",
)
CODE = StyleProfile(
    "code", capitalize_sentences=False, terminal_punctuation=False, lowercase_all=False,
    bullet_prefix="// ", tone="literal", notes=("never auto-punctuate in editors/terminals",),
)
SEARCH = StyleProfile(
    "search", capitalize_sentences=False, terminal_punctuation=False, lowercase_all=True,
    tone="literal",
)

_CHAT_APPS = ("slack", "whatsapp", "discord", "telegram", "teams", "messages", "imessage",
              "signal", "messenger", "wechat")
_DOC_APPS = ("notion", "docs", "word", "pages", "obsidian", "confluence", "outlook", "gmail",
             "mail", "notes")
_CODE_APPS = ("code", "vscode", "cursor", "pycharm", "intellij", "vim", "neovim", "sublime",
              "terminal", "powershell", "cmd", "iterm", "alacritty", "wezterm", "windowsterminal")


def resolve_style(ctx: AppContext) -> StyleProfile:
    if ctx.control_kind in ("code", "terminal"):
        return CODE
    if ctx.control_kind in ("search", "url"):
        return SEARCH
    k = ctx.key
    if any(a in k for a in _CODE_APPS):
        return CODE
    if any(a in k for a in _CHAT_APPS):
        return CASUAL
    if any(a in k for a in _DOC_APPS):
        return PROFESSIONAL
    return PROFESSIONAL


_SENT_SPLIT = re.compile(r"([.!?]\s+)")


def _capitalize_sentences(text: str) -> str:
    parts = _SENT_SPLIT.split(text)
    out = []
    cap_next = True
    for part in parts:
        if not part:
            continue
        if _SENT_SPLIT.fullmatch(part):
            out.append(part)
            cap_next = True
            continue
        if cap_next and part:
            # capitalize first alpha char, preserving leading bullets/newlines
            i = 0
            while i < len(part) and not part[i].isalpha():
                i += 1
            if i < len(part):
                part = part[:i] + part[i].upper() + part[i + 1 :]
            cap_next = False
        out.append(part)
    return "".join(out)


def format_for(text: str, profile: StyleProfile) -> str:
    """Apply a style profile to *complete* text (idempotent)."""
    if not text:
        return text
    if profile.lowercase_all:
        return text.lower()
    lines = text.split(profile.newline)
    styled: list[str] = []
    for line in lines:
        s = line
        if profile.capitalize_sentences and s:
            s = _capitalize_sentences(s)
        styled.append(s)
    out = profile.newline.join(styled)
    if profile.terminal_punctuation:
        stripped = out.rstrip()
        if stripped and stripped[-1].isalnum():
            out = stripped + "."
    return out
