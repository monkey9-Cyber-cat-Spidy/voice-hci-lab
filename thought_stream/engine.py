"""ThoughtStreamEngine: streaming transcript in, surgical keystrokes out."""

from __future__ import annotations

from dataclasses import dataclass

from hci_common.clock import Clock, MonotonicClock
from hci_common.keystrokes import KeyOp

from .commands import apply_commands, extract_commands
from .disfluency import PivotEvent, resolve_pivots, strip_fillers
from .patcher import PatchPlan, compute_patch
from .sinks import KeystrokeSink, RecordingSink
from .style import AppContext, StyleProfile, format_for, resolve_style


@dataclass
class PatchResult:
    target: str
    plan: PatchPlan
    pivots: list[PivotEvent]
    latency_ms: float
    final: bool

    @property
    def ops(self) -> list[KeyOp]:
        return self.plan.ops


@dataclass
class EngineStats:
    updates: int = 0
    dispatches: int = 0
    keystrokes: int = 0
    pivots: int = 0
    max_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    first_dispatch_at_ms: float | None = None

    @property
    def mean_latency_ms(self) -> float:
        return self.total_latency_ms / self.updates if self.updates else 0.0


def render_target(raw: str, profile: StyleProfile, *, final: bool = True) -> tuple[str, list[PivotEvent]]:
    """Pure function: raw transcript -> text that should be on screen."""
    cleaned = strip_fillers(raw)
    marked = extract_commands(cleaned)
    resolved, pivots = resolve_pivots(marked, final=final)
    text = apply_commands(resolved, newline=profile.newline, bullet_prefix=profile.bullet_prefix)
    return format_for(text, profile), pivots


class ThoughtStreamEngine:
    """Keeps ``rendered`` (what is on screen) in sync with the evolving transcript.

    Call ``feed(partial, final=False)`` on every ASR update. Partials may
    revise earlier words; the engine does not care whether a change came from
    the speaker or the recognizer - it just patches.
    """

    def __init__(self, sink: KeystrokeSink | None = None, *, context: AppContext | None = None,
                 clock: Clock | None = None, word_aligned: bool = True,
                 allow_caret_moves: bool = True, commit_partials: bool = True) -> None:
        self.sink: KeystrokeSink = sink or RecordingSink()
        self.context = context or AppContext()
        self.profile = resolve_style(self.context)
        self.clock = clock or MonotonicClock()
        self.word_aligned = word_aligned
        self.allow_caret_moves = allow_caret_moves
        self.commit_partials = commit_partials
        self.rendered = ""
        self.stats = EngineStats()
        self.history: list[PatchResult] = []
        self._t0: float | None = None

    def set_context(self, context: AppContext) -> None:
        self.context = context
        self.profile = resolve_style(context)

    def mark_speech_onset(self) -> None:
        self._t0 = self.clock.now_ms()

    def feed(self, partial: str, *, final: bool = False) -> PatchResult:
        t_start = self.clock.now_ms()
        if self._t0 is None:
            self._t0 = t_start
        target, pivots = render_target(partial, self.profile, final=final)

        if not final and not self.commit_partials:
            plan = PatchPlan()
        else:
            if not final:
                # Hold back the trailing, possibly half-recognised word on
                # partials. The single biggest flicker reducer in streaming
                # dictation; the trailing period from style is also deferred.
                target = _stable_prefix(target)
            plan = compute_patch(self.rendered, target, word_aligned=self.word_aligned,
                                 allow_caret_moves=self.allow_caret_moves)
            if plan.ops:
                self.sink.dispatch(plan.ops)
                self.rendered = target
                self.stats.dispatches += 1
                self.stats.keystrokes += plan.cost
                if self.stats.first_dispatch_at_ms is None:
                    self.stats.first_dispatch_at_ms = self.clock.now_ms() - self._t0

        latency = self.clock.now_ms() - t_start
        self.stats.updates += 1
        self.stats.pivots += len(pivots)
        self.stats.total_latency_ms += latency
        self.stats.max_latency_ms = max(self.stats.max_latency_ms, latency)
        result = PatchResult(target=target, plan=plan, pivots=pivots, latency_ms=latency,
                             final=final)
        self.history.append(result)
        return result

    def reset(self) -> None:
        self.rendered = ""
        self.history.clear()
        self.stats = EngineStats()
        self._t0 = None


def _stable_prefix(text: str) -> str:
    """Drop a trailing partial word and any style-added trailing period."""
    t = text.rstrip(".")
    if not t:
        return ""
    if t[-1] in " \n":
        return t
    cut = max(t.rfind(" "), t.rfind("\n"))
    if cut <= 0:
        return ""
    return t[:cut]
