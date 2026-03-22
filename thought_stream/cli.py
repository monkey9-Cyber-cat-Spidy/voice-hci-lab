"""thought-stream CLI.

    thought-stream demo                 # scripted demo with a recording sink
    thought-stream demo --live          # type into the focused window (Windows)
    thought-stream text "say ... actually make that ..."  # one-shot resolve

The live demo gives you 3 seconds to focus a text field, then streams a
scripted utterance word by word so you can watch the in-place correction.
"""

from __future__ import annotations

import argparse
import sys
import time

from hci_common.clock import MonotonicClock

from .engine import ThoughtStreamEngine, render_target
from .sinks import RecordingSink, make_os_sink
from .style import AppContext, resolve_style

DEMO_UTTERANCES = [
    ("Slack", "hey team um the deployment is ready actually wait make that delayed until 4 PM "
              "because QA found an edge case"),
    ("Notion", "action items new line bullet ship the patch new line bullet notify the on call "
               "scratch that notify support period"),
    ("Slack", "send it to john at four no wait to jane at four"),
]


def _fmt_op(o) -> str:
    return f"{o.kind}({o.text!r})" if o.kind == "type" else f"{o.kind}({o.count})"


def _stream_words(engine: ThoughtStreamEngine, utterance: str, delay: float, verbose: bool) -> None:
    words = utterance.split()
    engine.mark_speech_onset()
    for i in range(1, len(words) + 1):
        partial = " ".join(words[:i])
        r = engine.feed(partial, final=(i == len(words)))
        if verbose and r.ops:
            ops = ", ".join(_fmt_op(o) for o in r.ops)
            print(f"  [{r.latency_ms:6.2f} ms] {r.plan.strategy:<13} {ops}")
        if delay:
            time.sleep(delay)


def cmd_demo(args: argparse.Namespace) -> int:
    live = args.live
    if live:
        sink = make_os_sink()
        print("Focus a text field... typing starts in 3 s")
        time.sleep(3)
    for app, utt in DEMO_UTTERANCES:
        ctx = AppContext(app_name=app)
        sink = sink if live else RecordingSink()
        eng = ThoughtStreamEngine(sink, context=ctx, clock=MonotonicClock())
        print(f"\n[{app} / style={resolve_style(ctx).name}]\n  spoken: {utt}")
        _stream_words(eng, utt, args.delay, args.verbose)
        shown = sink.text if isinstance(sink, RecordingSink) else eng.rendered
        print(f"  on screen: {shown!r}")
        s = eng.stats
        print(f"  updates={s.updates} dispatches={s.dispatches} keystrokes={s.keystrokes} "
              f"pivots={s.pivots} mean={s.mean_latency_ms:.3f}ms max={s.max_latency_ms:.3f}ms")
        if live:
            sink.dispatch([__import__("hci_common.keystrokes", fromlist=["type_text"]).type_text("\n")])
    return 0


def cmd_text(args: argparse.Namespace) -> int:
    ctx = AppContext(app_name=args.app)
    target, pivots = render_target(args.text, resolve_style(ctx))
    print(target)
    for p in pivots:
        print(f"  pivot[{p.kind}/{p.strategy}] {p.pivot!r}: {p.retracted!r} -> {p.replacement!r}",
              file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="thought-stream")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--live", action="store_true", help="type into the focused window")
    d.add_argument("--delay", type=float, default=0.0, help="seconds between words")
    d.add_argument("-v", "--verbose", action="store_true")
    d.set_defaults(fn=cmd_demo)
    t = sub.add_parser("text")
    t.add_argument("text")
    t.add_argument("--app", default="Notion")
    t.set_defaults(fn=cmd_text)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
