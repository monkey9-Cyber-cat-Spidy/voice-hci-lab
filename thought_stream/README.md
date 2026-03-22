# thought_stream: Real-Time Disfluency Resolution and In-Place Keystroke Patching

## Abstract

Human speech is fundamentally disfluent. Natural spoken communication contains self-interruptions, false starts, filler vocalizations, and mid-utterance cognitive revisions (*"the deployment is ready... actually wait, make that delayed until 4 PM"*). Traditional voice dictation systems process speech through one of two suboptimal paradigms: verbatim insertion (which clobbers the active text buffer with conversational garbage and requires high human correction effort) or full-buffer destructive replacement (which destroys caret position, introduces visual screen flicker, and breaks in multi-line documents).

`thought_stream` introduces a streaming, sub-millisecond human-computer interaction (HCI) pipeline that resolves conversational disfluencies in real time and computes the minimal set of native operating system keystrokes needed to rewrite only the affected clause in-place. Across 162 evaluated speech utterances in VoiceHCI-Bench, `thought_stream` reduces human Correction Overhead Rate (COR) from 1.103 to 0.021 (a 98.1% reduction) with a 95th-percentile computational overhead of 0.08 ms per partial update.

```
+--------------------------------------------------------------------------------------------------+
|                                    THOUGHT-STREAM ARCHITECTURE                                   |
+--------------------------------------------------------------------------------------------------+
|  Partial Audio / ASR Stream                                                                      |
|       |                                                                                          |
|       v                                                                                          |
|  [ Filler Stripper ]              -> Drops "um", "uh", "er" without character offset drift       |
|       |                                                                                          |
|       v                                                                                          |
|  [ Meta-Command Parser ]          -> Converts "new line", "bullet" into private-use markers      |
|       |                              (\ue000 namespace) that act as immutable clause boundaries  |
|       v                                                                                          |
|  [ Structural Pivot Classifier ]  -> Hard vs Soft Pivots (Restart, Anchor, Complement)           |
|       |                                                                                          |
|       v                                                                                          |
|  [ Streaming Deferral Gate ]      -> Holds back trailing incomplete corrections to stop flicker  |
|       |                                                                                          |
|       v                                                                                          |
|  [ App Context Stylist ]          -> Enforces syntax rules (Slack vs Notion vs VS Code)          |
|       |                                                                                          |
|       v                                                                                          |
|  [ Costed Diff Patcher ]          -> Evaluates Prefix-Only vs Prefix+Suffix patch strategies    |
|       |                                                                                          |
|       v                                                                                          |
|  [ OS Keystroke Dispatcher ]      -> Native SendInput with KEYEVENTF_UNICODE hardware events     |
+--------------------------------------------------------------------------------------------------+
```

---

## 1. Problem Formulation

Let an incoming spoken utterance be represented as a sequence of streaming transcript tokens $T = (w_1, w_2, \dots, w_n)$ emitted by a continuous speech recognizer. In conversational speech, $T$ frequently diverges from the user's intended target text $T^*$. 

A disfluency consists of three contiguous spans:
1. **The Repaired Span ($I_r$)**: The original speech that the user wishes to retract or revise.
2. **The Interregnum / Pivot ($P$)**: The cue phrase or discourse marker signaling retraction (e.g. *"I mean"*, *"no wait"*, *"actually"*, *"scratch that"*).
3. **The Repair ($I_c$)**: The updated content intended to replace or modify $I_r$.

Traditional approaches either delay rendering until the speaker finishes (resulting in unacceptably high Time-to-First-Action of 5.4+ seconds) or eagerly render tokens verbatim, forcing the user to execute manual backspaces and cursor movements. 

Our objective is to compute a target representation $S_t = f(T_t)$ at each streaming step $t$, such that:
1. As $t \to n$, $S_t = T^*$.
2. The keystroke transition cost from the previous rendered buffer $S_{t-1}$ to $S_t$ is strictly minimized.
3. The internal engine compute latency $\tau_{\text{compute}} < 1.0\text{ ms}$.

