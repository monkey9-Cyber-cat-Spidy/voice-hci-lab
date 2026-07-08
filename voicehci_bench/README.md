# voicehci_bench: Human-Centered Evaluation Suite for Voice Computer Interfaces

## Abstract

For over three decades, speech processing research has relied almost exclusively on Word Error Rate (WER) as its primary optimization objective. In modern agentic computing, however, WER is fundamentally disconnected from the human user experience: it treats all substitutions equally, fails to reward early perceptual feedback, ignores screen flicker, and completely obscures the cognitive friction of repairing conversational speech errors.

`voicehci_bench` introduces a rigorous, human-centered evaluation harness and metric suite designed specifically for voice-driven interaction. The benchmark measures **Time-to-First-Action (TTFA)**, **Correction Overhead Rate (COR)**, **Tail Latency**, **Intent Drift**, and **Rewrite Ratio** across 182 structured test records spanning 9 conversational categories. The suite is deterministic, requires no network calls, executes in under 0.5 seconds, and provides automated HTML Pareto visualization dashboards.

```
+---------------------------------------------------------------------------------------------------+
|                                  VOICEHCI-BENCH EVALUATION FRAMEWORK                              |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ 182 Test Records ]  -> clean, filler, pivot_restart, pivot_complement, scratch,                |
|                           meta, compound, hard (adversarial), action                              |
|       |                                                                                           |
|       v                                                                                           |
|  [ Scripted Recognizer ] -> FakeClock, word-level jitter, realistic ASR lag, endpointing silence  |
|       |                                                                                           |
|       v                                                                                           |
|  [ Pluggable Systems ] -> Evaluates verbatim-stream, final-cleaned, and thought-stream models     |
|       |                                                                                           |
|       v                                                                                           |
|  [ Metric Evaluator ]  -> Computes TTFA, Tail Latency, COR, Drift, and Rewrite Ratio              |
|       |                                                                                           |
|       v                                                                                           |
|  [ Output Artifacts ]  -> results/latest.json, results/REPORT.md, results/index.html              |
+---------------------------------------------------------------------------------------------------+
```

---

## 1. The Fallacy of Word Error Rate (WER) in Interactive Computing

Word Error Rate is defined as the minimum Levenshtein distance between reference tokens $R$ and hypothesis tokens $H$, normalized by reference length:
$$\text{WER} = \frac{S + D + I}{N}$$

In voice-driven human-computer interaction, WER fails in four fundamental dimensions:
1. **Asymmetric Error Severity**: A system that outputs *"meet at four"* when the speaker said *"meet at four... no, at five"* receives a low WER penalty (1 substitution), yet the functional impact is severe: an incorrect calendar invite is created.
2. **Temporal Blindness**: WER cannot distinguish between a system that displays text progressively with 500 ms TTFA versus a system that displays nothing for 6 seconds and outputs text in a single block.
3. **Punctuation and Formatting Invisibility**: Spoken meta-directives (*"new line"*, *"bullet"*) are discarded by standard text normalizers, obscuring layout errors.
4. **Correction Effort Mismatch**: If a streaming model flickers wildly or positions the caret incorrectly, the human user must spend significant physical effort fixing the output. WER measures none of this physical friction.

---

## 2. Formal Metric Definitions

`voicehci_bench` formalizes five complementary metrics capturing the latency, accuracy, and ergonomic cost of voice interaction:

### 2.1 Time-to-First-Action (TTFA)
The elapsed time from speech onset ($t_{\text{onset}}$) to the moment the first visible user-facing UI change lands on the display ($t_{\text{first\_ui}}$):
$$\text{TTFA} = t_{\text{first\_ui}} - t_{\text{onset}}$$
- In dictation: The moment the first character is injected into the focused control.
- In desktop actions: The moment the target window launches or receives input focus.

### 2.2 Tail Latency
The duration between when the speaker stops speaking ($t_{\text{speech\_end}}$) and when the system stops mutating the output buffer ($t_{\text{settled}}$):
$$\text{Latency}_{\text{tail}} = t_{\text{settled}} - t_{\text{speech\_end}}$$
This represents the idle time a user must wait before they can resume typing or proceed with their workflow.

### 2.3 Correction Overhead Rate (COR)
The physical effort required by a human user to transform the actual system output $O$ into the intended gold text $G$, normalized by the length of the gold text:
$$\text{COR} = \frac{\text{HumanEdits}(O, G)}{|G|}$$

#### Architectural Postmortem: The Human Edit Model (Killed Idea 5)
In our initial prototype, COR was calculated using the system's internal diff patcher (`compute_patch(O, G)`). However, because the diff patcher assumes the cursor is positioned at the end of the text, a missing capital letter at position 0 cost an entire buffer re-type: verbatim dictation scored COR 1.32 on perfectly clean sentences.

We replaced this with a realistic **Human Edit Model** using `difflib.SequenceMatcher`:
- For each contiguous differing span:
  - 1 navigation operation (mouse click or cursor navigation).
  - 1 keystroke per character deleted.
  - 1 keystroke per character inserted.
Under this model, verbatim clean text scores 0.08, matching empirical human keystroke logs.

### 2.4 Intent Drift
The probability that an abandoned, retracted, or corrected thought leaks into the final output:
$$\text{Drift} = \frac{1}{|D|} \sum_{d \in D} \mathbb{I}(\text{RetractedThoughtInOutput}(d))$$
For OS actions, drift measures whether an abandoned target application (e.g. Spotify when the user pivoted to Slack) was executed.

