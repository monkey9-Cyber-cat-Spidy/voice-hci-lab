"""Injectable clocks.

Latency is the product in voice HCI, so every component takes a ``Clock``
instead of calling ``time`` directly. Tests use ``FakeClock`` to make
time-to-first-action assertions deterministic.
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> float:  # pragma: no cover - protocol
        """Milliseconds on a monotonic timeline."""
        ...


class MonotonicClock:
    def now_ms(self) -> float:
        return time.perf_counter() * 1000.0


class FakeClock:
    """A clock you advance by hand."""

    def __init__(self, start_ms: float = 0.0) -> None:
        self._t = float(start_ms)

    def now_ms(self) -> float:
        return self._t

    def advance(self, ms: float) -> None:
        if ms < 0:
            raise ValueError("cannot move a monotonic clock backwards")
        self._t += ms

    def set(self, ms: float) -> None:
        if ms < self._t:
            raise ValueError("cannot move a monotonic clock backwards")
        self._t = float(ms)
