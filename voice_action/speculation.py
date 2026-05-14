"""Speculative execution on streaming intent.

    partial: "open sl"         -> hypothesis OPEN_APP (no app)      -> wait
    partial: "open slack"      -> OPEN_APP(slack) conf 0.95         -> PREWARM slack
    partial: "open slack and"  -> same key                          -> keep
    final:   "open slack and message john saying running late"
                               -> COMMIT: OpenApp reuses prewarm, SendMessage runs

If the hypothesis key changes mid-utterance ("open slack... no, open
spotify"), the stale prewarm is rolled back before the new one starts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hci_common.clock import Clock

from .actions import (
    Action,
    ActionContext,
    ClickElement,
    FocusWindow,
    MoveFile,
    OpenApp,
    PressSend,
    Receipt,
    SendMessage,
    TrustPolicy,
    TypeText,
    UndoStack,
)
from .intent import Intent, IntentHypothesis


@dataclass
class Plan:
    actions: list[Action]
    hypotheses: list[IntentHypothesis]


@dataclass
class CommitResult:
    receipts: list[Receipt] = field(default_factory=list)
    pending_confirm: list[Action] = field(default_factory=list)
    previews: list[Action] = field(default_factory=list)
    undone: bool = False
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.receipts)


def build_plan(hyps: list[IntentHypothesis], *, send_messages: bool = True,
               cwd_file: str | None = None) -> Plan:
    actions: list[Action] = []
    for h in hyps:
        s = h.slots
        if h.intent is Intent.OPEN_APP and "app" in s:
            actions.append(OpenApp(s["app"]))
        elif h.intent is Intent.FOCUS_WINDOW and "app" in s:
            actions.append(FocusWindow(s["app"]))
        elif h.intent is Intent.SEND_MESSAGE and "recipient" in s and "body" in s:
            app = s.get("app") or _infer_app(actions) or "slack"
            actions.append(SendMessage(s["recipient"], s["body"], app=app))
            if send_messages:
                actions.append(PressSend(s["recipient"]))
        elif h.intent is Intent.SEARCH_WEB and "query" in s:
            app = _infer_app(actions) or "chrome"
            if not any(isinstance(a, (OpenApp, FocusWindow)) and a.app == app for a in actions):
                actions.append(OpenApp(app))
            actions.append(ClickElement("address bar", roles=("edit", "combobox")))
            actions.append(TypeText(s["query"] + "\n"))
        elif h.intent is Intent.TYPE_TEXT and "text" in s:
            actions.append(TypeText(s["text"]))
        elif h.intent is Intent.MOVE_FILE and "dest" in s and cwd_file:
            actions.append(MoveFile(cwd_file, s["dest"]))
    return Plan(actions, hyps)


def _infer_app(actions: list[Action]) -> str | None:
    for a in reversed(actions):
        if isinstance(a, (OpenApp, FocusWindow)):
            return a.app
    return None


class SpeculativeExecutor:
    def __init__(self, ctx: ActionContext, *, trust: TrustPolicy | None = None,
                 undo: UndoStack | None = None, prewarm_threshold: float = 0.85,
                 enable_speculation: bool = True) -> None:
        self.ctx = ctx
        self.clock: Clock = ctx.clock
        self.trust = trust or TrustPolicy()
        self.undo = undo or UndoStack(ctx)
        self.prewarm_threshold = prewarm_threshold
        self.enable_speculation = enable_speculation
        self._spec_key: tuple | None = None
        self._spec_action: OpenApp | None = None
        self._spec_receipt: Receipt | None = None
        self.last_commit: CommitResult | None = None

    # -- speculation -----------------------------------------------------------
    def on_hypothesis(self, hyps: list[IntentHypothesis]) -> bool:
        """Returns True if a prewarm was started on this call."""
        if not self.enable_speculation or not hyps:
            return False
        h = hyps[0]
        if h.intent is Intent.CANCEL:
            self.abort()
            return False
        key = h.key()
        if h.intent not in (Intent.OPEN_APP, Intent.FOCUS_WINDOW, Intent.SEND_MESSAGE,
                            Intent.SEARCH_WEB):
            return False
        app = h.slots.get("app") or ("chrome" if h.intent is Intent.SEARCH_WEB else None)
        if h.confidence < self.prewarm_threshold or not app:
            return False
        if self._spec_key == key:
            return False
        if self._spec_key is not None:
            self.abort()
        action = OpenApp(app)
        if not action.speculative_safe:
            return False
        self._spec_key = key
        self._spec_action = action
        self._spec_receipt = action.prewarm(self.ctx)
        return True

    def abort(self) -> None:
        if self._spec_action and self._spec_receipt and self._spec_receipt.ok:
            self._spec_action.abort(self.ctx)
        self._spec_key = self._spec_action = self._spec_receipt = None

    # -- commit ----------------------------------------------------------------
    def commit(self, plan: Plan, *, confirm: bool = False) -> CommitResult:
        res = CommitResult()
        hyps = plan.hypotheses
        if hyps and hyps[0].intent is Intent.CANCEL:
            self.abort()
            res.cancelled = True
            self.last_commit = res
            return res
        if hyps and hyps[0].intent is Intent.UNDO:
            self.abort()
            r = self.undo.undo_last()
            res.undone = r is not None
            if r is not None:
                self.trust.record_undo(r.action)
            self.last_commit = res
            return res

        for action in plan.actions:
            # Reuse the prewarmed OpenApp when it matches.
            if (isinstance(action, OpenApp) and self._spec_action
                    and self._spec_action.app == action.app):
                action = self._spec_action
            decision = self.trust.decide(action)
            if decision == "confirm" and not confirm:
                res.pending_confirm.append(action)
                self.ctx.emit("needs_confirm", action=action.describe())
                break  # everything after an unconfirmed step waits too
            if decision == "preview":
                res.previews.append(action)
                self.ctx.emit("preview", action=action.describe())
            receipt = action.execute(self.ctx)
            res.receipts.append(receipt)
            self.undo.push(receipt)
            if receipt.ok:
                self.trust.record_success(action)
            else:
                self.ctx.emit("action_failed", action=action.describe(), **receipt.detail)
                break
        # A prewarm that the plan never used is a wrong guess: roll it back.
        if self._spec_action and not any(r.action is self._spec_action for r in res.receipts):
            self.abort()
        self._spec_key = self._spec_action = self._spec_receipt = None
        self.last_commit = res
        return res

    def undo_last_commit(self) -> int:
        if not self.last_commit:
            return 0
        n = self.undo.undo_group(self.last_commit.receipts)
        for r in self.last_commit.receipts:
            if r.undone:
                self.trust.record_undo(r.action)
        return n
