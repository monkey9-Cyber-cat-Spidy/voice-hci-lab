"""Keystroke operations: the lowest common denominator of OS text editing.

A ``KeyOp`` is something any platform can dispatch: type a string, press
Backspace N times, move the caret, or send a chord like ``ctrl+z``.
``apply_ops`` is a pure simulator used both by tests and by the benchmark's
Correction Overhead metric (how many keystrokes a human would need to fix a
system's output).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

OpKind = Literal["type", "backspace", "left", "right", "end", "key"]


@dataclass(frozen=True)
class KeyOp:
    kind: OpKind
    text: str = ""
    count: int = 1

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("count must be >= 0")
        if self.kind == "type" and self.count != 1:
            raise ValueError("'type' ops carry text, not a count")

    @property
    def cost(self) -> int:
        """Physical key presses this op represents."""
        if self.kind == "type":
            return len(self.text)
        return self.count


def type_text(text: str) -> KeyOp:
    return KeyOp("type", text=text)


def backspace(n: int) -> KeyOp:
    return KeyOp("backspace", count=n)


def move_left(n: int) -> KeyOp:
    return KeyOp("left", count=n)


def move_right(n: int) -> KeyOp:
    return KeyOp("right", count=n)


def end() -> KeyOp:
    return KeyOp("end")


def key(chord: str) -> KeyOp:
    return KeyOp("key", text=chord)


def keystroke_cost(ops: Iterable[KeyOp]) -> int:
    return sum(op.cost for op in ops)


def apply_ops(text: str, ops: Iterable[KeyOp], caret: int | None = None) -> str:
    """Simulate ``ops`` against ``text`` with the caret initially at ``caret``
    (default: end of text). Returns the resulting text.

    Chord ops (``key``) are ignored by the simulator except ``ctrl+a``+type,
    which we do not model; they are for real sinks only.
    """
    buf = list(text)
    pos = len(buf) if caret is None else max(0, min(caret, len(buf)))
    for op in ops:
        if op.kind == "type":
            buf[pos:pos] = list(op.text)
            pos += len(op.text)
        elif op.kind == "backspace":
            n = min(op.count, pos)
            del buf[pos - n : pos]
            pos -= n
        elif op.kind == "left":
            pos = max(0, pos - op.count)
        elif op.kind == "right":
            pos = min(len(buf), pos + op.count)
        elif op.kind == "end":
            pos = len(buf)
        elif op.kind == "key":
            continue
        else:  # pragma: no cover - exhaustive
            raise ValueError(f"unknown op kind {op.kind!r}")
    return "".join(buf)
