"""Keystroke sinks: where KeyOps go.

``RecordingSink`` is the in-memory simulator used by tests and the benchmark.
``WindowsSendInputSink`` drives the real OS caret through ``SendInput`` via
ctypes (no third-party dependency). Import of the Windows sink is lazy so the
engine stays usable on any platform.
"""

from __future__ import annotations

import sys
from typing import Protocol

from hci_common.keystrokes import KeyOp, apply_ops


class KeystrokeSink(Protocol):
    def dispatch(self, ops: list[KeyOp]) -> None: ...  # pragma: no cover - protocol


class RecordingSink:
    """Applies ops to an internal buffer and keeps a log."""

    def __init__(self, initial: str = "") -> None:
        self.text = initial
        self.log: list[KeyOp] = []
        self.dispatch_count = 0

    def dispatch(self, ops: list[KeyOp]) -> None:
        if not ops:
            return
        self.dispatch_count += 1
        self.log.extend(ops)
        self.text = apply_ops(self.text, ops)

    @property
    def total_keystrokes(self) -> int:
        return sum(op.cost for op in self.log)


def make_os_sink() -> KeystrokeSink:
    if sys.platform == "win32":
        from .backends.windows_input import WindowsSendInputSink

        return WindowsSendInputSink()
    raise RuntimeError(
        "No native sink for this platform yet. Use RecordingSink, or contribute a "
        "macOS CGEvent sink in thought_stream/backends/."
    )
