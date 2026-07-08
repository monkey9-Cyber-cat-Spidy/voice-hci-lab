"""Systems under test.

Dictation systems consume ``TranscriptChunk`` streams and produce text through
a ``RecordingSink`` (so keystrokes, TTFA and rewrite ratio are observable).
Action systems run the voice_action agent against a mock desktop.

Baselines are deliberately simple so the deltas are interpretable:

* ``verbatim-stream``  - type each new word as it arrives, no cleaning.
* ``final-cleaned``    - wait for the final transcript, strip fillers, type once.
* ``thought-stream``   - the real engine, patching on partials.
* ``thought-stream-final`` - the real engine, but only on the final transcript
  (isolates the streaming contribution to TTFA / rewrite cost).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from hci_common.clock import FakeClock
from thought_stream.disfluency import strip_fillers
from thought_stream.engine import ThoughtStreamEngine
from thought_stream.sinks import RecordingSink
from thought_stream.style import AppContext, format_for, resolve_style
from voice_action.actions import ActionContext, MockOSBackend, TrustPolicy
from voice_action.agent import SessionTrace, VoiceActionAgent
from voice_action.events import TranscriptChunk
from voice_action.grounding import MockUIProvider, UINode, UITree

from .schema import BenchRecord


@dataclass
class DictationOutput:
    text: str
    first_output_ms: float | None
    final_ms: float | None
    system_keystrokes: int
    updates: int
    compute_ms: list[float] = field(default_factory=list)


class DictationSystem(Protocol):  # pragma: no cover - protocol
    name: str

    def run(self, record: BenchRecord, chunks: Iterable[TranscriptChunk],
            clock: FakeClock) -> DictationOutput: ...


def _deliver(chunk: TranscriptChunk, clock: FakeClock) -> None:
    if chunk.t_ms > clock.now_ms():
        clock.set(chunk.t_ms)


class VerbatimStream:
    name = "verbatim-stream"

    def run(self, record, chunks, clock):
        sink = RecordingSink()
        first = None
        compute: list[float] = []
        updates = 0
        last_words: list[str] = []
        final_ms = None
        for ch in chunks:
            _deliver(ch, clock)
            t = time.perf_counter()
            words = ch.text.split()
            # type only words that are new or changed (naive: from first diff)
            k = 0
            while k < min(len(words), len(last_words)) and words[k] == last_words[k]:
                k += 1
            from hci_common.keystrokes import backspace, type_text

            ops = []
            if k < len(last_words):
                ops.append(backspace(len(" ".join(last_words)) - len(" ".join(last_words[:k]))))
            new = " ".join(words[k:])
            if new:
                ops.append(type_text((" " if k else "") + new))
            if ops:
                sink.dispatch(ops)
                if first is None:
                    first = clock.now_ms()
                final_ms = clock.now_ms()
            last_words = words
            compute.append((time.perf_counter() - t) * 1000)
            updates += 1
        return DictationOutput(sink.text, first, final_ms, sink.total_keystrokes, updates, compute)


class FinalCleaned:
    name = "final-cleaned"

    def run(self, record, chunks, clock):
        sink = RecordingSink()
        compute: list[float] = []
        updates = 0
        first = final_ms = None
        profile = resolve_style(AppContext(record.app))
        for ch in chunks:
            _deliver(ch, clock)
            updates += 1
            if not ch.final:
                continue
            t = time.perf_counter()
            text = format_for(strip_fillers(ch.text), profile)
            from hci_common.keystrokes import type_text

            sink.dispatch([type_text(text)])
            compute.append((time.perf_counter() - t) * 1000)
            first = final_ms = clock.now_ms()
        return DictationOutput(sink.text, first, final_ms, sink.total_keystrokes, updates, compute)


class ThoughtStreamSystem:
    def __init__(self, streaming: bool = True, word_aligned: bool = True, caret_moves: bool = True,
                 name: str | None = None):
        self.streaming = streaming
        self.word_aligned = word_aligned
        self.caret_moves = caret_moves
        self.name = name or ("thought-stream" if streaming else "thought-stream-final")

    def run(self, record, chunks, clock):
        sink = RecordingSink()
        eng = ThoughtStreamEngine(sink, context=AppContext(record.app), clock=clock,
                                  word_aligned=self.word_aligned,
                                  allow_caret_moves=self.caret_moves,
                                  commit_partials=self.streaming)
        eng.mark_speech_onset()
        compute: list[float] = []
        first = final_ms = None
        for ch in chunks:
            _deliver(ch, clock)
            t = time.perf_counter()
            r = eng.feed(ch.text, final=ch.final)
            compute.append((time.perf_counter() - t) * 1000)
            if r.ops:
                if first is None:
                    first = clock.now_ms()
                final_ms = clock.now_ms()
        return DictationOutput(sink.text, first, final_ms, sink.total_keystrokes,
                               eng.stats.updates, compute)


# --------------------------------------------------------------------------- actions


def _desktop_tree() -> UITree:
    return UITree("slack", "Slack", [
        UINode("treeitem", "john", (10, 100, 200, 120)),
        UINode("treeitem", "jane", (10, 120, 200, 140)),
        UINode("treeitem", "priya", (10, 140, 200, 160)),
        UINode("treeitem", "marcus", (10, 160, 200, 180)),
        UINode("edit", "Message", (220, 700, 1200, 740), focused=True),
        UINode("edit", "Address and search bar", (300, 10, 900, 40)),
        UINode("button", "Send", (1210, 705, 1250, 735)),
    ])


@dataclass
class ActionOutput:
    trace: SessionTrace
    intent: str
    slots: dict
    prewarm_hit: bool
    pending_confirm: bool
    compute_ms: list[float]


class VoiceActionSystem:
    def __init__(self, speculation: bool = True, name: str | None = None):
        self.speculation = speculation
        self.name = name or ("voice-action-speculative" if speculation else "voice-action-serial")

    def run(self, record: BenchRecord, chunks: Iterable[TranscriptChunk],
            clock: FakeClock) -> ActionOutput:
        os_b = MockOSBackend(clock=clock, running={"chrome", "vscode", "spotify"})
        ctx = ActionContext(os=os_b, ui=MockUIProvider(_desktop_tree()), clock=clock)
        agent = VoiceActionAgent(ctx, trust=TrustPolicy(), enable_speculation=self.speculation,
                                 send_messages=True)
        compute: list[float] = []
        t = time.perf_counter()
        trace = agent.run(chunks, speech_onset_ms=0.0)
        compute.append((time.perf_counter() - t) * 1000)
        last = trace.hypotheses[-1]["hyps"] if trace.hypotheses else []
        intent = last[0][0] if last else "unknown"
        slots = last[0][2] if last else {}
        return ActionOutput(trace, intent, slots, trace.prewarm_hits > 0,
                            bool(trace.pending_confirm), compute)


DICTATION_SYSTEMS: dict[str, DictationSystem] = {
    "verbatim-stream": VerbatimStream(),
    "final-cleaned": FinalCleaned(),
    "thought-stream": ThoughtStreamSystem(streaming=True),
    "thought-stream-final": ThoughtStreamSystem(streaming=False),
    "thought-stream-charaligned": ThoughtStreamSystem(streaming=True, word_aligned=False,
                                                      name="thought-stream-charaligned"),
}
ACTION_SYSTEMS: dict[str, VoiceActionSystem] = {
    "voice-action-speculative": VoiceActionSystem(True),
    "voice-action-serial": VoiceActionSystem(False),
}
