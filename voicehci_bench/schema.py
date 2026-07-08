"""Record and result schemas (plain dataclasses, JSON-friendly)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class BenchRecord:
    id: str
    category: str  # clean | filler | pivot_restart | pivot_complement | scratch | meta | compound | action
    kind: str  # "dictation" | "action"
    spoken: str  # what the user says, verbatim, including disfluencies
    app: str = "Notion"
    expected_text: str = ""  # gold final text (dictation)
    expected_intent: str = ""  # gold intent (action)
    expected_slots: dict[str, str] = field(default_factory=dict)
    retracted_terms: list[str] = field(default_factory=list)  # must NOT appear
    required_terms: list[str] = field(default_factory=list)  # must appear
    asr_revisions: dict[str, str] = field(default_factory=dict)  # simulate mishear->fix
    difficulty: int = 1  # 1..3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> BenchRecord:
        return cls(**d)


@dataclass
class RecordResult:
    record_id: str
    system: str
    category: str
    kind: str
    output_text: str = ""
    ttfa_ms: float | None = None
    final_ms: float | None = None  # when the output stopped changing (dictation) / commit end
    speech_end_ms: float | None = None  # when the user stopped talking
    tail_latency_ms: float | None = None  # final_ms - speech_end_ms (perceived "done")
    correction_keystrokes: int = 0
    cor: float = 0.0  # correction overhead rate
    wer: float = 0.0
    drift: bool | None = None  # None when not applicable
    system_keystrokes: int = 0
    rewrite_ratio: float = 0.0
    updates: int = 0
    compute_ms_p50: float = 0.0
    compute_ms_p95: float = 0.0
    intent_correct: bool | None = None
    slots_correct: bool | None = None
    prewarm_hit: bool | None = None
    pending_confirm: bool | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SystemSummary:
    system: str
    n: int
    ttfa_ms_median: float | None
    ttfa_ms_p90: float | None
    tail_latency_ms_median: float | None
    cor_mean: float
    wer_mean: float
    drift_rate: float | None
    rewrite_ratio_mean: float
    compute_ms_p95: float
    intent_accuracy: float | None
    slot_accuracy: float | None
    prewarm_hit_rate: float | None
    by_category: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