### 2.5 Rewrite Ratio
The total number of keystrokes dispatched by the system, divided by the character length of the gold string:
$$\text{Ratio}_{\text{rewrite}} = \frac{\text{TotalKeystrokesDispatched}}{|G|}$$
A ratio near 1.0 indicates clean, append-only insertion. A ratio significantly above 1.0 indicates excessive backspacing and visible screen flicker.

---

## 3. Dataset Taxonomy and Adversarial Suite

The benchmark dataset (`data/voicehci_bench_v1.jsonl`) contains 182 records across 9 distinct categories:

| Category | Count | Linguistic Characteristics | Example Utterance |
| :--- | :---: | :--- | :--- |
| **`clean`** | 20 | Fluent conversational speech | *"We are ready to deploy the updated authentication service."* |
| **`filler`** | 20 | Speech with vocalized hesitations | *"Um we need to uh verify the database migrations before launch."* |
| **`pivot_restart`** | 20 | Complete clause restarts | *"Send it to john at four... no, send it to jane at four."* |
| **`pivot_complement`** | 25 | Mid-stream predicate updates | *"The staging server is on hold... actually wait, make that running."* |
| **`scratch`** | 20 | Complete clause cancellations | *"Notify the team immediately, scratch that, wait for the postmortem."* |
| **`meta`** | 20 | Spoken punctuation and lists | *"Action items new line bullet test the fix new line bullet ping devops."* |
| **`compound`** | 25 | Multi-clause coordinated directives | *"Open slack and tell the team running late, then switch to vs code."* |
| **`hard`** | 12 | Syntactically ambiguous adversarial cases | *"Create a list, no, a dict of active user objects."* |
| **`action`** | 20 | OS application manipulation | *"Open terminal and run pytest."* |

---

## 4. The Adversarial "Hard" Category: A Commitment to Scientific Honesty

### Architectural Postmortem (Killed Idea 7)
It is common practice in AI benchmarks to write evaluation prompts that conform strictly to the author's heuristics, claiming a "100% success rate." We explicitly reject this practice.

The `hard` category contains 12 adversarial test cases specifically crafted to challenge the limits of rule-based syntactic grammars:
1. **Determiner-Led Noun Phrase Swaps**: *"a list, no, a dict of active users"*
2. **Bare Number Swaps (Without Prepositions)**: *"we need three, no, four reviewers on this PR"*
3. **Adjectives Inside Prepositional Phrases**: *"click the blue button, no, the green one"*

### Current Empirical Failure Rate
In current benchmark runs, `thought_stream` scores:
- **COR**: 0.280 on `hard` (vs 0.000 on standard categories).
- **Drift**: 33.3% on `hard` (failing 7 of 12 prompts).

This failure rate is intentional: it establishes the exact empirical boundary where rule heuristics fail, providing the rigorous baseline needed to justify a secondary slow-path neural re-rendering model.

---

## 5. Comparative Evaluation

Full evaluation results generated across 182 records using `FakeClock` with CRC32-seeded jitter (380 ms/word, 120 ms ASR lag, 400 ms endpoint silence):

```
+---------------------------------------------------------------------------------------------------------+
|                                    DICTATION SYSTEMS (n = 162)                                          |
+--------------------------+----------+----------+----------+---------+---------+---------+---------------+
| System                   | TTFA p50 | TTFA p90 | Tail p50 | COR     | WER     | Drift   | Compute p95   |
+--------------------------+----------+----------+----------+---------+---------+---------+---------------+
| verbatim-stream          |   499 ms |   554 ms |  1200 ms | 1.103   | 0.870   | 100.0%  | 0.01 ms       |
| final-cleaned (batch)    |  5444 ms |  7437 ms |  1600 ms | 0.929   | 0.808   | 100.0%  | 0.03 ms       |
| thought-stream           |  1005 ms |  1453 ms |  1600 ms | 0.021   | 0.021   |    4.1% | 0.08 ms       |
| thought-stream-final     |  5444 ms |  7437 ms |  1600 ms | 0.021   | 0.021   |    4.1% | 0.07 ms       |
+--------------------------+----------+----------+----------+---------+---------+---------+---------------+

+---------------------------------------------------------------------------------------------------------+
|                                      ACTION SYSTEMS (n = 20)                                            |
+--------------------------+----------+----------+----------+------------+-----------+---------+----------+
| System                   | TTFA p50 | TTFA p90 | Tail p50 | Intent Acc | Slot Acc  | Prewarm | Drift    |
+--------------------------+----------+----------+----------+------------+-----------+---------+----------+
| voice-action-serial      |  2308 ms |  4820 ms |  1030 ms |    1.00    |   1.00    |    0.0% |   0.0%   |
| voice-action-speculative |  2061 ms |  3621 ms |   870 ms |    1.00    |   1.00    |   60.0% |   0.0%   |
+--------------------------+----------+----------+----------+------------+-----------+---------+----------+
```

---

## 6. CLI Commands and Dashboard

```bash
# Execute benchmark runner and output summary report
python -m voicehci_bench.cli run

# Run specific systems
python -m voicehci_bench.cli run --systems thought-stream,verbatim-stream

# Launch local interactive Pareto and heat-table dashboard
python -m voicehci_bench.cli serve --port 8765
```

The interactive dashboard serves from `voicehci_bench/dashboard/index.html`, rendering client-side SVG Pareto charts and a comprehensive record explorer without external network dependencies.
