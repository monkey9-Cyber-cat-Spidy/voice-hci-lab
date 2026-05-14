"""Actions with built-in undo, an undo stack, and an earned-trust policy.

Design rules:

* Every ``Action`` knows whether it is **reversible** and whether it is
  **speculative-safe** (may run on a hypothesis before the user finishes).
* ``execute`` returns a ``Receipt`` that carries everything ``undo`` needs.
* ``TrustPolicy`` decides, per action class, between ``auto`` (do it, show a
  micro-toast), ``preview`` (show the toast, do it after a grace window unless
  escaped) and ``confirm`` (wait for an explicit yes). Trust is earned by
  uncontested executions and lost by undos.
"""

from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from hci_common.clock import Clock, MonotonicClock
from hci_common.keystrokes import KeyOp, backspace, type_text

from .grounding import UIProvider, UITree, find_element

# --------------------------------------------------------------------------- OS backend


class OSBackend(Protocol):  # pragma: no cover - protocol
    def resolve_app(self, app: str) -> str | None: ...
    def open_app(self, app: str, *, prewarm: bool = False) -> str | None: ...
    def close_app(self, app: str) -> bool: ...
    def focus_app(self, app: str) -> bool: ...
    def foreground_title(self) -> str: ...
    def click(self, x: int, y: int) -> None: ...
    def dispatch_keys(self, ops: list[KeyOp]) -> None: ...
    def move_file(self, src: str, dst: str) -> str: ...


@dataclass
class MockOSBackend:
    """Records calls; simulates latency through an injected clock.

    Launch is modelled asynchronously the way a real ``Popen`` behaves: the
    call returns at once and the window becomes visible ``cold_start_ms``
    later. ``focus_app`` on a still-launching app waits for it.
    """

    clock: Clock = field(default_factory=MonotonicClock)
    installed: set[str] = field(default_factory=lambda: {
        "slack", "chrome", "vscode", "terminal", "notepad", "spotify", "outlook", "explorer",
        "notion", "discord", "teams", "calculator", "edge", "whatsapp"})
    running: set[str] = field(default_factory=set)
    foreground: str = "desktop"
    calls: list[tuple] = field(default_factory=list)
    typed: list[KeyOp] = field(default_factory=list)
    resolve_cost_ms: float = 40.0  # Start-menu / PATH lookup
    cold_start_ms: float = 350.0  # process launch to first window
    focus_cost_ms: float = 20.0
    last_window_visible_at: float | None = None
    _resolved: set[str] = field(default_factory=set)
    _launching: dict[str, float] = field(default_factory=dict)  # app -> ready_at

    def _tick(self, ms: float) -> None:
        if hasattr(self.clock, "advance"):
            self.clock.advance(ms)  # type: ignore[attr-defined]

    def _wait_until(self, t: float) -> None:
        now = self.clock.now_ms()
        if t > now:
            self._tick(t - now)

    def resolve_app(self, app: str) -> str | None:
        self.calls.append(("resolve", app))
        if app not in self._resolved:
            self._tick(self.resolve_cost_ms)
            self._resolved.add(app)
        return f"C:/apps/{app}.exe" if app in self.installed else None

    def open_app(self, app: str, *, prewarm: bool = False) -> str | None:
        target = self.resolve_app(app)
        if not target:
            return None
        self.calls.append(("prewarm" if prewarm else "open", app))
        if app not in self.running and app not in self._launching:
            self._launching[app] = self.clock.now_ms() + self.cold_start_ms
        if prewarm:
            return target
        self.focus_app(app)
        return target

    def close_app(self, app: str) -> bool:
        self.calls.append(("close", app))
        if app in self._launching:
            del self._launching[app]
            return True
        if app in self.running:
            self.running.discard(app)
            if self.foreground == app:
                self.foreground = "desktop"
            return True
        return False

    def focus_app(self, app: str) -> bool:
        self.calls.append(("focus", app))
        if app in self._launching:
            ready = self._launching.pop(app)
            self._wait_until(ready)
            self.running.add(app)
            self.last_window_visible_at = ready
        elif app in self.running:
            self._tick(self.focus_cost_ms)
            self.last_window_visible_at = self.clock.now_ms()
        else:
            return False
        self.foreground = app
        return True

    def foreground_title(self) -> str:
        return self.foreground

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", x, y))

    def dispatch_keys(self, ops: list[KeyOp]) -> None:
        self.calls.append(("keys", tuple(ops)))
        self.typed.extend(ops)

    def move_file(self, src: str, dst: str) -> str:
        self.calls.append(("move", src, dst))
        return shutil.move(src, dst)


# --------------------------------------------------------------------------- context / receipts


@dataclass
class ActionContext:
    os: OSBackend
    ui: UIProvider
    clock: Clock = field(default_factory=MonotonicClock)
    events: list[tuple[str, float, dict]] = field(default_factory=list)

    def emit(self, name: str, **detail) -> None:
        self.events.append((name, self.clock.now_ms(), detail))


