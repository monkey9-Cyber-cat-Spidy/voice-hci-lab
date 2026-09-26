# 60-second demo script

Goal: show a mid-sentence correction landing *in place* in a real app, with a live latency
readout, then show a voice action whose target app is already open before the sentence ends.

## Setup (off camera)

```bash
pip install -e ".[windows,audio]"
voicehci-bench run && voicehci-bench serve     # dashboard open in a browser tab
```

Open Slack (or any chat app) and a terminal side by side. Terminal runs:

```bash
thought-stream demo --live --delay 0.15 -v
```

The `-v` lines are the on-screen latency counter: per-update compute in ms, the patch strategy,
and the exact keystrokes dispatched.

## Shot list

| t | On screen | Say / do |
|---|---|---|
| 0-10 s | Slack message box focused, terminal beside it | "Dictation tools type what you said. This types what you *meant*." |
| 10-25 s | Words appear as spoken; at "actually wait, make that delayed until 4 PM" only `ready` is deleted and replaced | Let the demo speak the first utterance. Point at the terminal: `complement` strategy, `backspace(5)`, `type('delayed until 4 PM')`, 0.0x ms. |
| 25-35 s | Second utterance: bullets form; "scratch that" removes only the last bullet | "Commands and corrections share the same clause model, so a retraction can't eat your formatting." |
| 35-50 s | `voice-action live --no-send`; say "open slack and message john saying running late" | Slack is in the foreground by the word "slack". The timeline prints TTFA at ~1.5 s against a ~6 s sentence. The Enter press is held: *"send to john" needs confirmation until trust is earned.* |
| 50-60 s | Dashboard: Pareto chart (TTFA vs COR), then the `hard` row in the heat table | "And here is where it still fails: 7 of 12 adversarial corrections. That's the next experiment." |

## Post copy

> Exploring sub-second speculative voice-to-action and streaming disfluency correction as open
> HCI research. Three things in the repo: a voice agent that pre-warms the app you're about to
> name and rolls back when it guessed wrong; a dictation engine that resolves "no wait, make
> that..." with a surgical in-place edit; and VoiceHCI-Bench, which measures time-to-first-action,
> correction overhead and intent drift instead of WER. Killed-ideas log in the README.
