# hci_common: Foundational Primitives for Temporal Virtualization and Keystroke Semantics

## Abstract

A persistent challenge in evaluating voice-driven human-computer interaction (HCI) systems is non-determinism: variable network conditions, operating system scheduler jitter, audio hardware drift, and asynchronous thread preemption render wall-clock latency benchmarks irreproducible across machines.

`hci_common` establishes the formal foundational substrate for `thought_stream`, `voice_action`, and `voicehci_bench`. It introduces two core primitives:
1. **Deterministic Temporal Virtualization (`Clock`)**: An injectable, millisecond-accurate virtual clock interface enabling exact time-travel simulation without sleep delays or scheduler jitter.
2. **Discrete Keystroke Formalism (`KeyOp`)**: A standardized vocabulary of discrete operating system input events paired with an in-memory execution simulator (`apply_ops`) that validates edit invariants before physical hardware dispatch.

By decoupling timing and hardware dispatch from core logic, `hci_common` enables full-system property tests and benchmark suites to execute hundreds of speech interactions deterministically in less than 500 milliseconds.

---

## 1. Temporal Virtualization: `MonotonicClock` vs `FakeClock`

In real-time speech interaction, algorithms must measure two orthogonal temporal domains:
- **Perceptual Time**: The timeline perceived by the user (e.g. speech onset, pause duration, endpointing silence).
- **Execution Time**: The wall-clock CPU time spent calculating string diffs and intent trees.

`hci_common/clock.py` defines an explicit `Clock` protocol:

```python
class Clock(Protocol):
    def now_ms(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
```

### 1.1 `MonotonicClock` (Production Runtime)
Utilizes `time.monotonic()` scaled to floating-point milliseconds. It is strictly monotonic and unaffected by operating system system clock steps (NTP synchronization). Used exclusively in live desktop mode (`--live`) and live microphone streaming.

### 1.2 `FakeClock` (Deterministic Testing and Benchmarking)
Maintains an internal scalar state `self._now_ms: float = 0.0`. 
- `advance(ms: float)`: Moves the virtual timeline forward by exact increments without halting the CPU thread.
- `sleep(seconds: float)`: Advances internal time by `seconds * 1000.0` instantaneously.

#### Impact on Research Rigor
Because `FakeClock` controls all temporal perception in `voicehci_bench`, benchmark timelines reproduce with bit-level identity across different CPUs, operating systems, and CI runners.

---

## 2. Keystroke Grammar and the `KeyOp` Simulator

Rather than directly emitting hardware-level scancodes or window messages during intermediate calculation, all text editing in the monorepo is modeled as an abstract sequence of discrete `KeyOp` operations.

### 2.1 Formal Grammar of `KeyOp`
`hci_common/keystrokes.py` formalizes input operations into six orthogonal variants:

$$\text{KeyOp} \in \{ \text{type}(s), \text{backspace}(n), \text{left}(n), \text{right}(n), \text{end}(), \text{key}(c) \}$$

| Operation | Arguments | Semantic Invariant | Physical Cost |
| :--- | :--- | :--- | :---: |
| `type` | `text: str` | Appends or inserts string $s$ at active caret position | $|s|$ |
| `backspace` | `count: int` | Deletes $n$ characters immediately preceding the caret | $n$ |
| `left` | `count: int` | Moves the caret position leftward by $n$ code points | $n$ |
| `right` | `count: int` | Moves the caret position rightward by $n$ code points | $n$ |
| `end` | none | Jumps caret position to end of buffer ($\text{pos} = |S|$) | $1$ |
| `key` | `text: str` | Dispatches single hotkey or chord (e.g. `enter`, `ctrl+z`) | $1$ |

### 2.2 In-Memory Simulation (`apply_ops`)
Before any sequence of `KeyOp` operations is dispatched to the operating system, it can be evaluated against an in-memory buffer via `apply_ops(buffer: str, ops: list[KeyOp]) -> str`.

`apply_ops` simulates a single-line or multi-line text edit control:
1. Maintains text content $S$ and integer caret index $p \in [0, |S|]$.
2. On `backspace(k)`: Removes slice $S[p-k : p]$ and sets $p \leftarrow \max(0, p - k)$.
3. On `left(k)`: Sets $p \leftarrow \max(0, p - k)$.
4. On `end()`: Sets $p \leftarrow |S|$.
5. On `type(s)`: Inserts $s$ at index $p$ and advances $p \leftarrow p + |s|$.

This enables randomized fuzz testing (over 200 random seeds in `tests/test_patcher.py`) to formally verify that computed diff patches produce the expected target text before touching any real desktop applications.

---

## 3. Human Edit Distance and Text Metrics

`hci_common/text.py` provides linguistic and edit-distance functions that mirror human typing mechanics:
- **`normalize_words(text: str)`**: Strips non-standard punctuation, collapses whitespace, and lowercases tokens for robust semantic comparisons.
- **`human_edit_distance(actual: str, target: str)`**: Deconstructs string differences using `difflib.SequenceMatcher`. Groups contiguous deletion and insertion blocks to accurately quantify the physical human keystroke overhead required to correct errors.

---

## 4. Design Invariant: Zero External Dependencies

`hci_common` depends solely on Python standard libraries (`dataclasses`, `typing`, `difflib`, `time`, `re`). It contains no third-party imports, C-extensions, or platform-specific bindings. This guarantees that any core algorithm built on `hci_common` remains universally portable and capable of running in constrained, sandboxed, or embedded environments.
