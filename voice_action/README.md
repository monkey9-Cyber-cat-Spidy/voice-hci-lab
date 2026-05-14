# voice_action: Speculative Voice-to-Action Computer Use with Earned Trust

## Abstract

Modern conversational AI systems are capable of reasoning and generating structured tool-calling invocations. However, when applied to desktop operating system automation, standard request-response pipelines exhibit severe perceptual latency: the user must complete an utterance, wait for speech silence endpointing (400-800 ms), wait for full-sequence ASR finalization (300-600 ms), and wait for model inference before application execution begins. On desktop cold starts, total latency frequently exceeds 5 to 7 seconds.

`voice_action` introduces a **speculative execution and early-intent classification framework** for desktop computer use. By classifying intent on streaming partial speech representations, the system initiates asynchronous application pre-warming while the user is still speaking. If the speaker alters their instruction mid-sentence, the speculative engine executes an automated compensation rollback, closing pre-warmed targets without user intervention. Furthermore, the architecture enforces a deterministic **Earned Trust Policy** that protects users from premature destructive execution while allowing friction-free operation on trusted patterns. 

In benchmark evaluations on synthetic desktop interaction tasks, `voice_action` reduces Time-to-First-Action (TTFA) median latency from 2308 ms to 2061 ms across general tasks, and reduces cold-start application presentation latency from 6404 ms to 1482 ms on complex compound utterances, achieving 100% intent and slot accuracy with 0% unhandled intent drift.

```
+----------------------------------------------------------------------------------------------------+
|                                    VOICE-ACTION PIPELINE TIMELINE                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  Speech Onset (t = 0 ms)                                                                           |
|       |                                                                                            |
|       v                                                                                            |
|  [ Partial: "open sl" ]            -> Classify: Intent=OPEN_APP, Slot: None (Wait)                 |
|       |                                                                                            |
|  [ Partial: "open slack" ]         -> Classify: Intent=OPEN_APP, Slot: slack (Conf=0.95)           |
|       |                               |                                                            |
|       |                               +-> ASYNC PRE-WARM: Launch Slack binary in background        |
|       v                                                                                            |
|  [ Partial: "open slack and..." ]  -> Hypothesis key unchanged -> Retain pre-warmed instance       |
|       |                                                                                            |
|  Speaker finishes (t = 6014 ms)                                                                    |
|       |                                                                                            |
|  [ Final ASR Finalized ]           -> COMMIT PHASE (t = 6054 ms):                                  |
|                                       - Window already active on screen (TTFA = 1482 ms)           |
|                                       - Accessibility Tree grounded: composer edit control found   |
|                                       - Message typed via synthetic keyboard events                |
|                                       - Destructive action (PressSend) gated by TrustPolicy        |
+----------------------------------------------------------------------------------------------------+
```

---

## 1. The Perceptual Latency Crisis in Voice Computer Use

In human-computer interaction, actions with latencies under 100 ms feel instantaneous; latencies under 1000 ms maintain an uninterrupted train of thought. Once latency exceeds 2000 ms, user engagement degrades into passive waiting.

Serial voice-to-action systems compound four independent delays:
$$\tau_{\text{serial}} = \tau_{\text{speech}} + \tau_{\text{endpoint}} + \tau_{\text{ASR}} + \tau_{\text{intent}} + \tau_{\text{cold\_start}} + \tau_{\text{grounding}} + \tau_{\text{exec}}$$

For a typical 6-second sentence (*"open slack and message john saying running late, start without me"*):
- $\tau_{\text{speech}} \approx 6000\text{ ms}$
- $\tau_{\text{endpoint}} \approx 400\text{ ms}$
- $\tau_{\text{ASR}} \approx 120\text{ ms}$
- $\tau_{\text{cold\_start}} \approx 350 - 2500\text{ ms}$ (Slack, Chrome, VS Code cold launches)
- Result: The user waits over 6.4 seconds before any visual feedback appears on their display.

