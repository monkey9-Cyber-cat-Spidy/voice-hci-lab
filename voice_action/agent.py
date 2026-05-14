"""VoiceActionAgent: transcript stream -> hypotheses -> speculation -> commit,
with a millisecond timeline for every utterance."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from hci_common.clock import Clock

from .actions import ActionContext, TrustPolicy, UndoStack
from .events import TranscriptChunk
from .intent import IntentHypothesis, StreamingIntentClassifier
from .speculation import CommitResult, Plan, SpeculativeExecutor, build_plan


@dataclass
class SessionTrace:
    transcript: str = ""
    speech_onset_ms: float = 0.0
    first_hypothesis_ms: float | None = None
    prewarm_ms: float | None = None
    final_transcript_ms: float | None = None
    commit_start_ms: float | None = None
    commit_end_ms: float | None = None
    first_ui_change_ms: float | None = None
    hypotheses: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    events: list[tuple[str, float, dict]] = field(default_factory=list)
    ok: bool = False
    pending_confirm: list[str] = field(default_factory=list)
    prewarm_hits: int = 0
    prewarm_aborts: int = 0

    @property
    def ttfa_ms(self) -> float | None:
        """Time-to-first-action: speech onset -> first visible UI change."""
        if self.first_ui_change_ms is None:
            return None
        return self.first_ui_change_ms - self.speech_onset_ms

    @property
    def commit_latency_ms(self) -> float | None:
        """Final transcript -> commit finished (what the user perceives as 'did it work')."""
        if self.commit_end_ms is None or self.final_transcript_ms is None:
            return None
        return self.commit_end_ms - self.final_transcript_ms

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ttfa_ms"] = self.ttfa_ms
        d["commit_latency_ms"] = self.commit_latency_ms
        return d


class VoiceActionAgent:
    def __init__(self, ctx: ActionContext, *, classifier: StreamingIntentClassifier | None = None,
                 trust: TrustPolicy | None = None, enable_speculation: bool = True,
                 send_messages: bool = True, prewarm_threshold: float = 0.85) -> None:
        self.ctx = ctx
        self.clock: Clock = ctx.clock
        self.classifier = classifier or StreamingIntentClassifier()
        self.trust = trust or TrustPolicy()
        self.undo = UndoStack(ctx)
        self.executor = SpeculativeExecutor(ctx, trust=self.trust, undo=self.undo,
                                            prewarm_threshold=prewarm_threshold,
                                            enable_speculation=enable_speculation)
        self.send_messages = send_messages
        self.cwd_file: str | None = None

    def run(self, chunks: Iterable[TranscriptChunk], *, speech_onset_ms: float | None = None,
            confirm: bool = False) -> SessionTrace:
        trace = SessionTrace(speech_onset_ms=self.clock.now_ms() if speech_onset_ms is None
                             else speech_onset_ms)
        start_events = len(self.ctx.events)
        hyps: list[IntentHypothesis] = []
        for chunk in chunks:
            # Model ASR delivery time: the agent cannot see a chunk before t_ms.
            if hasattr(self.clock, "set") and chunk.t_ms > self.clock.now_ms():
                self.clock.set(chunk.t_ms)  # type: ignore[attr-defined]
            hyps = self.classifier.classify(chunk.text, final=chunk.final)
            trace.hypotheses.append({"t_ms": self.clock.now_ms(), "text": chunk.text,
                                     "hyps": [(h.intent.value, h.confidence, dict(h.slots))
                                              for h in hyps]})
            if hyps and hyps[0].confidence > 0 and trace.first_hypothesis_ms is None:
                trace.first_hypothesis_ms = self.clock.now_ms()
            if not chunk.final:
                if self.executor.on_hypothesis(hyps) and trace.prewarm_ms is None:
                    trace.prewarm_ms = self.clock.now_ms()
                continue
            trace.transcript = chunk.text
            trace.final_transcript_ms = self.clock.now_ms()
            plan: Plan = build_plan(hyps, send_messages=self.send_messages, cwd_file=self.cwd_file)
            trace.actions = [a.describe() for a in plan.actions]
            trace.commit_start_ms = self.clock.now_ms()
            result: CommitResult = self.executor.commit(plan, confirm=confirm)
            trace.commit_end_ms = self.clock.now_ms()
            trace.ok = result.ok and not result.pending_confirm
            trace.pending_confirm = [a.describe() for a in result.pending_confirm]
            trace.prewarm_hits = sum(1 for r in result.receipts if r.detail.get("prewarmed"))
        trace.events = self.ctx.events[start_events:]
        for name, t, detail in trace.events:
            if name == "ui_change" and trace.first_ui_change_ms is None:
                visible = detail.get("visible_at")
                trace.first_ui_change_ms = visible if visible is not None else t
            if name == "prewarm_abort":
                trace.prewarm_aborts += 1
        return trace

    def undo_last(self) -> int:
        return self.executor.undo_last_commit()
