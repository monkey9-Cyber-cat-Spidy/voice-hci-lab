# wispr-hci-lab

Three open experiments in speech-driven computer use, built as one Python monorepo with a
shared vocabulary for *what a keystroke is* and *how time is measured*:

| | Project | One-line claim | Status |
|---|---|---|---|
| 1 | **`voice_action/`** Speculative voice-to-action | Start acting on the first verb, not the last word. Pre-warm the target app during speech, commit on the final transcript, roll back if the guess was wrong. Every action carries its own undo; irreversible ones must earn trust. | Core + mock desktop tested; Windows UIA/SendInput backends written, live mic path behind an extra |
| 2 | **`thought_stream/`** Streaming disfluency & in-place patcher | Resolve "scratch that" / "no wait, make that…" as the user speaks, then rewrite *only the affected span* with the cheapest keystroke sequence. ASR self-corrections and human self-corrections share one code path. | Core complete, sub-millisecond per update |
| 3 | **`voicehci_bench/`** VoiceHCI-Bench | Measure what WER does not: time-to-first-action, correction overhead, intent drift under disfluency, rewrite ratio. 182 synthetic prompts, pluggable systems, static dashboard. | Runs in 0.5 s, CI-gated |

Everything runs on any OS with the standard library only. Native backends (Windows UI Automation,
`SendInput`) and the live microphone path (`faster-whisper`) are optional extras.

```bash
pip install -e ".[dev]"
pytest                          # 265 tests, < 1 s
thought-stream demo -v          # watch the in-place patcher work on three utterances
voice-action demo               # millisecond timelines, speculation on vs off
voicehci-bench run              # results/latest.json + results/REPORT.md
voicehci-bench serve            # dashboard at http://localhost:8765
```

---

## Project 1: speculative voice-to-action (`voice_action/`)

The latency of a voice command is mostly *waiting*: for the speaker to finish, for the
endpointer to fire, for the transcript to finalise. The pipeline here overlaps each wait
with useful work.

```
partial  "open sl"          -> hypothesis OPEN_APP (no app yet)            -> wait
partial  "open slack"       -> OPEN_APP(slack) conf 0.95                   -> PREWARM slack (launch starts)
partial  "open slack and"   -> same hypothesis key                         -> keep
final    "open slack and message john saying running late"
                            -> COMMIT: OpenApp reuses the running process, SendMessage grounds the
                               composer in the accessibility tree and types; PressSend is held
                               for confirmation until trust is earned
```

* **`intent.py`** - a grammar-based streaming prefix classifier. Confidence rises as slots fill
  (verb only 0.35, verb + resolved app 0.95). Compound commands split on "and / then".
  Fuzzy app resolution absorbs ASR mishears (`"open slag"` -> Slack). The transcript is run
  through Thought-Stream's pivot resolver first, so `"open spotify, no wait, open slack"`
  aborts the Spotify speculation instead of executing it.
* **`speculation.py`** - `SpeculativeExecutor` pre-warms on a hypothesis above a threshold,
  tracks the hypothesis *key*, and rolls back the pre-warm (closing what it launched) if the
  key changes or the committed plan never uses it.
* **`grounding.py`** - the focused window's accessibility tree, not a screenshot. `find_element`
  resolves spoken targets ("the message box", "send button") with role hints + fuzzy names.
  The Windows provider (`backends/windows_uia.py`) walks breadth-first under a hard 15 ms budget.
* **`actions.py`** - every `Action` declares `reversible` and `speculative_safe`, returns a
  `Receipt` that its `undo` consumes, and goes through `TrustPolicy`: reversible actions are
  `auto`; irreversible ones (`PressSend`, clicking an arbitrary button) start at `confirm`, reach
  `preview` after ~7 uncontested runs and `auto` after ~10, and lose three runs' worth on a
  single undo. `MoveFile` is tested against the real filesystem and undone.
* **`agent.py`** - records a timeline per utterance: first hypothesis, pre-warm, final
  transcript, first visible UI change (TTFA), commit end.

Measured on the mock desktop (380 ms/word, 120 ms ASR lag, 400 ms endpoint, 350 ms cold start):