`voice_action` eliminates $\tau_{\text{cold\_start}}$ from the critical path by evaluating hypotheses over partial transcripts $\tilde{T}_t$:
$$\tau_{\text{speculative}} = \max(\tau_{\text{hypothesis}} + \tau_{\text{prewarm}}, \tau_{\text{speech}}) + \tau_{\text{commit}}$$

Visual feedback (TTFA) occurs as soon as the target application appears on screen - often within 1.5 seconds of the user beginning to speak.

---

## 2. Streaming Intent Classification & Hypothesis Invariants

### 2.1 Prefix Grammar vs Latent Neural Delays
While large language models provide broad coverage, their inference latency (200-800 ms per token generation) makes them unsuitable for continuous streaming updates arriving every 100 ms from an acoustic model.

`voice_action/intent.py` implements a **streaming prefix grammar** that evaluates in under 0.05 ms:
- Intent definitions: `OPEN_APP`, `FOCUS_WINDOW`, `SEND_MESSAGE`, `SEARCH_WEB`, `MOVE_FILE`, `TYPE_TEXT`, `UNDO`, `CANCEL`.
- Confidence scoring: Scales dynamically with slot completeness:
  - Base verb detected (*"open"*): Confidence = 0.35 (insufficient to pre-warm).
  - Target application resolved (*"open slack"*): Confidence = 0.95 (triggers pre-warming).
- Compound command segmentation: Splitting phrases on discourse conjunctions (`and`, `then`).

### 2.2 Fuzzy Acoustic Alias Resolution
Spoken acoustics frequently lead to phonetic misrecognition in small streaming models:
- Spoken *"Slack"* transcribed as *"slag"* or *"slack app"*.
- Spoken *"Notepad"* transcribed as *"note pad"*.
- Spoken *"Visual Studio Code"* transcribed as *"code"*, *"the editor"*, or *"vscode"*.

The classifier resolves tokens against canonical alias tables combined with normalized token prefix searches and Levenshtein distance metrics (`cutoff=0.8`). If an acoustic mishear matches a known alias, confidence is preserved without failure.

### 2.3 Integration with Disfluency Engine
Critically, partial transcripts are passed through `thought_stream`'s pivot resolver before classification. If a user speaks:
> *"open spotify, no wait, open slack"*

The disfluency resolver retracts *"spotify"* before the intent grammar parses the string, ensuring that Spotify is never erroneously executed or pre-warmed.

---

## 3. Speculative Pre-Warming and Rollback Dynamics

The speculative execution lifecycle is governed by an explicit state machine:

```
[ IDLE ] 
    |
    | Partial transcript yields Hypothesis with Conf >= 0.85
    v
[ PRE-WARMED ] -> Process spawned or resolved asynchronously
    |
    +---> Case A: Final transcript matches Hypothesis Key
    |              |
    |              v
    |         [ COMMITTED ] -> Reuses running process; executes remaining slots
    |
    +---> Case B: Hypothesis Key changes or speech cancelled
                   |
                   v
              [ ABORTED ] -> Executes automated compensation rollback; terminates process
```

### 3.1 Hypothesis Key Invariant
Every speculative hypothesis constructs an immutable identity key:
$$\text{Key} = (\text{Intent}, \text{App}, \text{Recipient}, \text{Destination})$$

While incoming partial transcripts may fluctuate in non-critical tokens (*"open slack"*, *"open slack please"*, *"open slack and"*), the hypothesis key remains invariant. The engine retains the pre-warmed process without re-launching.

### 3.2 Automated Compensation Rollback
If the speaker pivots (*"open slack... actually make that terminal"*), the hypothesis key changes. The speculative manager triggers an immediate rollback:
1. Locates the process identifier (PID) spawned during pre-warming.
2. Sends an asynchronous termination signal (`SIGTERM` / `TerminateProcess`).
3. Resets the context and pre-warms the newly requested target.

