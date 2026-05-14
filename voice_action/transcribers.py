"""Transcript sources.

``ScriptedTranscriber`` turns a sentence into a realistic stream of partials
on a fake clock (word timings, optional recogniser self-revisions). It is the
backbone of the tests and of VoiceHCI-Bench.

``FasterWhisperStreamingTranscriber`` is the live microphone path. It is
import-guarded: ``pip install "wispr-hci-lab[audio]"``.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass, field

from hci_common.clock import Clock, FakeClock

from .events import TranscriptChunk


@dataclass
class ScriptedTranscriber:
    text: str
    clock: Clock = field(default_factory=FakeClock)
    ms_per_word: float = 380.0  # ~2.6 words/s conversational
    asr_lag_ms: float = 120.0  # recogniser delay behind audio
    final_lag_ms: float = 400.0  # endpointing silence before "final"
    revisions: dict[str, str] | None = None  # first-heard -> corrected (applied one update later)
    seed: int = 0

    def __iter__(self) -> Iterator[TranscriptChunk]:
        rng = random.Random(self.seed)
        words = self.text.split()
        heard: list[str] = []
        pending_fix: tuple[int, str] | None = None
        for i, w in enumerate(words):
            if hasattr(self.clock, "advance"):
                self.clock.advance(self.ms_per_word * rng.uniform(0.8, 1.2))  # type: ignore[attr-defined]
            if pending_fix:
                idx, fixed = pending_fix
                heard[idx] = fixed
                pending_fix = None
            # The script holds what the recogniser *first* hears; a revision
            # swaps in the corrected word one update later, like real ASR.
            if self.revisions and w.lower() in self.revisions:
                pending_fix = (i, self.revisions[w.lower()])
            heard.append(w)
            yield TranscriptChunk(" ".join(heard), self.clock.now_ms() + self.asr_lag_ms, False, i)
        if pending_fix:
            idx, fixed = pending_fix
            heard[idx] = fixed
        if hasattr(self.clock, "advance"):
            self.clock.advance(self.final_lag_ms)  # type: ignore[attr-defined]
        yield TranscriptChunk(" ".join(heard), self.clock.now_ms(), True, len(words))

    @property
    def speech_onset_ms(self) -> float:
        return 0.0


class FasterWhisperStreamingTranscriber:  # pragma: no cover - needs mic + model
    """Sliding-window streaming on top of faster-whisper.

    Every ``hop_ms`` the whole buffered utterance (up to ``window_s``) is
    re-transcribed; the result is emitted as a partial. When the RMS energy
    stays below ``silence_rms`` for ``endpoint_ms`` the partial becomes final
    and the buffer resets. Not the most efficient streaming scheme, but it
    is dependency-light and its revisions are exactly what the patcher is for.
    """

    def __init__(self, model_size: str = "base.en", device: str = "cpu", compute_type: str = "int8",
                 sample_rate: int = 16000, hop_ms: int = 400, window_s: float = 12.0,
                 endpoint_ms: int = 700, silence_rms: float = 0.01, clock: Clock | None = None):
        try:
            import numpy as np  # noqa: F401
            import sounddevice as sd  # noqa: F401
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError('pip install "wispr-hci-lab[audio]"') from exc
        from hci_common.clock import MonotonicClock

        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.sr = sample_rate
        self.hop_ms = hop_ms
        self.window = int(window_s * sample_rate)
        self.endpoint_ms = endpoint_ms
        self.silence_rms = silence_rms
        self.clock = clock or MonotonicClock()
        self.speech_onset_ms: float | None = None

    def __iter__(self) -> Iterator[TranscriptChunk]:
        import numpy as np
        import sounddevice as sd

        buf = np.zeros(0, dtype=np.float32)
        silent_ms = 0
        seq = 0
        last_text = ""
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32") as stream:
            while True:
                frames, _ = stream.read(int(self.sr * self.hop_ms / 1000))
                chunk = frames[:, 0]
                rms = float(np.sqrt(np.mean(chunk**2)))
                buf = np.concatenate([buf, chunk])[-self.window:]
                if rms < self.silence_rms:
                    silent_ms += self.hop_ms
                else:
                    silent_ms = 0
                    if self.speech_onset_ms is None:
                        self.speech_onset_ms = self.clock.now_ms()
                if self.speech_onset_ms is None:
                    buf = buf[-self.sr:]  # keep 1 s of pre-roll
                    continue
                segments, _ = self.model.transcribe(buf, beam_size=1, vad_filter=True,
                                                    without_timestamps=True)
                text = " ".join(s.text.strip() for s in segments).strip()
                final = silent_ms >= self.endpoint_ms and bool(text)
                if text and (text != last_text or final):
                    yield TranscriptChunk(text, self.clock.now_ms(), final, seq)
                    seq += 1
                    last_text = text
                if final:
                    buf = np.zeros(0, dtype=np.float32)
                    silent_ms = 0
                    last_text = ""
                    self.speech_onset_ms = None
