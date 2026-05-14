"""Event types flowing through the agent."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranscriptChunk:
    """One ASR update. ``text`` is the *full* partial transcript so far."""

    text: str
    t_ms: float  # time on the agent clock when this update became available
    final: bool = False
    seq: int = 0


@dataclass
class TimelineEvent:
    name: str
    t_ms: float
    detail: dict = field(default_factory=dict)
