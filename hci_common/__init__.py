"""Shared primitives: clocks, keystroke operations, and text helpers.

Everything in here is dependency-free and OS-agnostic so that the three
projects (voice_action, thought_stream, voicehci_bench) can share one
vocabulary for *what a keystroke is* and *how time is measured*.
"""

from .clock import Clock, FakeClock, MonotonicClock
from .keystrokes import KeyOp, apply_ops, backspace, key, keystroke_cost, move_left, type_text
from .text import levenshtein, normalize_words, word_error_rate

__all__ = [
    "Clock",
    "FakeClock",
    "KeyOp",
    "MonotonicClock",
    "apply_ops",
    "backspace",
    "key",
    "keystroke_cost",
    "levenshtein",
    "move_left",
    "normalize_words",
    "type_text",
    "word_error_rate",
]
