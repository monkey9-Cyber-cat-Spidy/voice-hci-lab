"""UI grounding through accessibility trees.

Instead of a full-screen screenshot and a vision model, we read the focused
window's accessibility tree (UI Automation on Windows, AXUIElement on macOS)
and resolve spoken targets ("the message box", "send button") by fuzzy name
match. Trees are small, deterministic, carry exact bounding boxes, and
snapshot in milliseconds.

``MockUIProvider`` lets tests and the benchmark run without a desktop.
"""

from __future__ import annotations

import difflib
import sys
from dataclasses import dataclass, field
from typing import Protocol

from hci_common.clock import Clock, MonotonicClock
from hci_common.text import normalize_words


@dataclass(frozen=True)
class UINode:
    role: str  # "edit" | "button" | "listitem" | "menuitem" | "hyperlink" | "tab" | ...
    name: str
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)  # left, top, right, bottom
    focused: bool = False
    value: str = ""
    automation_id: str = ""

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.rect
        return ((left + right) // 2, (top + bottom) // 2)


@dataclass
class UITree:
    app_name: str
    window_title: str
    nodes: list[UINode] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def focused(self) -> UINode | None:
        return next((n for n in self.nodes if n.focused), None)


class UIProvider(Protocol):
    def snapshot(self) -> UITree: ...  # pragma: no cover - protocol


class MockUIProvider:
    def __init__(self, tree: UITree | None = None) -> None:
        self.tree = tree or UITree("desktop", "")
        self.snapshots = 0

    def set_tree(self, tree: UITree) -> None:
        self.tree = tree

    def snapshot(self) -> UITree:
        self.snapshots += 1
        return self.tree


@dataclass(frozen=True)
class Match:
    node: UINode
    score: float


_ROLE_HINTS = {
    "box": ("edit", "combobox", "document"),
    "field": ("edit", "combobox"),
    "input": ("edit", "combobox"),
    "button": ("button", "splitbutton"),
    "tab": ("tab", "tabitem"),
    "link": ("hyperlink",),
    "menu": ("menuitem", "menu"),
    "channel": ("treeitem", "listitem", "hyperlink"),
    "item": ("listitem", "treeitem"),
}


def find_element(tree: UITree, query: str, roles: tuple[str, ...] | None = None,
                 min_score: float = 0.55) -> Match | None:
    """Best node for a spoken ``query`` ("the message box", "send button")."""
    qwords = normalize_words(query)
    if not qwords:
        return None
    hinted_roles: tuple[str, ...] = roles or ()
    if not hinted_roles:
        for w in qwords:
            if w in _ROLE_HINTS:
                hinted_roles = _ROLE_HINTS[w]
    content = [w for w in qwords if w not in _ROLE_HINTS and w not in ("the", "a", "an", "my")]
    q = " ".join(content) or " ".join(qwords)

    best: Match | None = None
    for node in tree.nodes:
        name = " ".join(normalize_words(node.name + " " + node.automation_id))
        if not name:
            continue
        score = difflib.SequenceMatcher(None, q, name).ratio()
        if q and q in name:
            score = max(score, 0.9)
        if hinted_roles:
            score += 0.15 if node.role in hinted_roles else -0.25
        if node.focused:
            score += 0.05
        if best is None or score > best.score:
            best = Match(node, round(score, 3))
    if best and best.score >= min_score:
        return best
    return None


def make_os_ui_provider(clock: Clock | None = None, budget_ms: float = 15.0) -> UIProvider:
    if sys.platform == "win32":
        from .backends.windows_uia import WindowsUIAProvider

        return WindowsUIAProvider(clock or MonotonicClock(), budget_ms=budget_ms)
    raise RuntimeError("No accessibility provider for this platform yet (macOS AX is a TODO).")