---

## 2. Structural Pivot Resolution

Naive keyword matching on words like *"no"* or *"actually"* fails catastrophically in production:
- In *"there is no way"*, the word *"no"* is essential content, not a pivot.
- In *"it's actually fine"*, *"actually"* is an intensifying adverb, not a course correction.
- In *"notify the on-call"*, character-offset substrings can falsely match *"no"*.

To solve this without the latency and nondeterminism of heavy neural language models, `thought_stream` introduces a **two-tier structural pivot grammar**:

### 2.1 Hard Pivots (Unconditional Triggers)
Hard pivots represent explicit linguistic retraction markers that unambiguously signal an edit operation regardless of surrounding syntactic context:
- Patterns: `make that`, `change that to`, `I mean`, `no wait`, `scratch that`, `actually wait`.
- Action: Unconditionally triggers clause retraction or complement replacement.

### 2.2 Soft Pivots (Syntactically Gated Triggers)
Soft pivots consist of single discourse words (`no`, `actually`, `wait`, `sorry`, `rather`). A soft pivot only fires if the proposed repair structurally aligns with the preceding clause through one of three deterministic strategies:

1. **Restart Alignment**: The tokens following the pivot match the syntactic start of the preceding clause:
   - Spoken: *"send it to john... no, send it to jane"*
   - Resolution: Detects identical prefix *"send it to"*; retracts *"john"* and commits *"jane"*.
2. **Value Anchor Alignment**: The tokens following the pivot match a preposition or copula introducing a value (time, number, date, identifier):
   - Spoken: *"meet at four... no, at five"*
   - Resolution: Anchors on preposition *"at"*; swaps target value *"four"* for *"five"*.
3. **Complement Replacement**: The repair modifies a verb predicate:
   - Spoken: *"the deployment is ready... actually, delayed"*
   - Resolution: Binds to the copular verb *"is"*; replaces predicate adjective *"ready"* with *"delayed"*.

If a soft pivot fails structural alignment, the token is treated as legitimate content text, preserving phrases such as *"there is no problem"* and *"I actually agree"*.

---

## 3. Immutable Clause Markers vs Offset Bookkeeping

### Architectural Postmortem (Killed Idea 1)
In early prototypes, formatting directives (*"new line"*, *"bullet"*, *"period"*) were stored as integer character offsets into a raw string. 
When a subsequent retraction (*"scratch that"*) removed text earlier in the buffer, all trailing offsets became invalid, resulting in severe layout corruption (e.g., rendering `bullet` markers inside chopped words).

### The Solution: Private-Use Inline Boundary Markers
`thought_stream` converts spoken formatting commands directly into Unicode Private-Use Area characters (`\ue000` through `\ue003`) immediately upon intake:
- `\ue000`: Soft clause break / space normalizer
- `\ue001`: Hard newline
- `\ue002`: Bulleted list item marker
- `\ue003`: Sentence terminator (period)

Because these markers remain embedded in the token stream, they travel through the pivot resolution engine as native characters. When a retraction occurs, slicing tokens automatically updates formatting boundaries without integer tracking. Markers are translated into native app whitespace only during final keystroke emission.

---

## 4. Costed Diff Patcher & Streaming Deferral

Given the currently rendered text $A$ and the new target text $B$, the engine must transform $A$ into $B$ on the user's screen.

### 4.1 Dual Patch Strategy Evaluation
The engine calculates and costs two separate patch strategies:

1. **Prefix-Only Strategy (Backspace & Retype)**:
   - Find longest common prefix $LCP(A, B)$.
   - Delete suffix of $A$: emit $|A| - |LCP(A, B)|$ backspaces.
   - Type suffix of $B$: emit $|B| - |LCP(A, B)|$ character keystrokes.
   - Total Cost: $\text{Cost}_{\text{prefix}} = (|A| - |LCP|) + (|B| - |LCP|)$.

