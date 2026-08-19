# tests: Automated Verification Suite and Continuous Regression Harness

## Abstract

Speech-driven human-computer interaction systems operate under extreme non-deterministic pressure: streaming speech recognizers emit incomplete tokens, phonetic misspellings, and out-of-order partial revisions. To ensure mathematical correctness, stability, and zero regressions across all interaction layers, this test suite enforces strict behavioral invariants through unit tests, property-based randomized fuzzing, and CI-gated benchmark thresholds.

The test suite contains **265 automated test cases** that execute in under 1 second.

---

## 1. Test Architecture and Taxonomy

The test directory is organized into modular suites mapping directly to system layers:

```
tests/
  +-- conftest.py                   -> Shared fixtures, synthetic clocks, mock UI trees
  +-- test_keystrokes.py            -> KeyOp grammar and apply_ops simulator invariants
  +-- test_disfluency.py            -> Hard vs soft pivot resolution and negative retention
  +-- test_commands_style.py        -> Formatting boundary markers and multi-app styling
  +-- test_patcher.py               -> Diff patcher cost functions and randomized fuzzing
  +-- test_engine.py                -> Streaming lifecycle and anti-flicker deferral
  +-- test_intent_grounding.py      -> Prefix grammar classification and UIA tree parsing
  +-- test_actions_speculation.py   -> Speculative pre-warming, rollbacks, and trust curves
  +-- test_cli.py                   -> CLI dispatchers, argument parsers, and trace outputs
  +-- test_bench.py                 -> CI Quality Gates across VoiceHCI-Bench
```

---

## 2. Invariant Specifications

### 2.1 Patcher Invariant (Property-Based Fuzzing)
In `tests/test_patcher.py`, a 200-seed property test generates pairs of random strings $(A, B)$ containing arbitrary prefixes, interior edits, and suffixes.
For every pair $(A, B)$:
1. The engine computes both the prefix-only and prefix-plus-suffix patch plans.
2. The simulator executes `apply_ops(A, plan.ops)`.
3. Invariant Assertion: $\text{apply\_ops}(A, \text{plan.ops}) \equiv B$.
4. Cost Invariant: $\text{plan.cost} \le \text{Cost}_{\text{naive\_retype}}$.

If an edit sequence fails to reach $B$ or produces an out-of-bounds caret position, the test halts immediately with the random seed.

### 2.2 Disfluency Non-Destruction Invariant (Negative Testing)
In `tests/test_disfluency.py`, negative assertions verify that content words resembling discourse markers are never mistakenly parsed as retractions:
- *"there is no way"* $\to$ Preserves *"there is no way"* (asserts 0 pivots triggered).
- *"it is actually fine"* $\to$ Preserves *"it is actually fine"*.
- *"notify the on call"* $\to$ Does not match *"no"* inside *"notify"*.
- *"no problem at all"* $\to$ Content preserved.

### 2.3 Speculative Rollback Invariant
In `tests/test_actions_speculation.py`:
- When a speaker begins *"open slack..."*, the pre-warming hook registers a running PID.
- When the speaker pivots to *"actually make that terminal"*, the test verifies:
  1. The Slack PID receives an immediate termination call.
  2. The Terminal executable is launched.
  3. No residual Slack process remains registered in active contexts.

---

## 3. Continuous Integration Quality Gates (`test_bench.py`)

`tests/test_bench.py` executes the entire 182-record VoiceHCI-Bench suite as an automated test. It enforces non-negotiable quality thresholds:

```python
# Extract from tests/test_bench.py
def test_full_benchmark_quality_gates():
    payload = run_benchmark()
    systems = {s["system"]: s for s in payload["systems"]}
    
    # 1. Thought-Stream Quality Gate:
    ts = systems["thought-stream"]
    assert ts["cor_mean"] < 0.05, f"COR regressed: {ts['cor_mean']}"
    assert ts["drift_rate"] < 0.05, f"Drift regressed: {ts['drift_rate']}"
    assert ts["ttfa_ms_median"] < 1200.0, f"TTFA regressed: {ts['ttfa_ms_median']} ms"
    assert ts["compute_ms_p95"] < 1.0, f"Compute exceeded 1ms budget: {ts['compute_ms_p95']} ms"
    
    # 2. Speculative Action Quality Gate:
    act = systems["voice-action-speculative"]
    assert act["intent_accuracy"] == 1.0, "Intent accuracy dropped below 100%"
    assert act["slot_accuracy"] == 1.0, "Slot accuracy dropped below 100%"
    assert act["prewarm_hit_rate"] >= 0.50, f"Prewarm hit rate fell: {act['prewarm_hit_rate']}"
```

If any heuristic change causes Correction Overhead or Intent Drift to regress on standard template categories, the test fails automatically.

---

## 4. Execution Commands

```bash
# Execute entire test suite
pytest

# Execute with verbose output and per-test timing
pytest -v --durations=10

# Execute only CI quality gate assertions
pytest tests/test_bench.py -v
```