```
"open slack and message john saying running late, start without me"
                      speculation ON        speculation OFF
first hypothesis       552 ms                552 ms
prewarm               1132 ms                   -
final transcript      6054 ms               6014 ms
first UI change       1482 ms  <- TTFA      6404 ms
commit latency           0 ms                390 ms
```

With speculation the Slack window is on screen 1.5 s into a 6 s utterance. Without it the user
waits for the cold start *after* they stop talking.

## Project 2: Thought-Stream (`thought_stream/`)

```
raw partial transcript
  -> strip fillers                   um / uh / er
  -> extract meta-commands           "new line", "period", "delete the last sentence" -> inline markers
  -> resolve pivots                  "scratch that", "no wait, make that X", "I mean X"
  -> apply markers                   layout, punctuation, bullets
  -> style for the active app        Slack vs Notion vs VS Code
  -> minimal keystroke patch         common prefix (+ optional common suffix with caret moves)
  -> KeystrokeSink                   RecordingSink (tests/bench) or WindowsSendInputSink
```

Key design points, each of which exists because the naive version failed (see the log below):

* **Pivots come in two classes.** *Hard* pivots ("make that", "change that to", "I mean",
  "no wait", "scratch that") always fire. *Soft* ones ("no", "actually", "wait", "sorry",
  "rather") fire only if the correction aligns to the last clause by a structural strategy:
  **restart** ("send it to john … no, send it to jane"), **anchor** ("to john at four … no wait,
  to jane"), or **complement** ("the deployment is ready … make that delayed"). Otherwise the
  word is content, so "there is no way" and "it's actually fine" survive.
* **Complement anchoring prefers the verb copula** ("is on hold" -> "is merged") unless the
  last preposition introduces a *value* (number, weekday, time): "at four" -> "at five".
* **Meta-commands become inline markers** that double as clause boundaries, so "…new line,
  bullet notify the on-call, scratch that" retracts only the last bullet and no offsets drift.
* **Streaming deferral.** On partials, a trailing pivot whose correction is still short is
  hidden rather than applied; applying early picks the wrong span and causes a visible double
  rewrite. The trailing half-recognised word is also held back.
* **Two patch strategies are costed and the cheaper wins.** Prefix-only (backspace + retype)
  versus prefix+suffix (arrow-left, backspace the middle, type, End). The patcher asserts both
  reach the target on every call; a 200-seed property test does too. Word alignment keeps the
  rewrite from starting mid-word, at a measured keystroke cost the bench reports.

```
$ thought-stream text "hey team um the deployment is ready actually wait make that delayed until 4 PM" --app Slack
Hey team the deployment is delayed until 4 PM
  pivot[replace/complement] 'actually wait make that': 'ready' -> 'delayed until 4 PM'

$ thought-stream text "action items new line bullet ship the patch new line bullet notify the on call scratch that notify support period"
Action items
- Ship the patch
- Notify support.
```

## Project 3: VoiceHCI-Bench (`voicehci_bench/`)

| Metric | Definition |
|---|---|
| **TTFA** | speech onset -> first visible UI change (first keystroke for dictation, first window/focus/click for actions) |
| **Tail latency** | user stops talking -> output stops changing |
| **COR** (correction overhead rate) | keystrokes a human needs to turn the output into the intended text, per intended character. Human edit model: one navigation press per edit cluster + one per deleted/inserted char |
| **Drift** | on utterances with a retraction: did the retracted thought leak into the output, or the corrected one go missing? For actions: was the retracted app acted on? |
| **Rewrite ratio** | keystrokes the *system* dispatched per intended character (flicker proxy for streaming) |
| plus | WER, per-update compute p50/p95, intent + slot accuracy, pre-warm hit rate |

The dataset (`data/voicehci_bench_v1.jsonl`, 182 records, regenerated deterministically by
`voicehci-bench dataset`) covers: clean, filler, pivot_restart, pivot_complement, scratch, meta,
compound, **hard** (adversarial corrections the current rules are expected to miss), and action.
Transcripts are streamed through a scripted recogniser on a fake clock (380 ms/word, 120 ms lag,
400 ms endpoint, optional mid-stream self-revisions) so every number is reproducible.

Results from `voicehci-bench run` on this machine (full table in `results/REPORT.md`):

| system | TTFA p50 | TTFA p90 | tail p50 | COR | WER | drift | rewrite | compute p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| verbatim-stream (baseline) | 499 ms | 554 | 1200 | 1.10 | 0.87 | 100% | 1.85 | 0.01 ms |
| final-cleaned (baseline) | 5444 ms | 7437 | 1600 | 0.93 | 0.81 | 100% | 1.84 | 0.03 ms |
| **thought-stream** | **1005 ms** | 1453 | 1600 | **0.021** | 0.021 | **4.1%** | 1.84 | 0.37 ms |
| thought-stream-final | 5444 ms | 7437 | 1600 | 0.021 | 0.021 | 4.1% | 1.01 | 0.29 ms |

| action system | TTFA p50 | TTFA p90 | tail p50 | intent acc | slot acc | prewarm hit | drift |
|---|---:|---:|---:|---:|---:|---:|---:|
| voice-action-serial | 2308 ms | 4820 | 1030 | 1.00 | 1.00 | - | 0% |
| **voice-action-speculative** | **2061 ms** | **3621** | **870** | 1.00 | 1.00 | 60% | 0% |

Timing columns are deterministic (fake clock, CRC-seeded word jitter) and reproduce exactly across
runs; the compute column is wall-clock on the machine that ran it.

Read these with the caveats in the next section. The `hard` category is where it gets honest:
thought-stream scores COR 0.28 and drift 33% there, failing 7 of 12 prompts.

---

## Experiments & architectural decisions (what we killed)

Each entry is a decision made *in this codebase*, with the evidence that forced it. Where a
number is quoted it came from running this repo; where a decision rests on reasoning rather
than measurement, it says so.

**1. Killed: character-offset bookkeeping for meta-commands.**
*Hypothesis:* record "new line" / "bullet" / "period" as positions in the content string and
apply them after pivot resolution.
*Evidence:* the first demo run rendered `"• • Tify suppor t."` for the action-items utterance.
Retractions shrink the text, so every offset after a retraction pointed into the wrong place.
*Decision:* commands become inline private-use markers carried *through* pivot resolution and
treated as clause boundaries. Offsets cannot drift because there are none.

**2. Killed: bare "no" / "actually" as unconditional pivots.**
*Hypothesis:* any pivot word triggers a correction.
*Evidence:* the regex matched "no" inside "notify"; "there is no way" and "it's actually fine"
were mangled into nonsense corrections.
*Decision:* word-boundary matching, plus a hard/soft split: soft pivots fire only when the
correction aligns structurally (restart / anchor / complement). Five negative cases are pinned
in `tests/test_disfluency.py`.

**3. Killed: applying pivots eagerly on streaming partials.**
*Hypothesis:* resolve the pivot on every partial so the screen updates as early as possible.
*Evidence:* on "send it to john at four, no wait, to jane at four" the one-word correction
"to" anchored early, deleted "to john at four", then the engine re-typed it piece by piece:
55 keystrokes. Deferring a trailing pivot until its correction has two words (three for soft
pivots): 49 keystrokes, identical final text, one visible rewrite instead of two.
*Decision:* deferral is on; `resolve_pivots(final=False)` hides the forming correction.

**4. Killed: "last preposition wins" complement anchoring.**
*Hypothesis:* a correction after "make that / I mean" replaces whatever follows the last
copula or preposition.
*Evidence:* "the demo is on hold, I mean merged" -> "the demo is on merged" (4 of 25
complement records in the first bench run). But "meet at four, I mean five" needs the
preposition anchor.
*Decision:* prefer the verb copula unless the word after the preposition looks like a value
(number, weekday, time). Both cases pass; the residual failure class is in the `hard` set.

**5. Killed: using the product patcher as the correction-overhead metric.**
*Hypothesis:* COR = cost of `compute_patch(output, gold)`, since that is the minimal keystroke
sequence.
*Evidence:* with the caret at the end, a missing capital letter at position 0 costs a full
retype under that model: verbatim dictation scored COR 1.32 on *clean* sentences, which no
human would experience.
*Decision:* a human edit model (one navigation press per differing span, plus one per
deleted/inserted character). Verbatim's clean COR fell to 0.08, the right order of magnitude.

**6. Killed: pre-warm = resolve the executable only.**
*Hypothesis:* speculation can stay invisible by only resolving the launch target during speech.
*Evidence:* the first timeline showed speculation saving 40 ms of a 410 ms commit. The cold
start, the thing users actually wait for, still happened after they stopped talking.
*Decision:* pre-warm starts the launch (modelled asynchronously, like a real `Popen`), and a
wrong guess closes it. TTFA on the Slack utterance moved from 6404 ms to 1482 ms; the cost is
that a wrong guess is briefly visible, which is why the executor aborts on hypothesis change and
`PressSend` is still trust-gated.

**7. Killed: a perfect benchmark score.**
*Hypothesis:* 0.000 COR across every category means the engine works.
*Evidence:* the v1 templates were written by the same person who wrote the rules. That is a
regression suite, not a generalisation claim.
*Decision:* a `hard` category of 12 adversarial corrections was added *expecting* failures;
7 fail. The CI gate asserts perfection only on the template categories and reports `hard`.

**8. Not built, by design: screenshot + vision-model UI grounding.**
*Reasoning (not measured in this repo):* an accessibility-tree snapshot of the focused window is
deterministic, carries exact bounding boxes and control roles, needs no network, and fits a
single-digit-millisecond budget; a vision round trip does none of those. The UIA provider
enforces a 15 ms budget and returns a partial tree rather than blowing it. What would reverse
this: apps that expose nothing to UIA (custom canvases, some games), which is where a vision
fallback belongs.

**9. Not built, by design: clipboard-paste insertion.**
*Reasoning (not measured):* paste clobbers the user's clipboard, renders as one visible
select-and-replace, and is blocked in some apps. `SendInput` with `KEYEVENTF_UNICODE` types any
BMP character into any focused control and is what makes the in-place edit look like editing.

**10. Not built yet: an LLM in the correction loop.**
*Reasoning:* the rule-based resolver costs ~0.07 ms p95 per partial; a model call costs
hundreds of ms and nondeterminism in a path that runs on every ASR update. The `hard` category
(7/12 failures) is exactly the evidence that would justify a *slow path*: a model that
re-renders the final text once, after endpointing, behind the same `render_target` signature.

## Known failures and limits

* The `hard` set shows the shape of what the rules miss: corrections that replace a
  determiner-led noun phrase ("a list, no, a dict of users"), a number without a preposition
  ("three, no, four reviewers"), or an adjective inside a phrase ("the blue button, no, the
  green one"). See `results/REPORT.md` and the dashboard's record explorer.
* The dataset is synthetic. Nothing here is a user study; TTFA and COR are reproducible
  *model* numbers under a fixed ASR profile, not perceptual measurements.
* Native backends are Windows-only and exercised manually, not in CI. macOS `AXUIElement` and a
  `CGEvent` sink are the obvious next ports.
* The live microphone path re-transcribes a sliding window with `faster-whisper`; it is
  dependency-light but not the efficient way to stream.
* Grounding uses fuzzy name matching over tree nodes; it has no notion of visual layout beyond
  bounding boxes.

## Repository layout

```
hci_common/        Clock (injectable), KeyOp + simulator, text metrics
thought_stream/    disfluency, commands, patcher, style, engine, sinks, backends/windows_input
voice_action/      intent, grounding, actions, speculation, agent, transcribers, backends/{windows_uia,windows_os}
voicehci_bench/    schema, dataset, metrics, systems, runner, report, dashboard/index.html
data/              voicehci_bench_v1.jsonl (182 records)
results/           latest.json, REPORT.md (regenerated by `voicehci-bench run`)
tests/             265 tests
docs/DEMO_SCRIPT.md  the 60-second recording plan
```

## Live demos (Windows)

```bash
pip install -e ".[windows,audio]"
thought-stream demo --live --delay 0.15   # focus any text field; watch the correction land in place
voice-action live --no-send              # microphone -> intent -> real apps; never presses Enter
```

The live agent persists trust scores in `.voice_action_trust.json`, so `PressSend` stays on
`confirm` until it has earned its way to `preview`.

## License

MIT.