@dataclass
class Receipt:
    action: Action
    ok: bool
    t_start_ms: float
    t_end_ms: float
    detail: dict = field(default_factory=dict)
    undone: bool = False

    @property
    def duration_ms(self) -> float:
        return self.t_end_ms - self.t_start_ms


class Action(ABC):
    name: str = "action"
    reversible: bool = True
    speculative_safe: bool = False

    @abstractmethod
    def execute(self, ctx: ActionContext) -> Receipt: ...

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        return False

    def describe(self) -> str:
        return self.name

    def _receipt(self, ctx: ActionContext, t0: float, ok: bool, **detail) -> Receipt:
        return Receipt(self, ok, t0, ctx.clock.now_ms(), detail)


# --------------------------------------------------------------------------- concrete actions


@dataclass
class OpenApp(Action):
    """Open (or focus) an app. ``prewarm`` starts the launch during speech;
    ``execute`` on commit then only has to focus. If the speculation turns
    out wrong, ``abort`` closes what prewarm started."""

    app: str
    name: str = "open_app"
    reversible: bool = True
    speculative_safe: bool = True
    _prewarmed: bool = False

    def prewarm(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        target = ctx.os.open_app(self.app, prewarm=True)
        self._prewarmed = target is not None
        ctx.emit("prewarm", app=self.app, ok=self._prewarmed)
        return self._receipt(ctx, t0, self._prewarmed, prewarm=True, target=target)

    def abort(self, ctx: ActionContext) -> None:
        if self._prewarmed:
            ctx.os.close_app(self.app)
            ctx.emit("prewarm_abort", app=self.app)
        self._prewarmed = False

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        if ctx.os.focus_app(self.app):
            ctx.emit("ui_change", kind="focus", app=self.app,
                     visible_at=getattr(ctx.os, "last_window_visible_at", None))
            return self._receipt(ctx, t0, True, launched=self._prewarmed, prewarmed=self._prewarmed)
        target = ctx.os.open_app(self.app)
        ok = target is not None
        if ok:
            ctx.emit("ui_change", kind="launch", app=self.app,
                     visible_at=getattr(ctx.os, "last_window_visible_at", None))
        return self._receipt(ctx, t0, ok, launched=ok, prewarmed=self._prewarmed)

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        if receipt.detail.get("launched"):
            return ctx.os.close_app(self.app)
        return True

    def describe(self) -> str:
        return f"open {self.app}"


@dataclass
class FocusWindow(Action):
    app: str
    name: str = "focus_window"

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        prev = ctx.os.foreground_title()
        ok = ctx.os.focus_app(self.app)
        if ok:
            ctx.emit("ui_change", kind="focus", app=self.app)
        return self._receipt(ctx, t0, ok, previous=prev)

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        prev = receipt.detail.get("previous")
        return bool(prev) and ctx.os.focus_app(prev)

    def describe(self) -> str:
        return f"switch to {self.app}"


@dataclass
class TypeText(Action):
    text: str
    name: str = "type_text"

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        ctx.os.dispatch_keys([type_text(self.text)])
        ctx.emit("ui_change", kind="type", chars=len(self.text))
        return self._receipt(ctx, t0, True, chars=len(self.text))

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        ctx.os.dispatch_keys([backspace(receipt.detail["chars"])])
        return True

    def describe(self) -> str:
        return f"type {self.text!r}"


_INPUT_ROLES = {"edit", "combobox", "document"}


@dataclass
class ClickElement(Action):
    """Click a UI element named in speech. Clicking an *input* only moves
    focus (reversible); clicking anything else may trigger unknown behaviour,
    so it is irreversible and trust-gated."""

    query: str
    name: str = "click_element"
    roles: tuple[str, ...] | None = None
    reversible: bool = field(default=False)

    def __post_init__(self) -> None:
        if self.roles and set(self.roles) <= _INPUT_ROLES:
            self.reversible = True

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        tree: UITree = ctx.ui.snapshot()
        ctx.emit("grounding", nodes=len(tree.nodes), latency_ms=tree.latency_ms)
        m = find_element(tree, self.query, roles=self.roles)
        if not m:
            return self._receipt(ctx, t0, False, reason="no_match", query=self.query)
        x, y = m.node.center
        ctx.os.click(x, y)
        ctx.emit("ui_change", kind="click", target=m.node.name, score=m.score)
        return self._receipt(ctx, t0, True, target=m.node.name, score=m.score)

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        return self.reversible  # focus moves need no explicit undo

    def describe(self) -> str:
        return f"click {self.query!r}"


@dataclass
class MoveFile(Action):
    src: str
    dest_dir: str
    name: str = "move_file"

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        if not os.path.exists(self.src):
            return self._receipt(ctx, t0, False, reason="missing_src")
        Path(self.dest_dir).mkdir(parents=True, exist_ok=True)
        new_path = ctx.os.move_file(self.src, os.path.join(self.dest_dir, os.path.basename(self.src)))
        ctx.emit("ui_change", kind="move", dest=new_path)
        return self._receipt(ctx, t0, True, moved_to=new_path, original=self.src)

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        if not receipt.ok:
            return False
        ctx.os.move_file(receipt.detail["moved_to"], receipt.detail["original"])
        return True

    def describe(self) -> str:
        return f"move {os.path.basename(self.src)} to {self.dest_dir}"


@dataclass
class SendMessage(Action):
    """Focus the app, ground the composer, type the body. **Does not press
    Enter** - sending is the irreversible part (see ``PressSend``), so it is
    gated by the trust policy separately."""

    recipient: str
    body: str
    app: str = "slack"
    name: str = "send_message"
    reversible: bool = True

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        if (ctx.os.foreground_title() != self.app and not ctx.os.focus_app(self.app)
                and ctx.os.open_app(self.app) is None):
            return self._receipt(ctx, t0, False, reason="app_unavailable")
        tree = ctx.ui.snapshot()
        ctx.emit("grounding", nodes=len(tree.nodes), latency_ms=tree.latency_ms)
        conv = find_element(tree, self.recipient, roles=("listitem", "treeitem", "hyperlink"))
        if conv:
            ctx.os.click(*conv.node.center)
        composer = find_element(tree, "message box", roles=("edit", "document"))
        if composer and not composer.node.focused:
            ctx.os.click(*composer.node.center)
        ctx.os.dispatch_keys([type_text(self.body)])
        ctx.emit("ui_change", kind="type", chars=len(self.body), recipient=self.recipient)
        return self._receipt(ctx, t0, True, chars=len(self.body),
                             recipient_found=conv is not None)

    def undo(self, ctx: ActionContext, receipt: Receipt) -> bool:
        ctx.os.dispatch_keys([backspace(receipt.detail["chars"])])
        return True

    def describe(self) -> str:
        return f"message {self.recipient} on {self.app}: {self.body!r}"


@dataclass
class PressSend(Action):
    """The irreversible tail of SendMessage, split out so trust can gate it."""

    recipient: str
    name: str = "press_send"
    reversible: bool = False

    def execute(self, ctx: ActionContext) -> Receipt:
        t0 = ctx.clock.now_ms()
        ctx.os.dispatch_keys([KeyOp("key", "enter")])
        ctx.emit("ui_change", kind="send", recipient=self.recipient)
        return self._receipt(ctx, t0, True)

    def describe(self) -> str:
        return f"send to {self.recipient}"


# --------------------------------------------------------------------------- undo stack


class UndoStack:
    def __init__(self, ctx: ActionContext, max_depth: int = 50) -> None:
        self.ctx = ctx
        self._stack: list[Receipt] = []
        self.max_depth = max_depth

    def push(self, receipt: Receipt) -> None:
        if receipt.ok:
            self._stack.append(receipt)
            del self._stack[: -self.max_depth]

    def undo_last(self) -> Receipt | None:
        while self._stack:
            r = self._stack.pop()
            if r.action.reversible and r.action.undo(self.ctx, r):
                r.undone = True
                self.ctx.emit("undo", action=r.action.name)
                return r
        return None

    def undo_group(self, receipts: list[Receipt]) -> int:
        """Undo a batch (everything one utterance did), newest first."""
        n = 0
        for r in reversed(receipts):
            if r in self._stack:
                self._stack.remove(r)
            if r.ok and r.action.reversible and r.action.undo(self.ctx, r):
                r.undone = True
                n += 1
        if n:
            self.ctx.emit("undo", count=n)
        return n

    def __len__(self) -> int:
        return len(self._stack)


# --------------------------------------------------------------------------- trust


@dataclass
class TrustPolicy:
    """Per-action-class trust in [0, 1]. Reversible actions start trusted;
    irreversible ones must earn it: ten clean runs to reach preview, more to
    reach auto, and a single undo costs three runs' worth."""

    scores: dict[str, float] = field(default_factory=dict)
    gain: float = 0.1
    loss: float = 0.3
    preview_threshold: float = 0.7
    auto_threshold: float = 0.95
    path: str | None = None

    def score(self, action: Action) -> float:
        return self.scores.get(action.name, 1.0 if action.reversible else 0.0)

    def decide(self, action: Action) -> str:
        s = self.score(action)
        if action.reversible:
            return "auto"
        if s >= self.auto_threshold:
            return "auto"
        if s >= self.preview_threshold:
            return "preview"
        return "confirm"

    def record_success(self, action: Action) -> None:
        self.scores[action.name] = min(1.0, round(self.score(action) + self.gain, 3))
        self._save()

    def record_undo(self, action: Action) -> None:
        self.scores[action.name] = max(0.0, round(self.score(action) - self.loss, 3))
        self._save()

    def _save(self) -> None:
        if self.path:
            Path(self.path).write_text(json.dumps(self.scores, indent=2))

    @classmethod
    def load(cls, path: str) -> TrustPolicy:
        p = Path(path)
        scores = json.loads(p.read_text()) if p.exists() else {}
        return cls(scores=scores, path=path)