2. **Prefix + Suffix Strategy (Interior Surgical Edit)**:
   - Find longest common prefix $LCP(A, B)$ and longest common suffix $LCS(A, B)$ such that spans do not overlap.
   - Move caret left into edit position: emit $|LCS|$ left-arrow keypresses.
   - Backspace differing middle section: emit $|A| - |LCP| - |LCS|$ backspaces.
   - Type replacement middle section: emit $|B| - |LCP| - |LCS|$ characters.
   - Return caret to end of text: emit 1 `End` keypress.
   - Total Cost: $\text{Cost}_{\text{suffix}} = |LCS| + (|A| - |LCP| - |LCS|) + (|B| - |LCP| - |LCS|) + 1$.

The patcher evaluates both candidate sequences, verifies that both reach $B$ in simulation, and dispatches the lower-cost sequence.

### 4.2 Streaming Deferral (Anti-Flicker Gate)
On streaming partial transcripts, applying a pivot immediately when only one word of the correction has been transcribed often selects an incorrect structural anchor. 

`thought_stream` enforces a **streaming deferral window**:
- Trailing hard pivots are hidden until at least 2 words of correction text have arrived.
- Trailing soft pivots are deferred until 3 words have arrived.
- Trailing half-recognized tokens are held in a buffer.

This eliminates visible double-rewrites and reduced system rewrite ratios by 28% in empirical testing.

---

## 5. Native OS Integration (`user32.SendInput`)

For production desktop integration on Windows, `thought_stream/backends/windows_input.py` interfaces with native `SendInput` APIs using Python `ctypes`:
- **Unicode Injection**: Uses `KEYEVENTF_UNICODE` with `ord(ch)` in `KEYBDINPUT`, bypassing locale and keyboard layout mismatches.
- **Hardware Scan Codes**: Standard virtual keys (`VK_BACK`, `VK_LEFT`, `VK_END`, `VK_RETURN`) are explicitly resolved using `user32.MapVirtualKeyW(vk, 0)` so that native Windows edit controls do not reject synthetic keystrokes.
- **Anti-Coalescing Delay**: Batches keystrokes with microsecond inter-event pacing to prevent the Windows UI message queue from dropping rapid backspaces in high-concurrency applications.

---

## 6. Empirical Benchmark Results

Evaluated on the 162 dictation records in VoiceHCI-Bench:

| Metric | Verbatim Stream | Final Cleaned (Batch) | thought_stream | Improvement |
| :--- | :---: | :---: | :---: | :---: |
| **TTFA p50** | 499 ms | 5444 ms | **1005 ms** | **-4.4s vs Batch** |
| **TTFA p90** | 554 ms | 7437 ms | **1453 ms** | **-6.0s vs Batch** |
| **Tail Latency p50** | 1200 ms | 1600 ms | **1600 ms** | Deterministic |
| **Correction Overhead (COR)** | 1.103 | 0.929 | **0.021** | **98.1% lower effort** |
| **Intent Drift Rate** | 100.0% | 100.0% | **4.1%** | **95.9% less drift** |
| **Engine Compute p95** | 0.01 ms | 0.03 ms | **0.08 ms** | Sub-millisecond |

*(All residual drift is concentrated strictly within the adversarial `hard` evaluation set).*

---

## 7. Verification and Test Suite

The engine is validated by an automated regression suite:
- `tests/test_disfluency.py`: Hard and soft pivot grammar, negative content retention cases.
- `tests/test_commands_style.py`: Formatting boundary retention and multi-app styling.
- `tests/test_patcher.py`: 200-seed randomized fuzz testing asserting that patched buffers match target text.
- `tests/test_engine.py`: End-to-end streaming engine lifecycle verification.

Run test suite:
```bash
pytest tests/test_disfluency.py tests/test_commands_style.py tests/test_patcher.py tests/test_engine.py -v
```