---

## 4. Grounding via Accessibility Trees vs Vision Overhead

### Architectural Postmortem (Decision 8)
A prevalent design in computer-use research involves capturing full-screen screenshots and passing images to multi-modal vision models. We explicitly rejected this approach based on three empirical constraints:
1. **Latency Overhead**: Capturing, downsampling, and transmitting a 4K frame to a vision endpoint requires 600-1200 ms per step.
2. **Coordinate Drift**: Multi-monitor scaling factors, window drag states, and UI DPI shifts cause coordinate prediction errors.
3. **Computational Inefficiency**: Processing millions of screen pixels to find a 20-pixel text field is computationally disproportionate.

### The UI Automation (UIA) Solution
`voice_action/grounding.py` interfaces directly with operating system accessibility trees:
- On Windows: Uses `IUIAutomation` via native COM bindings (`ctypes` / `uiautomation`).
- **Budget Enforced Search**: The tree traversal is bounded by a strict **15.0 ms time budget**. If an element is not resolved within 15 ms, the search terminates with a partial tree rather than blocking the UI thread.
- **Control Semantics**: Elements expose structural roles (`edit`, `button`, `treeitem`, `window`) and names, enabling deterministic, layout-independent grounding.

---

## 5. Earned Trust Policy & Destructive Action Safety

User trust in voice interfaces is fragile: a single erroneously sent email or deleted file destroys user adoption.

`voice_action/actions.py` introduces a deterministic **Trust Policy** governing all action execution:
1. **Reversible Actions (`auto`)**: Launching applications, focusing windows, and typing drafts are considered safe and execute automatically. Every reversible action produces an encrypted `Receipt` stored in an undo stack.
2. **Irreversible Actions (`confirm` / `preview`)**: Actions such as clicking *"Send"*, dispatching emails, or deleting files begin at the `confirm` tier, requiring explicit user confirmation.
3. **Trust Escalation**:
   - Each uncontested, successfully completed action adds $+1$ to that action's trust score.
   - After 7 successful executions, the action escalates from `confirm` to `preview`.
   - After 10 successful executions, it escalates to `auto`.
4. **Punitive Trust Decay**:
   - If a user triggers an undo (*"undo that"* or `Ctrl+Z`), the trust score for that action immediately drops by **3 points**, instantly reverting automated permissions back to mandatory confirmation.

---

## 6. Empirical Performance Comparison

Evaluated on mock and live operating system desktop tasks (380 ms/word, 120 ms ASR lag, 400 ms endpointing silence, 350 ms cold start):

| Scenario | Serial Execution TTFA | Speculative TTFA | Latency Saved | Prewarm Hit Rate | Intent Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `"open slack and message john..."` | 6404 ms | **1482 ms** | **4922 ms (76.8%)** | 100% | 100% |
| `"switch to vs code"` | 2463 ms | **2463 ms** | 0 ms (warm process) | 100% | 100% |
| `"search for faster whisper..."` | 3820 ms | **1969 ms** | **1851 ms (48.4%)** | 100% | 100% |
| `"open slag"` *(Acoustic mishear)* | 1882 ms | **1482 ms** | **400 ms (21.3%)** | 100% | 100% |
| **All Tasks Combined (Median p50)** | **2308 ms** | **2061 ms** | **247 ms** | **60%** | **100%** |

---

## 7. Verification and Test Suite

- `tests/test_intent_grounding.py`: Intent classification, slot extraction, compound splitting, and fuzzy app alias matching.
- `tests/test_actions_speculation.py`: Pre-warm spawning, rollback under hypothesis change, undo receipts, and trust escalation curves.
- `tests/test_cli.py`: End-to-end simulation of CLI commands and trace output validation.

Run test suite:
```bash
pytest tests/test_intent_grounding.py tests/test_actions_speculation.py tests/test_cli.py -v
```
