"""voice-action CLI.

    voice-action demo                      # scripted utterances, mock OS, timeline
    voice-action say "open slack and message john saying running late"
    voice-action say --real "open notepad" # execute on real Windows OS
    voice-action live                      # microphone + real Windows backend

The demo prints the millisecond timeline that matters: when the first
hypothesis fired, when the app was pre-warmed, when the transcript finalised,
and when the first UI change landed (time-to-first-action).
"""

from __future__ import annotations

import argparse
import json

from hci_common.clock import FakeClock, MonotonicClock

from .actions import ActionContext, MockOSBackend, TrustPolicy
from .agent import VoiceActionAgent
from .grounding import MockUIProvider, UINode, UITree
from .transcribers import ScriptedTranscriber

DEMO = [
    "open slack and message john saying running late, start without me",
    "switch to vs code",
    "search for faster whisper streaming latency",
    "open slag",  # ASR mishear -> fuzzy app resolution
    "undo that",
]


def slack_tree() -> UITree:
    return UITree("slack", "Slack - Wispr Lab", [
        UINode("treeitem", "john", (10, 100, 200, 120)),
        UINode("treeitem", "general", (10, 130, 200, 150)),
        UINode("edit", "Message #general", (220, 700, 1200, 740), focused=True),
        UINode("button", "Send", (1210, 705, 1250, 735)),
        UINode("edit", "Search", (300, 10, 900, 40)),
    ])


def _print_trace(label: str, t, with_spec: bool) -> None:
    on = t.speech_onset_ms
    def fmt(v):
        return "   -  " if v is None else f"{v - on:6.0f}"
    print(f"\n  {label:<14} speculation={'on ' if with_spec else 'off'}")
    print(f"    first hypothesis @ {fmt(t.first_hypothesis_ms)} ms")
    print(f"    prewarm          @ {fmt(t.prewarm_ms)} ms")
    print(f"    final transcript @ {fmt(t.final_transcript_ms)} ms")
    print(f"    first UI change  @ {fmt(t.first_ui_change_ms)} ms   <- TTFA")
    print(f"    commit done      @ {fmt(t.commit_end_ms)} ms   (commit latency "
          f"{t.commit_latency_ms if t.commit_latency_ms is not None else '-'} ms)")
    print(f"    actions: {t.actions}  ok={t.ok} pending_confirm={t.pending_confirm}")


def run_scripted(text: str, speculation: bool, trust: TrustPolicy | None = None, real: bool = False):
    if real:
        from .backends.windows_os import WindowsOSBackend
        from .grounding import make_os_ui_provider

        clock = MonotonicClock()
        ctx = ActionContext(os=WindowsOSBackend(), ui=make_os_ui_provider(clock), clock=clock)
        agent = VoiceActionAgent(ctx, trust=trust or TrustPolicy(), enable_speculation=speculation)
        tr = ScriptedTranscriber(text, clock=clock)
        return agent.run(tr, speech_onset_ms=clock.now_ms(), confirm=False)

    clock = FakeClock()
    os_b = MockOSBackend(clock=clock, running={"vscode", "terminal"})
    ctx = ActionContext(os=os_b, ui=MockUIProvider(slack_tree()), clock=clock)
    agent = VoiceActionAgent(ctx, trust=trust or TrustPolicy(), enable_speculation=speculation)
    tr = ScriptedTranscriber(text, clock=clock)
    return agent.run(tr, speech_onset_ms=0.0, confirm=False)


def cmd_demo(args: argparse.Namespace) -> int:
    trust = TrustPolicy()
    for utt in DEMO:
        print(f"\n▶ \"{utt}\"")
        for spec in (True, False):
            t = run_scripted(utt, spec, trust)
            _print_trace("", t, spec)
    return 0


def cmd_say(args: argparse.Namespace) -> int:
    t = run_scripted(args.text, not args.no_speculation, real=args.real)
    _print_trace(args.text[:14], t, not args.no_speculation)
    if args.json:
        print(json.dumps(t.to_dict(), indent=2, default=str))
    return 0


def cmd_live(args: argparse.Namespace) -> int:  # pragma: no cover
    from .backends.windows_os import WindowsOSBackend
    from .grounding import make_os_ui_provider
    from .transcribers import FasterWhisperStreamingTranscriber

    clock = MonotonicClock()
    ctx = ActionContext(os=WindowsOSBackend(), ui=make_os_ui_provider(clock), clock=clock)
    agent = VoiceActionAgent(ctx, trust=TrustPolicy.load(args.trust_file),
                             send_messages=not args.no_send)
    stt = FasterWhisperStreamingTranscriber(model_size=args.model, clock=clock)
    print("Listening. Say e.g. 'open notepad' / 'switch to chrome' / 'undo that'. Ctrl+C to quit.")
    try:
        while True:
            onset = None
            chunks = []
            for ch in stt:
                if onset is None:
                    onset = stt.speech_onset_ms or clock.now_ms()
                chunks.append(ch)
                if ch.final:
                    break
            t = agent.run(iter(chunks), speech_onset_ms=onset)
            _print_trace(t.transcript[:14], t, True)
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="voice-action")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.set_defaults(fn=cmd_demo)
    s = sub.add_parser("say")
    s.add_argument("text")
    s.add_argument("--no-speculation", action="store_true")
    s.add_argument("--json", action="store_true")
    s.add_argument("--real", action="store_true", help="execute actions on the real Windows OS")
    s.set_defaults(fn=cmd_say)
    lv = sub.add_parser("live")
    lv.add_argument("--model", default="base.en")
    lv.add_argument("--trust-file", default=".voice_action_trust.json")
    lv.add_argument("--no-send", action="store_true", help="never press Enter in chat apps")
    lv.set_defaults(fn=cmd_live)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
